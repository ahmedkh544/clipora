import os
from dotenv import load_dotenv
load_dotenv()
MUAPI_API_KEY=os.getenv("MUAPI_API_KEY","").strip()
MUAPI_BASE_URL=os.getenv("MUAPI_BASE_URL","https://api.muapi.ai/api/v1").rstrip("/")
POLL_INTERVAL_SECONDS=float(os.getenv("MUAPI_POLL_INTERVAL","5"))
POLL_TIMEOUT_SECONDS=float(os.getenv("MUAPI_POLL_TIMEOUT","600"))
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY","").strip()
OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-4o-mini")
GEMINI_API_KEY=os.getenv("GEMINI_API_KEY","").strip()
GEMINI_MODEL=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
LLM_PROVIDER=os.getenv("LLM_PROVIDER","openai").strip().lower()
LOCAL_WHISPER_MODEL=os.getenv("LOCAL_WHISPER_MODEL","tiny")
LOCAL_WHISPER_DEVICE=os.getenv("LOCAL_WHISPER_DEVICE","auto")
LOCAL_OUTPUT_DIR=os.getenv("LOCAL_OUTPUT_DIR","output")
LOCAL_WHISPER_VAD_FILTER=os.getenv("LOCAL_WHISPER_VAD_FILTER","false").strip().lower()=="true"
_vad_params_env=os.getenv("LOCAL_WHISPER_VAD_PARAMETERS","")
if _vad_params_env:
    import json
    LOCAL_WHISPER_VAD_PARAMETERS=json.loads(_vad_params_env)
else:
    LOCAL_WHISPER_VAD_PARAMETERS={"threshold":0.5,"min_speech_duration_ms":250,"max_speech_duration_s":float("inf"),"min_silence_duration_ms":2000,"speech_pad_ms":400}
def require_api_key():
    if not MUAPI_API_KEY: raise RuntimeError("MUAPI_API_KEY is not set. Add it to your .env file or export it as an env var.")
    return MUAPI_API_KEY
def require_openai_key():
    if not OPENAI_API_KEY: raise RuntimeError("OPENAI_API_KEY is not set. Local mode needs an OpenAI key for highlight ranking.")
    return OPENAI_API_KEY
def require_gemini_key():
    if not GEMINI_API_KEY: raise RuntimeError("GEMINI_API_KEY is not set. Local mode needs a Gemini key when LLM_PROVIDER=gemini.")
    return GEMINI_API_KEY
