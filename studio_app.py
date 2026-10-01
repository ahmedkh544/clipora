import os, threading, uuid, re, subprocess, random
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from studio.core import select_highlights, select_narrative_sequence, build_keep_ranges, word_timings, detect_visual_scene_boundaries
from studio.toolbox import refine_narrative_boundaries
from studio.factory import classify_source, build_listing_command, normalize_entries, select_video_urls, make_metadata
from studio.youtube_upload import upload_video, youtube_upload_ready
from shorts_generator.local.transcriber import transcribe_local
ROOT=Path(__file__).resolve().parent
RENDER_WIDTH=720
RENDER_HEIGHT=1280
RENDER_PRESET="ultrafast"
UPLOAD=ROOT/"studio_uploads"; OUTPUT=ROOT/"studio_output"; BROLL=ROOT/"studio_broll"
for d in (UPLOAD,OUTPUT,BROLL): d.mkdir(exist_ok=True)
JOBS={}; app=Flask(__name__); app.config["MAX_CONTENT_LENGTH"]=4*1024*1024*1024
HTML="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>VideoForge Studio</title><style>body{font-family:Arial;background:#0d1117;color:#e6edf3;max-width:1050px;margin:25px auto;padding:18px}h1{font-size:42px;margin-bottom:5px}.sub{color:#8b949e}section{background:#161b22;padding:22px;border-radius:16px;margin:16px 0}input,select,button{padding:11px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#fff;margin:4px}button{cursor:pointer;background:#238636}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}.bar{height:9px;background:#30363d;border-radius:8px}.fill{height:9px;background:#2ea043;border-radius:8px;width:0}.clip{border:1px solid #30363d;padding:14px;margin:10px 0;border-radius:10px}.clip video{display:block;width:min(100%,360px);aspect-ratio:9/16;height:auto;object-fit:contain;background:#000;border-radius:12px}label{display:block;margin:8px 0}.pill{display:inline-block;background:#21262d;padding:5px 8px;border-radius:20px;margin:3px;color:#8b949e}</style></head><body><h1>VideoForge</h1><p class='sub'>Local AI video factory — animated captions, word highlighting, hook scoring, silence cutting, zoom, B-roll and batch processing.</p><section><form id='f'><label>Video files <input type='file' name='videos' accept='video/*' multiple></label><label>YouTube URL <input name='url' type='url' style='width:80%' placeholder='Optional: https://www.youtube.com/watch?v=...'></label><div class='grid'><label>Shorts per video <input name='count' type='number' min='1' max='20' value='8'><small style='display:block;color:#8b949e'>Splits the entire video into this many sequential parts.</small></label><label>Videos from channel/playlist <input name='source_count' type='number' min='1' max='10' value='3'></label><label>Template <select name='template'><option value='tiktok'>TikTok</option><option value='reels'>Instagram Reels</option><option value='youtube'>YouTube Shorts</option></select></label><label>Silence cut <select name='silence'><option value='on'>On</option><option value='off'>Off</option></select></label><label>Auto Zoom <select name='zoom'><option value='on'>On</option><option value='off'>Off</option></select></label><label>Captions <select name='captions'><option value='karaoke'>Animated + word highlight</option><option value='plain'>Animated line captions</option></select></label><label>B-roll <select name='broll'><option value='auto'>Auto if local images exist</option><option value='off'>Off</option></select></label><label>YouTube upload <select name='upload'><option value='off'>Off</option><option value='on'>Auto upload (private)</option></select></label></div><p><span class='pill'>Optional B-roll: put JPG/PNG/WebP files in studio_broll</span><span class='pill'>Multiple videos = batch mode</span></p><button>CREATE SHORTS</button></form><p id='status'></p><div class='bar'><div id='fill' class='fill'></div></div></section><section id='results'></section><script>const f=document.getElementById('f'),s=document.getElementById('status'),fill=document.getElementById('fill'),r=document.getElementById('results');f.onsubmit=async e=>{e.preventDefault();r.innerHTML='';s.textContent='Uploading/queueing...';const x=await fetch('/api/jobs',{method:'POST',body:new FormData(f)});const j=await x.json();if(!x.ok){s.textContent=j.error||'Error';return}poll(j.id)};async function poll(id){const x=await fetch('/api/jobs/'+id),j=await x.json();s.textContent=j.message||j.status;fill.style.width=(j.progress||0)+'%';if(j.status==='done'){r.innerHTML=j.clips.map((c,i)=>'<div class=clip><b>#'+(i+1)+' '+escapeHtml(c.title)+'</b><p>'+escapeHtml(c.reason)+'</p><video controls playsinline src="/files/'+c.file+'"></video><br><a href="/files/'+c.file+'" download>Download</a></div>').join('');return}if(j.status==='error'){r.innerHTML='<b>Error:</b> '+escapeHtml(j.error);return}setTimeout(()=>poll(id),1000)}function escapeHtml(x){return String(x).replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[m]))}</script></body></html>"""
def ass_ts(x):
    x=max(0,float(x)); h=int(x//3600); m=int(x%3600//60); s=int(x%60); cs=int((x-int(x))*100); return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
def safe_ass(text): return str(text).replace("\\","\\\\").replace("{","\\{").replace("}","\\}").replace("\n"," ").strip()
def rtl_ass_text(text):
    text=str(text)
    if any("\u0600" <= ch <= "\u06ff" or "\u0750" <= ch <= "\u077f" or "\u08a0" <= ch <= "\u08ff" for ch in text):
        return chr(0x202b) + text + chr(0x202c)
    return text
def make_ass(transcript,start,end,out,style="tiktok",mode="karaoke"):
    size={"tiktok":45,"reels":43,"youtube":40}.get(style,43); margin={"tiktok":115,"reels":125,"youtube":110}.get(style,115)
    lines=["[Script Info]","ScriptType: v4.00+","PlayResX: 720","PlayResY: 1280","WrapStyle: 2","","[V4+ Styles]","Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",f"Style: Default,Arial,{size},&H00FFFFFF,&H0000FFFF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4,2,2,55,55,{margin},1","","[Events]","Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    for s in transcript.get("segments",[]):
        a=float(s.get("start",0)); b=float(s.get("end",0))
        if b<=start or a>=end: continue
        aa=max(a,start); bb=min(b,end); text=safe_ass(s.get("text",""))
        if not text: continue
        if mode=="karaoke":
            pieces=[]
            for w,wa,wb in word_timings(text,aa-start,bb-start): pieces.append("{\\k%d}%s"%(max(1,int((wb-wa)*100)),w))
            text=" ".join(pieces)
        text=rtl_ass_text(text)
        lines.append(f"Dialogue: 0,{ass_ts(aa-start)},{ass_ts(bb-start)},Default,,0,0,0,,{text}")
    Path(out).write_text("\n".join(lines),encoding="utf-8")
def render(src,start,end,ass,out,transcript=None,remove_silence=True,auto_zoom=True,broll=True):
    ranges=build_keep_ranges(transcript,start,end,min_gap=0.7) if transcript and remove_silence else [(start,end)]
    if not ranges: ranges=[(start,end)]
    filters=[]
    for i,(a,b) in enumerate(ranges): filters += [f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]",f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]"]
    va=''.join(f"[v{i}][a{i}]" for i in range(len(ranges))); filters.append(f"{va}concat=n={len(ranges)}:v=1:a=1[vcat][acat]")
    ass_path=ass.replace('\\','/').replace(':','\\:'); filters.append(f"[vcat]scale={RENDER_WIDTH}:{RENDER_HEIGHT}:force_original_aspect_ratio=increase,crop={RENDER_WIDTH}:{RENDER_HEIGHT},subtitles='{ass_path}'[vout]")
    images=[p for p in BROLL.iterdir() if p.suffix.lower() in {'.jpg','.jpeg','.png','.webp'}] if broll else []
    if images:
        img=str(random.choice(images)).replace('\\','/').replace(':','\\:'); filters.append(f"movie='{img}',scale=360:-2,format=rgba,colorchannelmixer=aa=0.88[brollv]"); filters.append("[vout][brollv]overlay=W-w-35:35:shortest=1[vfinal]"); vmap="[vfinal]"
    else: vmap="[vout]"
    cmd=["ffmpeg","-y","-loglevel","error","-i",src,"-filter_complex",';'.join(filters),"-map",vmap,"-map","[acat]","-c:v","libx264","-preset",RENDER_PRESET,"-crf","27","-c:a","aac","-b:a","128k","-movflags","+faststart",out]; subprocess.run(cmd,check=True)
def download_youtube(url,job_id,suffix="youtube"):
    out=UPLOAD/(job_id+"_"+suffix+".%(ext)s"); cmd=[os.fspath(ROOT/".venv"/"Scripts"/"python.exe"),"-m","yt_dlp","-f","bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b","--merge-output-format","mp4","-o",str(out),url]; subprocess.run(cmd,check=True); files=sorted(UPLOAD.glob(job_id+"_"+suffix+".*"),key=lambda p:p.stat().st_mtime,reverse=True)
    if not files: raise RuntimeError("YouTube download produced no file")
    return files[0]

def list_youtube(url,limit):
    cmd=build_listing_command(url,limit)
    cmd[0]=os.fspath(ROOT/".venv"/"Scripts"/"python.exe")
    cmd.insert(1,"-m"); cmd.insert(2,"yt_dlp")
    p=subprocess.run(cmd,capture_output=True,text=True,check=True)
    import json
    return normalize_entries(json.loads(p.stdout))
def media_duration(path):
    p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True,check=True)
    return float(p.stdout.strip())

