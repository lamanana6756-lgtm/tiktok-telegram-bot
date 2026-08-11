import re
import uuid
import logging
from pathlib import Path
import httpx
import yt_dlp
from config import TEMP_DIR, USER_AGENT

logger = logging.getLogger(__name__)

# Regular expression to catch various TikTok link formats
TIKTOK_URL_REGEX = re.compile(
    r'https?://(?:www\.|v[mt]\.|t\.)?tiktok\.com/[@\w\d_.\-/]+',
    re.IGNORECASE
)

# Regular expression to catch various YouTube & Shorts link formats
YOUTUBE_URL_REGEX = re.compile(
    r'https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|shorts/|embed/|v/)|youtu\.be/)([\w\-]{11})',
    re.IGNORECASE
)

def extract_tiktok_url(text: str) -> str | None:
    """Extract the first TikTok URL found in text."""
    match = TIKTOK_URL_REGEX.search(text)
    if match:
        return match.group(0)
    return None

def extract_youtube_url(text: str) -> str | None:
    """Extract the first YouTube URL found in text."""
    match = YOUTUBE_URL_REGEX.search(text)
    if match:
        return match.group(0)
    return None

def extract_any_supported_url(text: str) -> tuple[str, str] | None:
    """Extract first TikTok or YouTube URL found in text. Returns (url, platform)."""
    yt_url = extract_youtube_url(text)
    if yt_url:
        return (yt_url, "youtube")
    tt_url = extract_tiktok_url(text)
    if tt_url:
        return (tt_url, "tiktok")
    return None

async def fetch_tiktok_media(url: str) -> dict:
    """
    Fetch TikTok media details using TikWM API, with yt-dlp fallback.
    
    Returns a dictionary structure:
    {
        "status": "success" | "error",
        "type": "video" | "images",
        "title": str,
        "author": str,
        "video_url": str (if video),
        "image_urls": list[str] (if images),
        "audio_url": str | None,
        "error": str (if error)
    }
    """
    try:
        api_res = await fetch_from_tikwm(url)
        if api_res and api_res.get("status") == "success":
            return api_res
    except Exception as e:
        logger.warning(f"TikWM API failed for {url}: {e}")

    # Fallback to yt-dlp if TikWM API fails
    try:
        return await fetch_from_ytdlp(url)
    except Exception as e:
        logger.error(f"yt-dlp fallback failed for {url}: {e}")
        return {
            "status": "error",
            "error": "Unable to fetch TikTok media. Please verify the link is valid and public."
        }

