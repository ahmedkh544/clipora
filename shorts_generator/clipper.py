"""Per-clip cropping via MuAPI /autocrop."""
from . import muapi
from .downloader import _extract_video_url
def crop_clip(source_video_url,start_time,end_time,aspect_ratio="9:16"):
    payload={"video_url":source_video_url,"start_time":float(start_time),"end_time":float(end_time),"aspect_ratio":aspect_ratio}
    print(f"[clip] {start_time:.1f}s → {end_time:.1f}s @ {aspect_ratio}",flush=True)
    return _extract_video_url(muapi.run("autocrop",payload,label=f"autocrop({start_time:.0f}-{end_time:.0f})"))
def crop_highlights(source_video_url,highlights,aspect_ratio="9:16"):
    out=[]
    for i,h in enumerate(highlights,1):
        try: out.append({**h,"clip_url":crop_clip(source_video_url,h["start_time"],h["end_time"],aspect_ratio)})
        except Exception as e: out.append({**h,"clip_url":None,"error":str(e)})
    return out
