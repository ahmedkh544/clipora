"""Local-first video editing intelligence."""
import re
from typing import Dict, List, Tuple

HOOK_WORDS=set("secret mistake truth nobody never always why how learned lesson problem warning important surprising actually cost changed discovered goal system secret trick biggest easiest fastest before after avoid stop".split())

def score_segment(text: str) -> float:
    words=re.findall(r"[A-Za-zÀ-ÿ0-9']+", text.lower())
    if not words: return 0.0
    unique=len(set(words))/len(words)
    hook=sum(1 for w in words if w in HOOK_WORDS)
    question=text.count("?"); exclaim=text.count("!")
    return min(100.0,35*min(unique,1)+12*min(hook,4)+9*min(question,2)+6*min(exclaim,3)+min(len(words)/4,30))

def _build_windows(segs: List[Dict]) -> List[Dict]:
    windows=[]; current=None
    for s in segs:
        start=float(s.get("start",0)); end=float(s.get("end",0)); text=str(s.get("text","")).strip()
        if end<=start or not text: continue
        if current is None:
            current={"start":start,"end":end,"texts":[text]}; continue
        if start-current["end"]<=1.5 and end-current["start"]<=45:
            current["end"]=end; current["texts"].append(text)
        else:
            windows.append(current); current={"start":start,"end":end,"texts":[text]}
    if current: windows.append(current)
    return windows

def select_narrative_sequence(transcript: Dict, count: int=5, target_duration: float=55.0) -> List[Dict]:
    """Split the story from the first speech segment into chronological, adjacent episodes."""
    segs=[s for s in transcript.get("segments",[]) if float(s.get("end",0))>float(s.get("start",0)) and str(s.get("text","")).strip()]
    if not segs or count <= 0: return []
    total_end=float(segs[-1].get("end",0)); clips=[]; cursor=float(segs[0].get("start",0))
    min_duration=max(5.0,min(15.0,target_duration*0.5))
    for part in range(1,count+1):
        if cursor >= total_end-0.25: break
        remaining_parts=count-part+1
        desired_end=min(total_end,cursor+target_duration)
        if remaining_parts == 1: desired_end=total_end
        candidates=[s for s in segs if float(s.get("end",0))>cursor+min_duration and float(s.get("end",0))<=min(total_end,cursor+max(70.0,target_duration*1.35))]
        if candidates:
            scored=[]
            for s in candidates:
                e=float(s.get("end",0)); text=str(s.get("text","")).strip()
                punctuation=1 if text.endswith((".", "!", "?", "؟", "。")) else 0
                scored.append((punctuation,-abs(e-desired_end),e))
            boundary=max(scored)[2]
        else: boundary=desired_end
        boundary=max(cursor+min_duration,min(boundary,total_end))
        text=" ".join(str(s.get("text","")).strip() for s in segs if float(s.get("end",0))>cursor and float(s.get("start",0))<boundary).strip()
        clips.append({"title":f"Part {part} — {text[:70]}","start_time":round(cursor,3),"end_time":round(boundary,3),"score":100-part,"hook_sentence":text[:220],"virality_reason":"Sequential narrative segment; follows the original story order and starts immediately after the previous part."})
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
