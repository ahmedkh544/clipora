"""Local-first video editing intelligence."""
import re
from typing import Dict, List, Tuple, Optional

HOOK_WORDS=set("secret mistake truth nobody never always why how learned lesson problem warning important surprising actually cost changed discovered goal system secret trick biggest easiest fastest before after avoid stop".split())

def score_segment(text: str) -> float:
    words=re.findall(r"[A-Za-zÀ-ÿ0-9']+", text.lower())
    if not words: return 0.0
    unique=len(set(words))/len(words); hook=sum(1 for w in words if w in HOOK_WORDS)
    question=text.count("?"); exclaim=text.count("!")
    return min(100.0,35*min(unique,1)+12*min(hook,4)+9*min(question,2)+6*min(exclaim,3)+min(len(words)/4,30))

def choose_scene_aware_boundary(desired: float, scene_boundaries: List[float], minimum: float, maximum: float) -> float:
    """Choose a visual scene boundary, preferring one just after the desired end."""
    valid=sorted(float(x) for x in scene_boundaries if minimum <= float(x) <= maximum)
    if not valid: return desired
    after=[x for x in valid if x >= desired]
    return min(after,key=lambda x:x-desired) if after else max(valid)

def detect_visual_scene_boundaries(video_path: str, sample_fps: float=2.0, threshold: float=0.45, min_gap: float=2.0) -> List[float]:
    """Detect shot boundaries with PySceneDetect, with the previous OpenCV detector as fallback."""
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector
        video=open_video(video_path)
        fps=float(video.frame_rate or 25.0)
        manager=SceneManager()
        manager.add_detector(ContentDetector(threshold=27.0, min_scene_len=max(1,int(round(fps*min_gap)))))
        manager.detect_scenes(video=video, show_progress=False)
        scenes=manager.get_scene_list()
        return [round(scene[1].get_seconds(),3) for scene in scenes[:-1]]
    except Exception:
        pass
    try: import cv2
    except ImportError: return []
    cap=cv2.VideoCapture(video_path)
    if not cap.isOpened(): return []
    fps=float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 25.0
    step=max(1,int(round(fps/max(0.1,sample_fps))))
    boundaries=[]; previous=None; last=-999.0; frame_index=0
    while True:
        ok,frame=cap.read()
        if not ok: break
        if frame_index % step:
            frame_index+=1; continue
        small=cv2.resize(frame,(160,90)); hsv=cv2.cvtColor(small,cv2.COLOR_BGR2HSV)
        hist=cv2.calcHist([hsv],[0,1],None,[24,16],[0,180,0,256]); cv2.normalize(hist,hist)
        if previous is not None:
            distance=1.0-float(cv2.compareHist(previous,hist,cv2.HISTCMP_CORREL)); timestamp=frame_index/fps
            if distance >= threshold and timestamp-last >= min_gap:
                boundaries.append(round(timestamp,3)); last=timestamp
        previous=hist; frame_index+=1
    cap.release(); return boundaries

def _build_windows(segs: List[Dict]) -> List[Dict]:
    windows=[]; current=None
    for s in segs:
        start=float(s.get("start",0)); end=float(s.get("end",0)); text=str(s.get("text","")).strip()
        if end<=start or not text: continue
        if current is None: current={"start":start,"end":end,"texts":[text]}; continue
        if start-current["end"]<=1.5 and end-current["start"]<=45:
            current["end"]=end; current["texts"].append(text)
        else: windows.append(current); current={"start":start,"end":end,"texts":[text]}
    if current: windows.append(current)
    return windows

