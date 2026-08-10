import os
import sys
import logging
from pathlib import Path
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from config import BOT_TOKEN
from downloader import (
    extract_tiktok_url,
    fetch_tiktok_media,
    download_file,
    cleanup_files,
)

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command in Khmer."""
    welcome_text = (
        "👋 **សូមស្វាគមន៍មកកាន់ TikTok Downloader Bot!**\n\n"
        "ខ្ញុំអាចជួយអ្នកទាញយក៖\n"
        "🎬 **វីដេអូ TikTok គ្មាន Watermark (អត់ជាប់ឡូហ្គោ)**\n"
        "🖼️ **រូបភាព Slide / Photo Posts**\n"
        "🎵 **បទចម្រៀង / សំឡេង Background**\n\n"
        "✨ **របៀបប្រកាត់ប្រើប្រាស់៖**\n"
        "1. ចម្លង (Copy) លីងវីដេអូ ឬរូបភាព TikTok\n"
        "2. ផ្ញើ (Paste & Send) លីងនោះមកកាន់ Bot នេះ\n"
        "3. រង់ចាំបន្តិច Bot នឹងផ្ញើជូនអ្នកភ្លាមៗ! 🚀\n\n"
        "ផ្ញើ `/help` ដើម្បីមើលការណែនាំបន្ថែម។"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command in Khmer."""
    help_text = (
        "📖 **ការណែនាំអំពីការប្រើប្រាស់**\n\n"
        "• **ទម្រង់លីងដែលគាំទ្រ៖**\n"
        "  - `https://www.tiktok.com/@user/video/123456789`\n"
        "  - `https://vt.tiktok.com/xxxxxx/`\n"
        "  - `https://vm.tiktok.com/xxxxxx/`\n\n"
        "• **លក្ខណៈពិសេស៖**\n"
        "  - 🎬 ទាញយកវីដេអូ HD គ្មាន Watermark\n"
        "  - 🖼️ ទាញយករូបភាព Slide ទាំងអស់ជាអាល់ប៊ុម\n"
        "  - 🎵 រក្សាទុកបទចម្រៀង Background\n\n"
        "ប្រសិនបើមានបញ្ហា សូមប្រាកដថាវីដេអូនោះជា Public!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def handle_tiktok_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process user messages containing TikTok links."""
    text = update.message.text or ""
    url = extract_tiktok_url(text)
    if not url:
        return

    status_msg = await update.message.reply_text(
        "🔍 *កំពុងដំណើរការលីង TikTok...*", parse_mode="Markdown"
    )
    temp_files: list[Path] = []

    try:
        media_info = await fetch_tiktok_media(url)

        if media_info.get("status") != "success":
            error_text = media_info.get("error", "មិនអាចទាញយកបានទេ! សូមពិនិត្យមើលលីងរបស់អ្នកឡើងវិញ។")
            await status_msg.edit_text(f"❌ {error_text}")
            return

        title = media_info.get("title", "")
        author = media_info.get("author", "")
        caption_lines = []
        if title:
            caption_lines.append(f"📌 {title}")
        if author:
            caption_lines.append(f"👤 @{author}")
        caption = "\n".join(caption_lines)
        if len(caption) > 1000:
            caption = caption[:997] + "..."

        media_type = media_info.get("type")

        # -----------------------------------------------------------
        # VIDEO POST
        # -----------------------------------------------------------
        if media_type == "video":
            video_url = media_info.get("video_url")
            if not video_url:
                await status_msg.edit_text("❌ មិនអាចស្វែងរកវីដេអូបានទេ។")
                return

            await status_msg.edit_text("⏬ *កំពុងទាញយកវីដេអូ (គ្មាន Watermark)...*", parse_mode="Markdown")
            video_path = await download_file(video_url, suffix=".mp4")
            temp_files.append(video_path)

            await status_msg.edit_text("📤 *កំពុងផ្ញើវីដេអូជូន...*", parse_mode="Markdown")
            with open(video_path, "rb") as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=caption,
                    supports_streaming=True,
                )
            await status_msg.delete()

        # -----------------------------------------------------------
        # PHOTO / SLIDESHOW POST
        # -----------------------------------------------------------
        elif media_type == "images":
            image_urls = media_info.get("image_urls", [])
            audio_url = media_info.get("audio_url")

            if not image_urls:
                await status_msg.edit_text("❌ មិនមានរូបភាពក្នុងប្រកាសនេះទេ។")
                return

            await status_msg.edit_text(
                f"⏬ *កំពុងទាញយក {len(image_urls)} រូបភាព...*", parse_mode="Markdown"
            )

            # Download all images
            downloaded_images: list[Path] = []
            for img_url in image_urls:
                img_path = await download_file(img_url, suffix=".jpg")
                downloaded_images.append(img_path)
                temp_files.append(img_path)

            await status_msg.edit_text("📤 *កំពុងផ្ញើរូបភាពជូន...*", parse_mode="Markdown")

            # Telegram allows max 10 media items per media group call
            chunk_size = 10
            for i in range(0, len(downloaded_images), chunk_size):
                chunk = downloaded_images[i:i + chunk_size]
                media_group = []

                for idx, img_path in enumerate(chunk):
                    item_caption = caption if (i == 0 and idx == 0) else None
                    with open(img_path, "rb") as f:
                        media_group.append(
                            InputMediaPhoto(media=f.read(), caption=item_caption)
                        )

                await update.message.reply_media_group(media=media_group)

            # If background audio is present, download & send audio
            if audio_url:
                try:
                    await status_msg.edit_text("🎵 *កំពុងផ្ញើបទចម្រៀង...*", parse_mode="Markdown")
                    audio_path = await download_file(audio_url, suffix=".mp3")
                    temp_files.append(audio_path)
                    with open(audio_path, "rb") as audio_file:
                        await update.message.reply_audio(
                            audio=audio_file,
                            title=f"{title[:40]} (Audio)" if title else "TikTok Audio",
                            performer=author or "TikTok",
                        )
                except Exception as audio_err:
                    logger.warning(f"Failed to send audio track: {audio_err}")

            await status_msg.delete()

        else:
            await status_msg.edit_text("❌ ទម្រង់ប្រព័ន្ធផ្សព្វផ្សាយមិនស្គាល់។")

    except Exception as e:
        logger.error(f"Error handling TikTok link {url}: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ មានបញ្ហាក្នុងការទាញយក។ សូមព្យាយាមម្តងទៀត។"
        )

    finally:
        # Clean up temporary files from disk
        cleanup_files(temp_files)

def main():
    """Start the bot."""
    if not BOT_TOKEN or BOT_TOKEN == "your_telegram_bot_token_here":
        print("\n" + "=" * 60)
        print("ERROR: TELEGRAM_BOT_TOKEN is not set in .env file!")
        print("Please set your bot token from @BotFather in the .env file.")
        print("Example:\nTELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        print("=" * 60 + "\n")
        sys.exit(1)

    print("🚀 Starting TikTok Downloader Telegram Bot...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r'https?://'),
            handle_tiktok_link,
        )
    )

    print("✅ Bot is running! Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
