import json, os, re, subprocess, threading, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template_string, request, send_file, session
from studio.core import build_keep_ranges, detect_visual_scene_boundaries, select_narrative_sequence
from studio.persistence import can_create_job, cleanup_old_files, create_job, create_session, create_user, get_job, get_user_by_session, logout, recent_jobs, authenticate, update_job, set_plan
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

HTML="""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Clipora — Story-first AI video clipping</title><style>
:root{--bg:#070b12;--panel:#0d1420;--line:#243246;--text:#f7f9fc;--muted:#93a1b5;--a:#7c5cff;--b:#21d4fd;--good:#35d07f}*{box-sizing:border-box}body{margin:0;min-width:320px;background:radial-gradient(circle at 12% 0%,#7c5cff25,transparent 28rem),radial-gradient(circle at 90% 10%,#21d4fd18,transparent 24rem),var(--bg);color:var(--text);font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif}.shell{max-width:1240px;margin:auto;padding:22px 18px 50px}.nav{display:flex;justify-content:space-between;align-items:center;padding:5px 0 24px}.brand{display:flex;align-items:center;gap:11px;font-weight:850;font-size:19px}.mark{width:38px;height:38px;border-radius:12px;display:grid;place-items:center;background:linear-gradient(135deg,var(--a),var(--b));box-shadow:0 12px 30px #7c5cff40}.mark svg{width:21px}.nav-right{display:flex;gap:8px;align-items:center}.pill,.ghost{border:1px solid var(--line);background:#0d1522;color:#dce5f0;border-radius:999px;padding:8px 11px;font-size:12px}.ghost{border-radius:10px;cursor:pointer}.primary{border:0;border-radius:11px;padding:12px 15px;background:linear-gradient(135deg,var(--a),#5d7cff);color:white;font-weight:800;cursor:pointer;box-shadow:0 12px 30px #7c5cff35}.hero{display:grid;grid-template-columns:1.12fr .88fr;gap:30px;align-items:center;padding:32px 0 28px}.eyebrow{display:inline-flex;gap:8px;align-items:center;color:#d1caff;background:#7c5cff16;border:1px solid #7c5cff40;border-radius:999px;padding:7px 10px;font-size:11px;font-weight:800;text-transform:uppercase}.dot{width:7px;height:7px;border-radius:50%;background:var(--good)}h1{font-size:clamp(43px,6vw,76px);line-height:.98;letter-spacing:-.065em;margin:18px 0}.grad{background:linear-gradient(100deg,#fff,#b9afff,#75ddff);-webkit-background-clip:text;background-clip:text;color:transparent}.lead{max-width:680px;color:#aab6c8;font-size:18px;line-height:1.65}.hero-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:20px}.proof{display:flex;gap:15px;flex-wrap:wrap;color:#8290a4;font-size:11px;margin-top:17px}.hero-art{min-height:320px;position:relative}.art{position:absolute;border:1px solid var(--line);border-radius:22px;background:linear-gradient(145deg,#111b2bf5,#080e17f5);box-shadow:0 24px 70px #00000055}.art-main{inset:0 30px 0 0;padding:18px}.art-top{display:flex;justify-content:space-between;color:#aab6c8;font-size:12px}.wave{height:150px;margin-top:22px;border-radius:15px;background:#7c5cff10;overflow:hidden;position:relative}.wave:after{content:'';position:absolute;left:0;right:0;top:67px;height:25px;background:repeating-linear-gradient(90deg,transparent 0 8px,#8d7cff 9px 11px,transparent 12px 19px);transform:skewY(-7deg)}.segments{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:7px;margin-top:11px}.segments i{height:7px;border-radius:8px;background:#27364a}.segments i:nth-child(1){background:var(--a)}.segments i:nth-child(2){background:#a78bfa}.segments i:nth-child(3){background:#38bdf8}.segments i:nth-child(4){background:#34d399}.art-phone{right:-7px;bottom:-3px;width:130px;height:185px;padding:9px}.phone{height:100%;border-radius:14px;background:linear-gradient(160deg,#18223a,#060b12);border:1px solid #33425a;display:flex;align-items:flex-end;padding:9px}.caption{width:100%;padding:7px;border-radius:7px;background:#000b;text-align:center;font-size:9px;font-weight:800}.auth,.studio{border:1px solid var(--line);background:#0d1420df;border-radius:22px;box-shadow:0 24px 70px #00000038;backdrop-filter:blur(14px)}.auth{max-width:760px;margin:20px auto;padding:26px}.auth-grid{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin:16px 0}.field{display:block;color:#b9c5d5;font-size:11px;font-weight:750}.field input,.field select{width:100%;margin-top:6px;padding:11px 12px;border:1px solid #29384e;border-radius:11px;background:#090f19;color:white;outline:0}.field input:focus,.field select:focus{border-color:#7560ff;box-shadow:0 0 0 3px #7c5cff18}.auth-actions{display:flex;gap:8px}.auth-msg{min-height:18px;color:var(--muted);font-size:12px}.studio{padding:19px}.section-head{display:flex;justify-content:space-between;gap:15px;align-items:flex-start;margin-bottom:16px}.section-head h2{margin:0;font-size:23px;letter-spacing:-.035em}.section-head p{margin:6px 0 0;color:var(--muted);line-height:1.5;font-size:12px}.workspace{display:grid;grid-template-columns:1.14fr .86fr;gap:14px}.dropzone{min-height:220px;border:1px dashed #3b4e68;border-radius:19px;display:grid;place-items:center;text-align:center;padding:25px;background:radial-gradient(circle at 50% 20%,#7c5cff18,transparent 17rem),#09111d;cursor:pointer;transition:.2s}.dropzone.drag{border-color:#9b8cff;background:#0d1625;transform:translateY(-1px)}.dropzone input{display:none}.drop-icon{width:53px;height:53px;margin:auto;border-radius:16px;display:grid;place-items:center;color:#d9d4ff;background:#7c5cff16;border:1px solid #7c5cff42}.dropzone h3{margin:13px 0 5px;font-size:18px}.dropzone p{margin:0;color:#8390a3;font-size:12px}.selected{margin-top:10px;color:#cbd5e1;font-size:11px}.settings{border:1px solid var(--line);border-radius:18px;padding:16px;background:#0a111d}.settings h3{margin:0 0 12px;font-size:15px}.settings-grid{display:grid;gap:10px}.mode{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:6px}.mode label{border:1px solid #29384e;border-radius:10px;padding:9px;background:#0b1320;cursor:pointer}.mode input{display:none}.mode label:has(input:checked){border-color:#7662ff;background:#7c5cff16}.story-badge{margin-top:6px;border:1px solid #29485c;border-radius:10px;padding:9px;color:#bde9f5;background:#21d4fd0c}.advanced{border-top:1px solid var(--line);padding-top:10px;margin-top:2px}.advanced summary{cursor:pointer;color:#aeb9c9;font-size:11px;font-weight:750}.advanced-grid{display:grid;gap:9px;margin-top:10px}.submit{width:100%;margin-top:3px}.processing{display:none;margin-top:13px;border:1px solid var(--line);border-radius:18px;padding:15px;background:#0a111d}.processing.show{display:block}.progress-meta{display:flex;justify-content:space-between;font-size:11px;color:#aeb9c9}.bar{height:7px;background:#1c293a;border-radius:99px;overflow:hidden;margin:9px 0 13px}.fill{height:100%;width:0;background:linear-gradient(90deg,var(--a),var(--b));transition:width .3s}.processing-steps{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}.step{padding:8px 5px;border-radius:9px;background:#0e1724;border:1px solid #1d2b3e;color:#718096;font-size:9px;text-align:center}.step.active{color:white;border-color:#6555c9;background:#7c5cff14}.step.done{color:#9debc0;border-color:#1d6c4b}.jobs{margin-top:22px}.job{border:1px solid var(--line);border-radius:17px;padding:15px;background:#0a111d;margin-top:9px}.job-head{display:flex;justify-content:space-between;gap:10px;align-items:center}.job-title{font-weight:800}.status{font-size:10px;padding:5px 8px;border-radius:99px;background:#182438;color:#b9c6d8}.status.done{color:#91e5b7;background:#35d07f14}.status.error{color:#ff9aa6;background:#ff6b7a14}.clip{display:grid;grid-template-columns:145px 1fr;gap:15px;border-top:1px solid #1d2939;padding-top:14px;margin-top:14px}.clip video{width:145px;aspect-ratio:9/16;object-fit:cover;background:#000;border-radius:13px;border:1px solid #27364a}.clip h3{margin:2px 0 6px;font-size:15px}.clip p{margin:0;color:#8f9db0;font-size:11px;line-height:1.55}.clip-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.clip-actions a,.clip-actions button{width:auto;text-decoration:none;border:1px solid #2a3a51;background:#111b2a;color:#dbe5f2;border-radius:8px;padding:7px 9px;font-size:10px;font-weight:750;cursor:pointer}.empty{padding:32px;text-align:center;color:#718096;border:1px dashed #28384d;border-radius:14px}.empty strong{display:block;color:#b8c4d5;margin-bottom:4px}.footer{text-align:center;color:#647287;font-size:10px;padding:24px}@media(max-width:900px){.hero,.workspace{grid-template-columns:1fr}.hero-art{max-width:620px;width:100%;margin:auto;min-height:280px}.processing-steps{overflow:auto}.step{min-width:70px}}@media(max-width:650px){.shell{padding:15px 12px 35px}.hero{padding-top:18px}.hero-art{min-height:230px}.art-main{padding:13px}.art-phone{width:105px;height:150px}.wave{height:105px}.auth-grid{grid-template-columns:1fr}.auth-actions{flex-direction:column}.section-head{flex-direction:column}.studio{padding:13px}.dropzone{min-height:200px}.clip{grid-template-columns:100px 1fr;gap:10px}.clip video{width:100px}}@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
</style></head><body><div class='shell'>
<header class='nav'><div class='brand'><div class='mark' aria-hidden='true'><svg viewBox='0 0 24 24' fill='none'><path d='M8 5.8v12.4L18.2 12 8 5.8Z' fill='white'/></svg></div>Clipora</div><div class='nav-right'>{% if user %}<span class='pill'>{{user.plan|upper}} · {{user.email}}</span><button class='ghost' onclick='logout()' aria-label='Log out'>Log out</button>{% endif %}</div></header>
{% if not user %}<section class='hero'><div><span class='eyebrow'><i class='dot'></i> Story-first AI clipping</span><h1>Turn one long video into a <span class='grad'>connected story.</span></h1><p class='lead'>Clipora finds narrative boundaries, keeps the sequence intact, reframes to 9:16 and adds Arabic captions — so your Shorts feel like chapters, not random fragments.</p><div class='hero-actions'><a class='primary' href='#auth' style='text-decoration:none'>Create free account</a><a class='ghost' href='#how' style='text-decoration:none'>See how it works</a></div><div class='proof'><span>✓ Sequential story cutting</span><span>✓ Arabic captions</span><span>✓ 9:16 ready</span></div></div><div class='hero-art' aria-hidden='true'><div class='art art-main'><div class='art-top'><b>Story sequence</b><span>8 chapters</span></div><div class='wave'></div><div class='segments'><i></i><i></i><i></i><i></i></div></div><div class='art art-phone'><div class='phone'><div class='caption'>الفكرة تستمر من مقطع إلى آخر</div></div></div></div></section>
<section id='auth' class='auth'><h2 style='margin:0'>Start creating</h2><p style='color:#8290a4;font-size:12px;margin:5px 0 0'>Free workspace · create an account in seconds</p><div class='auth-grid'><label class='field'>Email<input id='email' type='email' autocomplete='email' placeholder='you@example.com'></label><label class='field'>Password<input id='password' type='password' autocomplete='current-password' placeholder='••••••••'></label></div><div class='auth-actions'><button class='primary' onclick='auth("register")'>Create free account</button><button class='ghost' onclick='auth("login")'>Sign in</button></div><p id='authmsg' class='auth-msg' aria-live='polite'></p></section>
<section id='how' class='studio' style='margin-top:16px'><div class='section-head'><div><h2>From long-form to story-ready Shorts</h2><p>Upload once. Clipora handles narrative order, vertical framing and Arabic captions.</p></div></div></section>
{% else %}<section class='studio'><div class='section-head'><div><h2>Create a connected story</h2><p>Start with a long video. Clipora keeps the selected Shorts in narrative order.</p></div><span class='pill'>{{user.plan|upper}} plan</span></div>
<div class='workspace'><div><form id='f'><div id='dropzone' class='dropzone' role='button' tabindex='0' aria-label='Upload video files'><div><div class='drop-icon' aria-hidden='true'><svg width='25' height='25' viewBox='0 0 24 24' fill='none'><path d='M12 16V4m0 0-4 4m4-4 4 4M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/></svg></div><h3>Drop your long video here</h3><p>or click to browse · MP4, MOV and common video formats</p><div id='selected' class='selected'>No file selected</div></div><input id='videos' type='file' name='videos' accept='video/*' multiple></div><div style='margin-top:10px'><label class='field'>Or paste a YouTube URL<input name='url' type='url' placeholder='https://youtube.com/watch?v=…'></label></div>
<div class='settings' style='margin-top:11px'><h3>Story settings</h3><div class='settings-grid'><label class='field'>Shorts in this story<input name='count' type='number' min='1' max='20' value='8'></label><div class='field'>Output platform<div class='mode'><label><input type='radio' name='template' value='tiktok' checked><span>TikTok</span></label><label><input type='radio' name='template' value='reels'><span>Instagram Reels</span></label></div></div><div class='field'>Story mode<div id='storyMode' class='story-badge'>✓ Sequential narrative · 9:16</div></div><details class='advanced'><summary>Caption & visual controls</summary><div class='advanced-grid'><label class='field'>Captions<select name='captions'><option value='karaoke'>Arabic word highlight</option><option value='plain'>Arabic line captions</option><option value='off'>Off</option></select></label><label class='field'>Visual framing<select name='visuals'><option value='on'>Smart 9:16 + subtle motion</option><option value='off'>Center crop</option></select></label><label class='field'>YouTube sources<input name='source_count' type='number' min='1' max='10' value='3'></label></div></details><button class='primary submit' type='submit'>Generate connected Shorts →</button></div></div></form>
<div id='processing' class='processing' aria-live='polite'><div class='progress-meta'><b id='status'>Preparing your story…</b><span id='pct'>0%</span></div><div class='bar'><div id='fill' class='fill'></div></div><div id='processingSteps' class='processing-steps'><div class='step'>Transcribe</div><div class='step'>Find story</div><div class='step'>Boundaries</div><div class='step'>Reframe 9:16</div><div class='step'>Render captions</div></div></div></div>
<aside class='settings'><h3>What you get</h3><div class='settings-grid'><div class='pill'>01 · Complete thoughts</div><div class='pill'>02 · Sequential chapters</div><div class='pill'>03 · Arabic captions</div><div class='pill'>04 · Vertical framing</div></div><p style='color:#7f8ca0;font-size:11px;line-height:1.6;margin-top:14px'>The product is designed around continuity: each chapter follows the previous one instead of producing unrelated highlights.</p></aside></div>
<div class='jobs'><div class='section-head' style='margin-top:22px'><div><h2>Your stories</h2><p>Review chapters and download individual clips.</p></div></div><div id='jobs'><div class='empty'><strong>No stories yet</strong>Your generated clips will appear here.</div></div></div></section>{% endif %}<div class='footer'>Clipora · Story-first AI video repurposing</div></div>
<script>
const $=id=>document.getElementById(id);
async function auth(mode){const body={email:$.call(null,'email').value,password:$.call(null,'password').value};const x=await fetch('/api/auth/'+mode,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await x.json();if(!x.ok){$('authmsg').textContent=j.error||'Please check your details.';return}location.reload()}
async function logout(){await fetch('/api/auth/logout',{method:'POST'});location.reload()}
const f=$('f'),dz=$('dropzone'),fi=$('videos');
function showFiles(){const n=[...fi.files].length;$('selected').textContent=n?n+' video'+(n>1?'s':'')+' selected':'No file selected'}
if(dz&&fi){dz.onclick=e=>{if(e.target!==fi)fi.click()};dz.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();fi.click()}};['dragenter','dragover'].forEach(v=>dz.addEventListener(v,e=>{e.preventDefault();dz.classList.add('drag')}));['dragleave','drop'].forEach(v=>dz.addEventListener(v,e=>{e.preventDefault();dz.classList.remove('drag')}));dz.addEventListener('drop',e=>{if(e.dataTransfer.files.length){fi.files=e.dataTransfer.files;showFiles()}});fi.onchange=showFiles}
function setProgress(n,msg){$('fill').style.width=n+'%';$('pct').textContent=n+'%';$('status').textContent=msg;const active=n<15?1:n<35?2:n<55?3:n<85?4:5;document.querySelectorAll('#processingSteps .step').forEach((el,i)=>{el.classList.toggle('active',i+1===active);el.classList.toggle('done',i+1<active)})}
if(f)f.onsubmit=async e=>{e.preventDefault();$('processing').classList.add('show');setProgress(2,'Uploading your source…');const x=await fetch('/api/jobs',{method:'POST',body:new FormData(f)});const j=await x.json();if(!x.ok){setProgress(0,j.error||'Upload failed');return}poll(j.id)}
async function poll(id){const x=await fetch('/api/jobs/'+id),j=await x.json();setProgress(j.progress||0,j.message||j.status);if(j.status==='done'||j.status==='error'){loadJobs();return}setTimeout(()=>poll(id),900)}
async function loadJobs(){const x=await fetch('/api/jobs'),j=await x.json();$('jobs').innerHTML=j.jobs.map(job=>{let h='<div class="job"><div class="job-head"><div><div class="job-title">Story '+job.id.slice(0,8)+'</div><div style="color:#718096;font-size:10px">'+escapeHtml(job.message||'')+'</div></div><span class="status '+job.status+'">'+escapeHtml(job.status)+'</span></div>';if(job.status==='done'&&job.clips){h+=job.clips.map((c,i)=>'<div class="clip"><video controls playsinline preload="metadata" src="'+c.url+'"></video><div><h3>Chapter '+(i+1)+' · '+escapeHtml(c.title)+'</h3><p>'+escapeHtml(c.reason||'')+'</p><div class="clip-actions"><a href="'+c.url+'" download>Download clip</a><button data-url="'+c.url+'" onclick="copyLink(this)">Copy link</button></div></div></div>').join('')}if(job.error)h+='<p style="color:#ff9aa6">'+escapeHtml(job.error)+'</p>';return h+'</div>'}).join('')||'<div class="empty"><strong>No stories yet</strong>Your generated clips will appear here.</div>'}
async function copyLink(b){try{await navigator.clipboard.writeText(b.dataset.url);b.textContent='Copied';setTimeout(()=>b.textContent='Copy link',1100)}catch(e){alert(b.dataset.url)}}
function escapeHtml(x){return String(x).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
if($('jobs')){loadJobs();setInterval(loadJobs,5000)}
</script></body></html>"""

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

