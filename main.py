import os
import json
import asyncio
import logging
from firebase_functions import https_fn
from firebase_admin import initialize_app
import httpx

from downloader import (
    extract_tiktok_url,
    extract_youtube_url,
    extract_any_supported_url,
    fetch_tiktok_media,
    fetch_youtube_media,
    download_file,
    cleanup_files,
    compress_video_if_needed,
)

# Initialize Firebase App
initialize_app()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def send_telegram_request(method: str, data: dict = None, files: dict = None):
    """Send request to Telegram Bot API."""
    url = f"{TELEGRAM_API_URL}/{method}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        if files:
            res = await client.post(url, data=data, files=files)
        else:
            res = await client.post(url, json=data)
        return res.json()

async def process_telegram_update(update: dict):
    """Process incoming Telegram update payload."""
    message = update.get("message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return

    # Handle /start command
    if text.startswith("/start"):
        welcome_text = (
            "👋 **សូមស្វាគមន៍មកកាន់ TikTok & YouTube Downloader Bot!**\n\n"
            "ខ្ញុំអាចជួយអ្នកទាញយក៖\n"
            "🎬 **TikTok & YouTube Videos** — គ្មាន Watermark\n"
            "📱 **YouTube Shorts** — ល្បឿនលឿន 4K/HD\n"
            "🖼️ **Photo Slide Posts**\n"
            "🎵 **បទចម្រៀង MP3 Audio**\n\n"
            "✨ **របៀបប្រើប្រាស់៖**\n"
            "1. ចម្លង (Copy) លីង TikTok ឬ YouTube\n"
            "2. ផ្ញើ (Paste & Send) លីងនោះមកកាន់ Bot នេះ\n"
            "3. រង់ចាំបន្តិច Bot នឹងផ្ញើជូនអ្នកភ្លាមៗ! 🚀"
        )
        await send_telegram_request("sendMessage", {
            "chat_id": chat_id,
            "text": welcome_text,
            "parse_mode": "Markdown"
        })
        return

    # Extract TikTok or YouTube URL
    extracted = extract_any_supported_url(text)
    if not extracted:
        return

    url, platform = extracted
    platform_name = "YouTube" if platform == "youtube" else "TikTok"

    # Send status message
    status_res = await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": f"🔍 *កំពុងដំណើរការលីង {platform_name}...*",
        "parse_mode": "Markdown"
    })
    status_msg_id = status_res.get("result", {}).get("message_id")

    temp_files = []
    try:
        if platform == "youtube":
            media_info = await fetch_youtube_media(url)
        else:
            media_info = await fetch_tiktok_media(url)
        if media_info.get("status") != "success":
            err_msg = media_info.get("error", "Failed to fetch media.")
            if status_msg_id:
                await send_telegram_request("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": status_msg_id,
                    "text": f"❌ {err_msg}"
                })
            return

        author = media_info.get("author", "")
        caption = f"👤 @{author}  •  🤖 @ratanaban_bot" if author else "🤖 @ratanaban_bot"

        media_type = media_info.get("type")

        # VIDEO POST
        if media_type == "video":
            video_url = media_info.get("video_url")
            video_path = await download_file(video_url, suffix=".mp4")
            temp_files.append(video_path)

            file_size_bytes = video_path.stat().st_size
            file_size_mb = file_size_bytes / (1024 * 1024)

            if file_size_mb > 50.0:
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": f"⏬ ទាញយកវីដេអូផ្ទាល់ ({file_size_mb:.1f} MB)", "url": video_url}]
                    ]
                }
                if status_msg_id:
                    await send_telegram_request("editMessageText", {
                        "chat_id": chat_id,
                        "message_id": status_msg_id,
                        "text": (
                            f"⚠️ **វីដេអូមានទំហំធំ ({file_size_mb:.1f} MB)**\n\n"
                            f"Telegram មិនអនុញ្ញាតឱ្យ Bot ផ្ញើឯកសារធំជាង **50 MB** ដោយផ្ទាល់ក្នុង Chat ទេ។\n\n"
                            f"👇 **សូមចុចប៊ូតុងខាងក្រោមដើម្បីទាញយកវីដេអូ 4K ដើមភ្លាមៗ៖**"
                        ),
                        "parse_mode": "Markdown",
                        "reply_markup": reply_markup
                    })
                return

            with open(video_path, "rb") as vf:
                await send_telegram_request("sendVideo", data={
                    "chat_id": chat_id,
                }, files={"video": vf})

            if status_msg_id:
                await send_telegram_request("deleteMessage", {
                    "chat_id": chat_id,
                    "message_id": status_msg_id
                })

        # PHOTO SLIDESHOW POST
        elif media_type == "images":
            image_urls = media_info.get("image_urls", [])
            audio_url = media_info.get("audio_url")

            downloaded_images = []
            for img_url in image_urls:
                img_path = await download_file(img_url, suffix=".jpg")
                downloaded_images.append(img_path)
                temp_files.append(img_path)

            # Send photo album (up to 10 photos)
            files_dict = {}
            media_list = []
            for idx, path in enumerate(downloaded_images[:10]):
                attach_name = f"photo_{idx}"
                media_item = {"type": "photo", "media": f"attach://{attach_name}"}
                media_list.append(media_item)
                files_dict[attach_name] = (path.name, open(path, "rb"), "image/jpeg")

            async with httpx.AsyncClient(timeout=60.0) as client:
                await client.post(
                    f"{TELEGRAM_API_URL}/sendMediaGroup",
                    data={"chat_id": chat_id, "media": json.dumps(media_list)},
                    files=files_dict
                )

            # Close open file handles
            for f in files_dict.values():
                f[1].close()

            # Send Audio if available
            if audio_url:
                try:
                    audio_path = await download_file(audio_url, suffix=".mp3")
                    temp_files.append(audio_path)
                    with open(audio_path, "rb") as af:
                        await send_telegram_request("sendAudio", data={
                            "chat_id": chat_id,
                            "title": title[:40] if title else "TikTok Audio",
                            "performer": author or "TikTok"
                        }, files={"audio": af})
                except Exception as ae:
                    logger.warning(f"Audio send error: {ae}")

            if status_msg_id:
                await send_telegram_request("deleteMessage", {
                    "chat_id": chat_id,
                    "message_id": status_msg_id
                })

    except Exception as e:
        logger.error(f"Error handling update: {e}", exc_info=True)
        if status_msg_id:
            await send_telegram_request("editMessageText", {
                "chat_id": chat_id,
                "message_id": status_msg_id,
                "text": "❌ An error occurred processing your request."
            })
    finally:
        cleanup_files(temp_files)

@https_fn.on_request()
def telegram_webhook(req: https_fn.Request) -> https_fn.Response:
    """Firebase Cloud Function HTTP Webhook Entrypoint."""
    if req.method != "POST":
        return https_fn.Response("OK", status_code=200)

    try:
        update = req.get_json(silent=True)
        if update:
            asyncio.run(process_telegram_update(update))
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")

    return https_fn.Response("OK", status_code=200)
