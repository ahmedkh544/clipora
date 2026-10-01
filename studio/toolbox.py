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
