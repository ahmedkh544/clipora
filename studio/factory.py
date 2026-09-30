"""Local-first automation helpers for the VideoForge factory."""
import re
from urllib.parse import urlparse
from typing import Dict, List


def classify_source(url: str) -> str:
    host=urlparse(url).netloc.lower()
    path=urlparse(url).path.lower()
    query=urlparse(url).query.lower()
    if "playlist?list=" in url.lower() or ("list=" in query and "watch" not in path):
        return "playlist"
    if "/@" in path or "/channel/" in path or "/c/" in path or "/user/" in path:
        return "channel"
    if "youtube.com" in host or "youtu.be" in host:
        return "video"
    return "unknown"


def select_video_urls(entries: List[Dict], limit: int) -> List[Dict]:
    limit=max(1,int(limit))
    return [e for e in entries if e.get("url")][:limit]


def _hashtags(text: str) -> List[str]:
    words=re.findall(r"[A-Za-zÀ-ÿ0-9]+", text.lower())
    tags=["#Shorts","#YouTubeShorts"]
    for w in words:
        if len(w)>=5 and w not in {"about","there","which","their","this","that"}:
            tag="#"+w
            if tag not in tags: tags.append(tag)
        if len(tags)>=6: break
    return tags

def make_metadata(hook: str, template: str="youtube") -> Dict:
    clean=re.sub(r"\s+"," ",hook).strip(" .!?")
    if not clean:
        clean="The moment you need to hear"
    title=clean[:88].rstrip()
    title=f"{title} #Shorts"
    description=(f"{clean}.\n\n"
                 "Edited automatically with VideoForge.\n"
                 "#Shorts #YouTubeShorts")
    return {
        "title": title[:100],
        "description": description,
        "hashtags": _hashtags(clean),
        "privacy_status": "private",
        "template": template,
    }


def build_listing_command(url: str, limit: int) -> List[str]:
    limit=max(1,min(50,int(limit)))
    return ["yt-dlp","--flat-playlist","--dump-single-json","--playlist-end",str(limit),url]


def normalize_entries(payload: Dict) -> List[Dict]:
    if payload.get("entries"):
        out=[]
        for e in payload["entries"]:
            if not e: continue
            u=e.get("webpage_url") or e.get("url")
            if u: out.append({"url":u,"title":e.get("title","")})
        return out
    u=payload.get("webpage_url") or payload.get("original_url")
    return [{"url":u,"title":payload.get("title","")}] if u else []
