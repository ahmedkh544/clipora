import json, os, re, subprocess, threading, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template_string, request, send_file, session
from studio.core import build_keep_ranges, detect_visual_scene_boundaries, select_narrative_sequence
from studio.persistence import can_create_job, cleanup_old_files, create_job, create_session, create_user, get_job, get_user_by_session, logout, recent_jobs, authenticate, update_job
from studio.storage import OUTPUT_DIR, UPLOAD_DIR, presigned_get, storage_mode, upload_object, cleanup_s3
from studio.toolbox import vertical_crop_x, visual_filter
from studio.factory import classify_source, build_listing_command, normalize_entries, select_video_urls, make_metadata
from studio.youtube_upload import upload_video, youtube_upload_ready
from shorts_generator.local.transcriber import transcribe_local

ROOT=Path(__file__).resolve().parent
RENDER_WIDTH,RENDER_HEIGHT=720,1280
RENDER_PRESET=os.getenv("CLIPORA_RENDER_PRESET","ultrafast")
BROLL=ROOT/"studio_broll"
for d in (UPLOAD_DIR,OUTPUT_DIR,BROLL): d.mkdir(parents=True,exist_ok=True)
app=Flask(__name__)
app.secret_key=os.getenv("CLIPORA_SECRET_KEY","change-me-in-production")
app.config["MAX_CONTENT_LENGTH"]=4*1024*1024*1024
EXECUTOR=ThreadPoolExecutor(max_workers=max(1,int(os.getenv("CLIPORA_WORKERS","1"))))

def cleanup_loop():
    while True:
        try:
            cleanup_old_files(UPLOAD_DIR,24); cleanup_old_files(OUTPUT_DIR,24); cleanup_s3(24)
        except Exception: pass
        threading.Event().wait(6*3600)
threading.Thread(target=cleanup_loop,daemon=True).start()