def run_job(job_id,paths,count,opts):
    try:
        clips=[]; total=len(paths)
        for vi,path in enumerate(paths):
            base=vi/total*100; JOBS[job_id].update(status="working",progress=int(base),message=f"Transcribing {vi+1}/{total} locally..."); transcript=transcribe_local(str(path)); JOBS[job_id].update(progress=int(base+20/total),message=f"Analyzing visual scene boundaries {vi+1}/{total}..."); scene_boundaries=detect_visual_scene_boundaries(str(path)); duration=media_duration(path); JOBS[job_id].update(progress=int(base+20/total),message=f"Building full-video narrative sequence {vi+1}/{total}..."); highlights=select_narrative_sequence(transcript,count,target_duration=None,scene_boundaries=scene_boundaries,total_duration=duration)
            # Full-video narrative mode already has exact source boundaries; waveform refinement is intentionally disabled here.
            for n,h in enumerate(highlights,1):
                JOBS[job_id].update(progress=min(99,int(base+20/total+(70/total)*(n/len(highlights)))),message=f"Rendering {vi+1}/{total} — short {n}/{len(highlights)}..."); ass=OUTPUT/f"{job_id}_{vi+1}_{n}.ass"; out=OUTPUT/f"{job_id}_{vi+1}_{n}.mp4"; make_ass(transcript,h["start_time"],h["end_time"],str(ass),opts["template"],opts["captions"]); render(str(path),h["start_time"],h["end_time"],str(ass),str(out),transcript,False,opts["zoom"]=="on",opts["broll"]=="auto"); meta=make_metadata(h["hook_sentence"],opts["template"]); meta["source_start"]=h["start_time"]; meta["source_end"]=h["end_time"]; meta["source_duration"]=round(h["end_time"]-h["start_time"],3); upload_status="disabled"
                if opts.get("upload")=="on":
                    if youtube_upload_ready(ROOT):
                        meta["youtube_id"]=upload_video(str(out),meta,ROOT,"private"); upload_status="uploaded"
                    else: upload_status="credentials_required"
                meta["upload_status"]=upload_status; (OUTPUT/f"{job_id}_{vi+1}_{n}.json").write_text(__import__("json").dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8"); clips.append({"file":out.name,"title":meta["title"],"reason":h["virality_reason"],"metadata":meta})
        if not clips: raise RuntimeError("No speech highlights were found in the supplied videos.")
        JOBS[job_id].update(status="done",progress=100,message=f"Finished — {len(clips)} Shorts",clips=clips)
    except Exception as e: JOBS[job_id].update(status="error",error=str(e),message="Failed")
@app.get("/health")
def health():
    return jsonify(status="ok",service="clipora",jobs=len(JOBS))

@app.get("/")
def home(): return render_template_string(HTML)
@app.post("/api/jobs")
def create():
    files=request.files.getlist("videos"); url=request.form.get("url","").strip()
    if not files and not url: return jsonify(error="Add at least one video or a YouTube URL"),400
    jid=uuid.uuid4().hex; paths=[]
    for f in files:
        if f.filename: safe=re.sub(r"[^A-Za-z0-9_.-]","_",f.filename); p=UPLOAD/(jid+"_"+safe); f.save(p); paths.append(p)
    if url:
        try:
            source_kind=classify_source(url); source_count=max(1,min(10,int(request.form.get("source_count","3"))))
            if source_kind=="video": paths.append(download_youtube(url,jid))
            elif source_kind in {"channel","playlist"}:
                entries=select_video_urls(list_youtube(url,source_count),source_count)
                for i,e in enumerate(entries,1): paths.append(download_youtube(e["url"],jid,f"youtube_{i}"))
                if not paths: raise RuntimeError("No videos found in the YouTube source")
            else: raise RuntimeError("Unsupported source URL")
        except Exception as e: return jsonify(error=f"YouTube source failed: {e}"),400
    try: count=max(1,min(20,int(request.form.get("count","5"))))
    except ValueError: count=5
    opts={"template":request.form.get("template","tiktok"),"silence":request.form.get("silence","on"),"zoom":request.form.get("zoom","on"),"captions":request.form.get("captions","karaoke"),"broll":request.form.get("broll","auto"),"upload":request.form.get("upload","off")}; JOBS[jid]={"status":"queued","progress":0,"message":"Queued"}; threading.Thread(target=run_job,args=(jid,paths,count,opts),daemon=True).start(); return jsonify(id=jid)
@app.get("/api/jobs/<jid>")
def job(jid):
    if jid not in JOBS:return jsonify(error="not found"),404
    return jsonify(JOBS[jid])
@app.get("/files/<path:name>")
def files(name): return send_from_directory(OUTPUT,name,as_attachment=False)
if __name__=="__main__":
    port=int(os.getenv("PORT","8765"))
    app.run(host="0.0.0.0",port=port,debug=False)
