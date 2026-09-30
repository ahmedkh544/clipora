"""Optional YouTube uploader using the official YouTube Data API."""
from pathlib import Path
from typing import Dict

def build_video_body(meta: Dict, privacy: str="private") -> Dict:
    tags=[str(x).lstrip("#") for x in meta.get("hashtags",[]) if str(x).strip()]
    return {"snippet":{"title":str(meta.get("title","Short #Shorts"))[:100],"description":str(meta.get("description","")),"tags":tags[:15],"categoryId":"22"},"status":{"privacyStatus":privacy}}

def upload_video(path: str, meta: Dict, root: Path, privacy: str="private") -> str:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.auth.transport.requests import Request
    import pickle
    scopes=["https://www.googleapis.com/auth/youtube.upload"]; token=root/"youtube_token.pickle"; secrets=root/"client_secrets.json"; creds=None
    if token.exists():
        with token.open("rb") as f: creds=pickle.load(f)
    if creds and creds.expired and creds.refresh_token: creds.refresh(Request())
    if not creds or not creds.valid:
        if not secrets.exists(): raise FileNotFoundError("client_secrets.json is required for YouTube upload")
        flow=InstalledAppFlow.from_client_secrets_file(str(secrets),scopes); creds=flow.run_local_server(port=0)
        with token.open("wb") as f: pickle.dump(creds,f)
    youtube=build("youtube","v3",credentials=creds); body=build_video_body(meta,privacy); media=MediaFileUpload(path,mimetype="video/mp4",resumable=True)
    return youtube.videos().insert(part="snippet,status",body=body,media_body=media).execute()["id"]

def youtube_upload_ready(root: Path) -> bool:
    return (root/"client_secrets.json").exists()