def select_narrative_sequence(transcript: Dict, count: int=5, target_duration: Optional[float]=55.0, scene_boundaries: Optional[List[float]]=None, total_duration: Optional[float]=None) -> List[Dict]:
    """Split the full story into chronological, adjacent episodes covering its entire speech timeline."""
    segs=[s for s in transcript.get("segments",[]) if float(s.get("end",0))>float(s.get("start",0)) and str(s.get("text","")).strip()]
    if not segs or count <= 0: return []
    total_end=float(total_duration) if total_duration is not None else float(segs[-1].get("end",0)); clips=[]; cursor=0.0 if total_duration is not None else float(segs[0].get("start",0))
    scene_boundaries=scene_boundaries or []
    for part in range(1,count+1):
        if cursor >= total_end-0.25: break
        remaining_parts=count-part+1
        remaining_duration=max(0.0,total_end-cursor)
        target=target_duration if target_duration is not None else remaining_duration/remaining_parts
        desired_end=min(total_end,cursor+target)
        if remaining_parts == 1: desired_end=total_end
        if total_duration is not None:
            min_duration=max(0.5,min(15.0,target*0.35,remaining_duration/remaining_parts*0.5))
        else:
            min_duration=max(5.0,min(15.0,target*0.5))
        search_radius=8.0 if total_duration is not None else max(30.0,target*0.35)
        search_min=max(cursor+min_duration,desired_end-search_radius) if total_duration is not None else cursor+min_duration
        search_max=min(total_end,desired_end+search_radius)
        if total_duration is not None and remaining_parts > 1:
            # Reserve an equal share for every remaining part so a scene boundary can never consume them.
            reserved=remaining_duration/remaining_parts
            search_max=min(search_max,total_end-reserved*(remaining_parts-1))
        candidates=[s for s in segs if float(s.get("end",0))>=search_min and float(s.get("end",0))<=search_max]
        if total_duration is not None and candidates:
            # Full-video mode keeps exact 0..total_duration coverage, but chooses each
            # internal boundary from speech structure instead of a blind time split.
            scored=[]
            for s in candidates:
                e=float(s.get("end",0)); text=str(s.get("text","")).strip()
                punctuation=8.0 if text.endswith((".","!","?","؟","؛","。","！")) else 0.0
                next_start=next((float(n.get("start",e)) for n in segs if float(n.get("start",0))>=e-0.001 and float(n.get("start",0))>e),e)
                pause=min(3.0,max(0.0,next_start-e))
                pause_bonus=pause*3.0
                visual_bonus=12.0 if any(abs(e-x)<=1.5 for x in scene_boundaries) else 0.0
                scored.append((punctuation+pause_bonus+visual_bonus-abs(e-desired_end),e))
            boundary=max(scored)[1]
        elif total_duration is not None:
            # No usable transcript boundary: preserve the exact partition.
            boundary=desired_end
        elif candidates:
            scored=[]
            for i,s in enumerate(candidates):
                e=float(s.get("end",0)); text=str(s.get("text","")).strip(); words=text.lower().split(); last_word=words[-1].strip(".,!?") if words else ""
                if last_word in ("because","which","that","and","but","so","while","although","when","where","as"): continue
                punctuation=1 if text.endswith((".","!","?")) else 0; pause=0.0
                if i > 0:
                    previous_end=float(candidates[i-1].get("end",e)); candidate_start=float(s.get("start",e)); pause=min(3.0,max(0.0,candidate_start-previous_end))
                natural_bonus=punctuation*4.0+pause*3.0; visual_bonus=12.0 if any(abs(e-x)<=1.5 for x in scene_boundaries) else 0.0
                scored.append((natural_bonus+visual_bonus-abs(e-desired_end),e))
            boundary=max(scored)[1] if scored else desired_end
        else: boundary=desired_end
        boundary=max(cursor+min_duration,min(boundary,total_end)); text=" ".join(str(s.get("text","")).strip() for s in segs if float(s.get("end",0))>cursor and float(s.get("start",0))<boundary).strip()
        clips.append({"title":f"Part {part} — {text[:70]}","start_time":round(cursor,3),"end_time":round(boundary,3),"score":100-part,"hook_sentence":text[:220],"virality_reason":"Sequential narrative segment; follows story order and uses speech, pauses and visual scene boundaries."})
        cursor=boundary
    return clips

def select_highlights(transcript: Dict, count: int=5) -> List[Dict]:
    windows=_build_windows(transcript.get("segments",[])); candidates=[]
    for i,w in enumerate(windows):
        text=" ".join(w["texts"]).strip(); duration=w["end"]-w["start"]
        if duration<8: continue
        candidates.append((score_segment(text),i,w["start"],w["end"],text))
    candidates.sort(reverse=True); chosen=[]
    for score,i,start,end,text in candidates:
        if any(max(start,x["start_time"])<min(end,x["end_time"]) for x in chosen): continue
        clip_end=min(end+35,start+60); clip_start=max(0,start-1.0)
        chosen.append({"title":text[:80],"start_time":clip_start,"end_time":clip_end,"score":round(score),"hook_sentence":text[:220],"virality_reason":"Local hook score using curiosity, problem/benefit language, questions and speech density."})
        if len(chosen)>=count: break
    return sorted(chosen,key=lambda x:x["score"],reverse=True)

def build_keep_ranges(transcript: Dict, start: float, end: float, min_gap: float=0.7) -> List[Tuple[float,float]]:
    parts=[]
    for s in transcript.get("segments",[]):
        a=max(start,float(s.get("start",0))); b=min(end,float(s.get("end",0)))
        if b>a and str(s.get("text","")).strip(): parts.append((a,b))
    parts.sort(); out=[]
    for a,b in parts:
        if not out or a-out[-1][1]>min_gap: out.append((a,b))
        else: out[-1]=(out[-1][0],max(out[-1][1],b))
    return out

def map_time(t: float, ranges: List[Tuple[float,float]]) -> float:
    total=0.0
    for a,b in ranges:
        if t<=a: return total
        if t<=b: return total+(t-a)
        total += b-a
    return total

def word_timings(text: str, start: float, end: float):
    words=text.split(); duration=max(0.05,end-start); total=max(1,sum(len(w) for w in words)); cur=start
    for w in words:
        d=duration*len(w)/total; yield w,cur,min(end,cur+d); cur+=d