HTML="""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Clipora AI Studio</title><style>
*{box-sizing:border-box}body{font-family:Inter,Arial,sans-serif;background:#090d14;color:#eef2f7;max-width:1180px;margin:auto;padding:22px}header{display:flex;justify-content:space-between;align-items:center;gap:15px}h1{font-size:42px;margin:0}.muted{color:#8d99aa}.card{background:#111827;border:1px solid #263244;border-radius:18px;padding:20px;margin:16px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}label{display:block;color:#cbd5e1}input,select,button{width:100%;padding:11px;margin-top:6px;border-radius:10px;border:1px solid #334155;background:#0b1220;color:#fff}button{background:#2563eb;border:0;font-weight:700;cursor:pointer}.row{display:flex;gap:10px;align-items:center}.row>*{flex:1}.bar{height:10px;background:#263244;border-radius:10px;overflow:hidden}.fill{height:100%;width:0;background:#22c55e}.job{border:1px solid #263244;border-radius:14px;padding:14px;margin-top:12px}.clip{display:grid;grid-template-columns:180px 1fr;gap:15px;padding:14px 0;border-top:1px solid #263244}.clip video{width:180px;aspect-ratio:9/16;background:#000;border-radius:10px;object-fit:contain}.badge{padding:5px 9px;border-radius:999px;background:#1e293b;color:#cbd5e1;font-size:12px}.error{color:#fca5a5}.success{color:#86efac}@media(max-width:650px){.clip{grid-template-columns:1fr}.clip video{width:100%;max-width:280px}}
</style></head><body><header><div><h1>Clipora</h1><div class='muted'>Arabic-first narrative video → sequential 9:16 Shorts</div></div><div>{% if user %}<span class='badge'>{{user.email}} · {{user.plan|upper}}</span> <button style='width:auto;padding:8px 12px' onclick='logout()'>Logout</button>{% endif %}</div></header>
{% if not user %}<section class='card'><h2>Sign in / Create account</h2><div class='grid'><label>Email<input id='email' type='email' autocomplete='email'></label><label>Password<input id='password' type='password' autocomplete='current-password'></label></div><div class='row' style='margin-top:10px'><button onclick='auth("login")'>Sign in</button><button onclick='auth("register")'>Create free account</button></div><p id='authmsg' class='muted'></p></section>{% else %}<section class='card'><h2>Create Shorts</h2><form id='f'><div class='grid'><label>Video files<input type='file' name='videos' accept='video/*' multiple></label><label>YouTube URL<input name='url' type='url' placeholder='Optional YouTube URL'></label><label>Shorts per video<input name='count' type='number' min='1' max='20' value='8'></label><label>Template<select name='template'><option value='tiktok'>TikTok</option><option value='reels'>Instagram Reels</option><option value='youtube'>YouTube Shorts</option></select></label><label>Captions<select name='captions'><option value='karaoke'>Arabic word highlight</option><option value='plain'>Arabic line captions</option><option value='off'>Off</option></select></label><label>Visual processing<select name='visuals'><option value='on'>Smart 9:16 + subtle zoom</option><option value='off'>9:16 center crop</option></select></label></div><button style='margin-top:14px'>CREATE SHORTS</button></form><p id='status' class='muted'></p><div class='bar'><div id='fill' class='fill'></div></div><p class='muted'>Free plan: 3 jobs/month. Pro plan removes the monthly job limit.</p></section><section class='card'><h2>Jobs</h2><div id='jobs'></div></section><script>
async function auth(mode){const body={email:email.value,password:password.value};const x=await fetch('/api/auth/'+mode,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await x.json();if(!x.ok){authmsg.textContent=j.error||'Error';return}location.reload()}
async function logout(){await fetch('/api/auth/logout',{method:'POST'});location.reload()}
const f=document.getElementById('f');if(f)f.onsubmit=async e=>{e.preventDefault();status.textContent='Uploading and queueing…';const x=await fetch('/api/jobs',{method:'POST',body:new FormData(f)});const j=await x.json();if(!x.ok){status.textContent=j.error||'Error';return}poll(j.id)};
async function poll(id){const x=await fetch('/api/jobs/'+id),j=await x.json();status.textContent=j.message||j.status;fill.style.width=(j.progress||0)+'%';if(j.status==='done'||j.status==='error'){loadJobs();return}setTimeout(()=>poll(id),1000)}
async function loadJobs(){const x=await fetch('/api/jobs'),j=await x.json();jobs.innerHTML=j.jobs.map(job=>{let html='<div class=job><b>'+job.id.slice(0,8)+'</b> <span class=badge>'+job.status+'</span><p>'+escapeHtml(job.message||'')+'</p>';if(job.status==='done'&&job.clips){html+=job.clips.map((c,i)=>'<div class=clip><video controls playsinline src="'+c.url+'"></video><div><h3>#'+(i+1)+' '+escapeHtml(c.title)+'</h3><p>'+escapeHtml(c.reason)+'</p><a href="'+c.url+'" download>Download</a></div></div>').join('')}if(job.error)html+='<p class=error>'+escapeHtml(job.error)+'</p>';return html+'</div>'}).join('')||'<p class=muted>No jobs yet.</p>'}
function escapeHtml(x){return String(x).replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[m]))}loadJobs();setInterval(loadJobs,5000);
</script>{% endif %}</body></html>"""

def current_user(): return get_user_by_session(session.get("clipora_session"))