@app.post("/api/billing/checkout")
def billing_checkout():
    user=current_user()
    if not user:return jsonify(error="authentication required"),401
    if user["plan"]=="pro":return jsonify(error="Already on Pro"),400
    secret=os.getenv("STRIPE_SECRET_KEY"); price=os.getenv("STRIPE_PRO_PRICE_ID")
    if not secret or not price:return jsonify(error="Stripe billing is not configured yet"),503
    try:
        import stripe
        stripe.api_key=secret
        base=request.url_root.rstrip("/")
        checkout=stripe.checkout.Session.create(mode="subscription",customer_email=user["email"],client_reference_id=user["id"],subscription_data={"metadata":{"user_id":user["id"]}},line_items=[{"price":price,"quantity":1}],success_url=base+"/?billing=success",cancel_url=base+"/?billing=cancel")
        return jsonify(url=checkout.url)
    except Exception as exc:return jsonify(error=str(exc)),502

@app.post("/api/billing/webhook")
def billing_webhook():
    secret=os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:return jsonify(error="Stripe webhook is not configured"),503
    try:
        import stripe
        event=stripe.Webhook.construct_event(request.data,request.headers.get("Stripe-Signature",""),secret)
        obj=event["data"]["object"]; kind=event["type"]
        if kind=="checkout.session.completed":
            uid=obj.get("client_reference_id") or (obj.get("metadata") or {}).get("user_id")
            if uid:set_plan(uid,"pro")
        elif kind in {"customer.subscription.created","customer.subscription.updated"}:
            uid=(obj.get("metadata") or {}).get("user_id")
            if uid:set_plan(uid,"pro" if obj.get("status") in {"active","trialing"} else "free")
        elif kind=="customer.subscription.deleted":
            uid=(obj.get("metadata") or {}).get("user_id")
            if uid:set_plan(uid,"free")
        return jsonify(received=True)
    except Exception as exc:return jsonify(error=str(exc)),400

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