async def fetch_from_tikwm(url: str) -> dict | None:
    """Query multiple TikWM API endpoints with automatic failover for 365-day uptime."""
    api_endpoints = [
        "https://www.tikwm.com/api/",
        "https://api.tikwm.com/api/",
        "https://tikwm.com/api/",
        "https://v1.tikwm.com/api/",
    ]
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    params = {
        "url": url,
        "hd": 1
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for endpoint in api_endpoints:
            try:
                response = await client.get(endpoint, params=params, headers=headers)
                if response.status_code != 200:
                    continue

                res_json = response.json()
                if res_json.get("code") != 0 or "data" not in res_json:
                    continue

                data = res_json["data"]
                title = data.get("title", "TikTok Post")
                author = data.get("author", {}).get("nickname", "") or data.get("author", {}).get("unique_id", "")

                # Check if it contains images (Slideshow / Photo mode)
                images = data.get("images")
                if images and isinstance(images, list) and len(images) > 0:
                    return {
                        "status": "success",
                        "type": "images",
                        "title": title,
                        "author": author,
                        "image_urls": images,
                        "audio_url": data.get("music"),
                    }

                # Otherwise it's a video (Full HD hdplay prioritized)
                video_url = data.get("hdplay") or data.get("play") or data.get("wmplay")
                if video_url:
                    if video_url.startswith("//"):
                        video_url = "https:" + video_url
                    return {
                        "status": "success",
                        "type": "video",
                        "title": title,
                        "author": author,
                        "video_url": video_url,
                        "audio_url": data.get("music"),
                        "is_fhd": bool(data.get("hdplay")),
                    }
            except Exception as err:
                logger.warning(f"Self-healing failover: endpoint {endpoint} failed ({err}). Trying next endpoint...")
                continue

    return None

async def fetch_from_ytdlp(url: str) -> dict:
    """Fallback extraction using yt-dlp."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo+bestaudio/best",
        "user_agent": USER_AGENT,
    }

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    import asyncio
    info = await asyncio.to_thread(_extract)
    if not info:
        return {"status": "error", "error": "Could not extract media info."}

    title = info.get("title", "TikTok Post")
    author = info.get("uploader", "")
    direct_url = info.get("url")

    if not direct_url and "formats" in info:
        formats = info["formats"]
        if formats:
            direct_url = formats[-1].get("url")

    if direct_url:
        return {
            "status": "success",
            "type": "video",
            "title": title,
            "author": author,
            "video_url": direct_url,
            "audio_url": None,
            "is_fhd": True,
        }

    return {"status": "error", "error": "No downloadable media stream found."}

async def fetch_youtube_media(url: str) -> dict:
    """Fetch YouTube video or Shorts details using yt-dlp with mobile client emulation."""
    import asyncio
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "user_agent": USER_AGENT,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        }
    }

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.to_thread(_extract)
        if not info:
            return {"status": "error", "error": "Could not extract YouTube media info."}

        title = info.get("title", "YouTube Video")
        author = info.get("uploader") or info.get("channel") or ""

        direct_url = info.get("url")
        formats = info.get("formats", [])

        if not direct_url and formats:
            combined = [
                f for f in formats 
                if f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none")
            ]
            if combined:
                combined.sort(key=lambda x: x.get("height") or 0)
                direct_url = combined[-1].get("url")
            else:
                direct_url = formats[-1].get("url")

        audio_url = None
        if formats:
            audio_formats = [
                f for f in formats 
                if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")
            ]
            if audio_formats:
                audio_formats.sort(key=lambda x: x.get("abr") or 0)
                audio_url = audio_formats[-1].get("url")

        if direct_url:
            return {
                "status": "success",
                "type": "video",
                "platform": "youtube",
                "title": title,
                "author": author,
                "video_url": direct_url,
                "audio_url": audio_url or direct_url,
                "is_fhd": True,
            }

        return {"status": "error", "error": "No downloadable YouTube stream found."}
    except Exception as e:
        logger.error(f"YouTube extraction error for {url}: {e}")
        return {"status": "error", "error": "Unable to process YouTube link. Please verify the video is public."}

async def download_file(url: str, suffix: str = ".mp4", max_retries: int = 3) -> Path:
    """Download a remote file asynchronously with automatic retries and exponential backoff."""
    import asyncio
    filename = f"{uuid.uuid4().hex}{suffix}"
    file_path = TEMP_DIR / filename
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    response.raise_for_status()
                    with open(file_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
            return file_path
        except Exception as e:
            logger.warning(f"Download attempt {attempt}/{max_retries} failed for {url}: {e}")
            if attempt == max_retries:
                raise e
            await asyncio.sleep(attempt * 1.5)

    return file_path

def cleanup_files(file_paths: list[Path]):
    """Safely delete temporary files after sending to Telegram."""
    for path in file_paths:
        try:
            if path and path.exists():
                path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete temp file {path}: {e}")

async def compress_video_if_needed(file_path: Path, max_mb: float = 48.0) -> Path:
    """Compress video using ffmpeg ultrafast preset & 720p scaling if it exceeds max_mb."""
    import asyncio
    import subprocess

    if not file_path or not file_path.exists():
        return file_path

    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb <= max_mb:
        return file_path

    logger.info(f"Video size ({size_mb:.2f} MB) exceeds limit ({max_mb} MB). Compressing with ffmpeg ultrafast...")
    compressed_path = file_path.parent / f"compressed_{file_path.name}"

    def _run_ffmpeg():
        cmd = [
            "ffmpeg", "-y", "-i", str(file_path),
            "-vf", "scale=-2:720",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-threads", "2",
            "-c:a", "copy",
            str(compressed_path)
        ]
        return subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60
        )

    try:
        res = await asyncio.to_thread(_run_ffmpeg)
        if compressed_path.exists() and compressed_path.stat().st_size > 0:
            comp_mb = compressed_path.stat().st_size / (1024 * 1024)
            logger.info(f"Compression successful: {size_mb:.2f} MB -> {comp_mb:.2f} MB")
            return compressed_path
    except Exception as e:
        logger.error(f"FFmpeg video compression failed: {e}")

    return file_path