def ass_ts(x):
    x=max(0,float(x)); h=int(x//3600); m=int(x%3600//60); s=int(x%60); cs=int((x-int(x))*100); return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def safe_ass(text): return str(text).replace("\\","\\\\").replace("{","\\{").replace("}","\\}").replace("\n"," ").strip()

def rtl_ass_text(text):
    text=str(text)
    if any("\u0600"<=ch<="\u06ff" or "\u0750"<=ch<="\u077f" for ch in text): return chr(0x202b)+text+chr(0x202c)
    return text

def make_ass(transcript,start,end,out,mode="karaoke"):
    lines=["[Script Info]","ScriptType: v4.00+","PlayResX: 720","PlayResY: 1280","WrapStyle: 2","","[V4+ Styles]","Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding","Style: Default,DejaVu Sans,46,&H00FFFFFF,&H0000FFFF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,4,2,2,50,50,145,1","","[Events]","Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    for seg in transcript.get("segments",[]):
        a,b=float(seg.get("start",0)),float(seg.get("end",0))
        if b<=start or a>=end: continue
        aa,bb=max(a,start),min(b,end); words=seg.get("words") or []
        if mode=="off": continue
        if mode=="karaoke" and words:
            pieces=[]
            for w in words:
                wa,wb=float(w.get("start",a)),float(w.get("end",b))
                if wb<=start or wa>=end:continue
                pieces.append("{\\k%d}%s"%(max(1,int((min(wb,end)-max(wa,start))*100)),safe_ass(w.get("word",""))))
            text=" ".join(pieces)
        else:text=safe_ass(seg.get("text",""))
        text=rtl_ass_text(text)
        if text:lines.append(f"Dialogue: 0,{ass_ts(aa-start)},{ass_ts(bb-start)},Default,,0,0,0,,{text}")
    Path(out).write_text("\n".join(lines),encoding="utf-8")

def media_size(path):
    p=subprocess.run(["ffprobe","-v","error","-show_entries","stream=width,height","-of","csv=s=x:p=0",str(path)],capture_output=True,text=True,check=True); w,h=p.stdout.strip().split("x"); return int(w),int(h)

def render(src,start,end,ass,out,transcript,visuals=True,visual_index=0):
    w,h=media_size(src); crop_x=vertical_crop_x(src,RENDER_WIDTH,RENDER_HEIGHT) if visuals else max(0,(w-int(h*9/16))//2)
    vf=visual_filter(crop_x,w,h,RENDER_WIDTH,RENDER_HEIGHT,0.012+(visual_index%3)*0.008) if visuals else visual_filter(crop_x,w,h,RENDER_WIDTH,RENDER_HEIGHT,0)
    ass_path=str(ass).replace('\\','/').replace(':','\\:'); vf+=f",subtitles='{ass_path}'"
    cmd=["ffmpeg","-y","-loglevel","error","-ss",str(start),"-to",str(end),"-i",src,"-vf",vf,"-c:v","libx264","-preset",RENDER_PRESET,"-crf","25","-c:a","aac","-b:a","128k","-movflags","+faststart",out]
    subprocess.run(cmd,check=True)

def download_youtube(url,job_id,suffix="youtube"):
    out=UPLOAD_DIR/(job_id+"_"+suffix+".%(ext)s"); cmd=[os.fspath(ROOT/".venv"/"Scripts"/"python.exe"),"-m","yt_dlp","-f","bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b","--merge-output-format","mp4","-o",str(out),url]; subprocess.run(cmd,check=True); files=sorted(UPLOAD_DIR.glob(job_id+"_"+suffix+".*"),key=lambda p:p.stat().st_mtime,reverse=True); return files[0]

def list_youtube(url,limit):
    cmd=build_listing_command(url,limit); cmd[0]=os.fspath(ROOT/".venv"/"Scripts"/"python.exe"); cmd[1:1]=["-m","yt_dlp"]; return normalize_entries(json.loads(subprocess.run(cmd,capture_output=True,text=True,check=True).stdout))

def media_duration(path):
    p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True,check=True); return float(p.stdout.strip())

def run_job(job_id,user_id,paths,count,opts):
    try:
        all_clips=[]; total=len(paths)
        update_job(job_id,status="working",progress=1,message="Starting processing…")
        for vi,path in enumerate(paths):
            base=vi/total*100; update_job(job_id,progress=int(base),message=f"Transcribing Arabic audio {vi+1}/{total}…")
            transcript=transcribe_local(str(path),language="ar")
            update_job(job_id,progress=int(base+15/total),message="Detecting scene boundaries…"); scenes=detect_visual_scene_boundaries(str(path)); duration=media_duration(path)
            clips=select_narrative_sequence(transcript,count,target_duration=None,scene_boundaries=scenes,total_duration=duration)
            for n,h in enumerate(clips,1):
                update_job(job_id,progress=min(99,int(base+15/total+(80/total)*(n/len(clips)))),message=f"Rendering 9:16 short {n}/{len(clips)}…")
                ass=OUTPUT_DIR/f"{job_id}_{vi+1}_{n}.ass"; out=OUTPUT_DIR/f"{job_id}_{vi+1}_{n}.mp4"; make_ass(transcript,h["start_time"],h["end_time"],ass,opts["captions"])
                render(str(path),h["start_time"],h["end_time"],ass,str(out),transcript,opts["visuals"]=="on",n)
                meta=make_metadata(h["hook_sentence"],opts["template"]); meta.update(source_start=h["start_time"],source_end=h["end_time"],source_duration=round(h["end_time"]-h["start_time"],3),aspect_ratio="9:16",language="ar")
                key=upload_object(out,job_id,out.name); upload_status="disabled"
                if opts.get("upload")=="on" and youtube_upload_ready(ROOT): meta["youtube_id"]=upload_video(str(out),meta,ROOT,"private"); upload_status="uploaded"
                meta["upload_status"]=upload_status
                all_clips.append({"file":out.name,"title":meta["title"],"reason":h["virality_reason"],"metadata":meta,"storage_key":key})
                if storage_mode()=="s3":
                    try:out.unlink(); ass.unlink()
                    except OSError:pass
        update_job(job_id,status="done",progress=100,message=f"Finished — {len(all_clips)} Shorts",clips_json=json.dumps(all_clips,ensure_ascii=False))
    except Exception as exc:
        update_job(job_id,status="error",error=str(exc),message="Processing failed")
    finally:
        cleanup_old_files(UPLOAD_DIR,24); cleanup_old_files(OUTPUT_DIR,24)

@app.get("/health")
def health(): return jsonify(status="ok",service="clipora",storage=storage_mode())

@app.get("/")
def home(): return render_template_string(HTML,user=current_user())

@app.post("/api/auth/register")
def register():
    data=request.get_json(silent=True) or {}; email=str(data.get("email","")).strip(); password=str(data.get("password",""))
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$",email):return jsonify(error="Enter a valid email"),400
    try:uid=create_user(email,password)
    except ValueError as e:return jsonify(error=str(e)),400
    session["clipora_session"]=create_session(uid); return jsonify(ok=True)

@app.post("/api/auth/login")
def login():
    data=request.get_json(silent=True) or {}; user=authenticate(str(data.get("email","")),str(data.get("password","")))
    if not user:return jsonify(error="Invalid email or password"),401
    session["clipora_session"]=create_session(user["id"]); return jsonify(ok=True)

@app.post("/api/auth/logout")
def auth_logout():
    logout(session.pop("clipora_session",None)); return jsonify(ok=True)

@app.get("/api/account")
def account():
    user=current_user()
    if not user:return jsonify(error="authentication required"),401
    return jsonify(email=user["email"],plan=user["plan"])

@app.post("/api/jobs")
def create():
    user=current_user()
    if not user:return jsonify(error="Sign in first"),401
    if not can_create_job(user):return jsonify(error="Free plan limit reached. Upgrade to Pro to continue."),402
    files=request.files.getlist("videos"); url=request.form.get("url","").strip()
    if not files and not url:return jsonify(error="Add at least one video or a YouTube URL"),400
    jid=uuid.uuid4().hex; paths=[]
    for f in files:
        if f.filename:
            safe=re.sub(r"[^A-Za-z0-9_.-]","_",f.filename); p=UPLOAD_DIR/(jid+"_"+safe); f.save(p); paths.append(p)
    if url:
        try:
            kind=classify_source(url); source_count=max(1,min(10,int(request.form.get("source_count","3"))))
            if kind=="video":paths.append(download_youtube(url,jid))
            elif kind in {"channel","playlist"}:
                for i,e in enumerate(select_video_urls(list_youtube(url,source_count),source_count),1):paths.append(download_youtube(e["url"],jid,f"youtube_{i}"))
            else:raise RuntimeError("Unsupported source URL")
        except Exception as exc:return jsonify(error=f"YouTube source failed: {exc}"),400
    try:count=max(1,min(20,int(request.form.get("count","8"))))
    except ValueError:count=8
    opts={"template":request.form.get("template","tiktok"),"captions":request.form.get("captions","karaoke"),"visuals":request.form.get("visuals","on"),"upload":"off"}
    create_job(jid,user["id"]); EXECUTOR.submit(run_job,jid,user["id"],paths,count,opts); return jsonify(id=jid)

@app.get("/api/jobs")
def jobs():
    user=current_user()
    if not user:return jsonify(error="authentication required"),401
    rows=recent_jobs(user["id"])
    out=[]
    for row in rows:
        j=get_job(row["id"],user["id"]); clips=[]
        for c in j.get("clips",[]):
            c=dict(c); key=c.get("storage_key")
            if storage_mode()=="s3":c["url"]=presigned_get(key) if key else None
            else:c["url"]="/files/"+c.get("file","")
            clips.append(c)
        row["clips"]=clips; out.append(row)
    return jsonify(jobs=out)

@app.get("/api/jobs/<jid>")
def job(jid):
    user=current_user()
    if not user:return jsonify(error="authentication required"),401
    j=get_job(jid,user["id"])
    if not j:return jsonify(error="not found"),404
    return jsonify(j)

@app.get("/files/<path:name>")
def files(name):
    user=current_user()
    if not user:return jsonify(error="authentication required"),401
    safe=Path(name).name; return send_file(OUTPUT_DIR/safe,conditional=True)

if __name__=="__main__":
    from studio.persistence import init_db
    init_db(); app.run(host="0.0.0.0",port=int(os.getenv("PORT","8765")),debug=False)
