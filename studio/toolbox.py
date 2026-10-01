from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


def detect_with_transnetv2(video_path: str, threshold: float = 0.3) -> List[float]:
    """Optional TransNetV2 shot detection; returns [] when the optional package is absent."""
    try:
        from transnetv2_pytorch import TransNetV2
    except ImportError:
        return []
    try:
        model=TransNetV2(device="auto")
        scenes=model.predict(video_path, threshold=threshold)
        return sorted(round(float(end),3) for _,end in scenes[:-1])
    except Exception:
        return []


def refine_boundary_with_waveform(video_path: str, desired: float, window: float = 1.5) -> float:
    """Move a cut toward a nearby low-energy audio point using FFmpeg PCM output."""
    if shutil.which("ffmpeg") is None: return desired
    start=max(0.0,desired-window); duration=max(0.1,window*2)
    cmd=["ffmpeg","-v","error","-ss",str(start),"-t",str(duration),"-i",video_path,"-ac","1","-ar","8000","-f","s16le","pipe:1"]
    try: raw=subprocess.check_output(cmd,stderr=subprocess.DEVNULL)
    except Exception: return desired
    if not raw: return desired
    import array, math
    samples=array.array("h"); samples.frombytes(raw)
    step=80; best=(float("inf"),desired)
    for i in range(0,max(1,len(samples)-step),step):
        rms=math.sqrt(sum(x*x for x in samples[i:i+step])/max(1,step))
        t=start+i/8000
        if abs(t-desired)<=window and rms<best[0]: best=(rms,t)
    return round(best[1],3)


def refine_narrative_boundaries(video_path: str, clips: List[dict]) -> List[dict]:
    """Refine adjacent narrative cuts while preserving exact chronology."""
    out=[]
    for i,clip in enumerate(clips):
        item=dict(clip)
        if i < len(clips)-1:
            item["end_time"]=max(item["start_time"],refine_boundary_with_waveform(video_path,item["end_time"]))
        out.append(item)
    for i in range(1,len(out)):
        out[i]["start_time"]=out[i-1]["end_time"]
    return out


def run_external_adapter(command: List[str], timeout: int = 900) -> Tuple[bool,str]:
    """Run an installed open-source CLI without making it a hard dependency."""
    try:
        p=subprocess.run(command,capture_output=True,text=True,timeout=timeout,check=False)
        return p.returncode==0,(p.stdout or p.stderr).strip()
    except (OSError,subprocess.TimeoutExpired) as exc:
        return False,str(exc)


def frameshift_available() -> bool:
    return shutil.which("frameshift") is not None

def run_frameshift(input_path: str, output_path: str, ratio: str = "9:16") -> Tuple[bool,str]:
    if not frameshift_available(): return False,"FrameShift is not installed"
    return run_external_adapter(["frameshift",input_path,output_path,"--ratio",ratio])


def autocaption_available() -> bool:
    return shutil.which("autocaption") is not None

def run_autocaption(input_path: str, output_path: str) -> Tuple[bool,str]:
    if not autocaption_available(): return False,"auto-caption is not installed"
    return run_external_adapter(["autocaption",input_path,"-o",output_path,"--language","auto"])


def videoclipper_available() -> bool:
    return shutil.which("videoclipper") is not None


def autoai_available() -> bool:
    return Path("vendor/AutoAI").exists()


def smart_reframe_available() -> bool:
    return Path("vendor/smart-video-reframe").exists()


def broll_search_available() -> bool:
    return Path("vendor/broll-search").exists()

def video_conveyor_available() -> bool:
    return Path("vendor/video-conveyor").exists()

def openshorts_available() -> bool:
    return Path("vendor/openshorts").exists()

def steezy_available() -> bool:
    return Path("vendor/steezy-clipper").exists()


def vertical_crop_x(video_path: str, width: int=720, height: int=1280) -> int:
    """Find a stable 9:16 crop center using sampled OpenCV face detection; center fallback."""
    try:
        import cv2
        cap=cv2.VideoCapture(video_path)
        if not cap.isOpened(): return 0
        vw=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0); vh=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if vw<=0 or vh<=0: return 0
        crop_w=min(vw,max(2,int(round(vh*width/height))))
        if crop_w>=vw:return 0
        cascade=cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
        centers=[]
        total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0); step=max(1,total//12) if total else 30
        i=0
        while True:
            ok,frame=cap.read()
            if not ok:break
            if i%step==0:
                gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY); faces=cascade.detectMultiScale(gray,1.1,5,minSize=(48,48))
                if len(faces):
                    x,y,w,h=max(faces,key=lambda f:f[2]*f[3]); centers.append(x+w/2)
            i+=1
            if i>step*12:break
        cap.release()
        center=sum(centers)/len(centers) if centers else vw/2
        return max(0,min(vw-crop_w,int(round(center-crop_w/2))))
    except Exception:
        return 0


def visual_filter(crop_x: int, source_width: int, source_height: int, width: int=720, height: int=1280, zoom_level: float=0.02) -> str:
    """Create a vertical crop plus a restrained zoom, avoiding aggressive auto-editing."""
    crop_w=min(source_width,max(2,int(round(source_height*width/height))))
    z=max(0.0,min(0.045,zoom_level))
    if z<=0: return f"crop={crop_w}:{source_height}:{crop_x}:0,scale={width}:{height}"
    zw=int(round(crop_w*(1+z))); zh=int(round(source_height*(1+z)))
    zx=max(0,int(round(crop_x-z*crop_w/2))); zy=max(0,int(round(-z*source_height/2)))
    return f"scale={zw}:{zh},crop={crop_w}:{source_height}:{zx}:{zy},scale={width}:{height}"
