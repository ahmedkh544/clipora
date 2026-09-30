"""Transcription via MuAPI /openai-whisper."""
import json
from . import muapi
def _coerce_verbose(raw):
    if isinstance(raw,str):
        try:return json.loads(raw)
        except (TypeError,ValueError):return {}
    return raw if isinstance(raw,dict) else {}
def _extract_verbose_payload(result):
    for key in ("output","result","outputs"):
        v=result.get(key)
        if isinstance(v,dict) and "segments" in v:return v
        if isinstance(v,list) and v:
            decoded=_coerce_verbose(v[0])
            if "segments" in decoded:return decoded
        if isinstance(v,str):
            decoded=_coerce_verbose(v)
            if "segments" in decoded:return decoded
    if "segments" in result:return result
    raise RuntimeError(f"Could not find Whisper segments in MuAPI response: {result}")
def transcribe(media_url,language=None):
    print(f"[transcribe] muapi /openai-whisper on {media_url}",flush=True)
    payload={"audio_url":media_url,"response_format":"verbose_json"}
    if language:payload["language"]=language
    verbose=_extract_verbose_payload(muapi.run("openai-whisper",payload,label="openai-whisper"))
    segments=[{"start":float(s.get("start",0.0)),"end":float(s.get("end",0.0)),"text":(s.get("text") or "").strip()} for s in verbose.get("segments") or []]
    duration=float(verbose.get("duration") or (segments[-1]["end"] if segments else 0.0))
    print(f"[transcribe] {len(segments)} segments, {duration:.0f}s of audio",flush=True)
    return {"duration":duration,"segments":segments}
