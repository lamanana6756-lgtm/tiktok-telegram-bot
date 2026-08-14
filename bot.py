import os
import sys
import logging
from pathlib import Path
from telegram import Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from config import BOT_TOKEN
from downloader import (
    extract_tiktok_url,
    fetch_tiktok_media,
    download_file,
    cleanup_files,
    compress_video_if_needed,
)

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

AUDIO_CACHE = {}
PDF_CACHE = {}
LAST_KEYBOARD_MSG = {}

async def clear_previous_keyboard(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Remove inline keyboard from the previous message in this chat to keep feed clean."""
    prev_msg_id = LAST_KEYBOARD_MSG.get(chat_id)
    if prev_msg_id:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=prev_msg_id,
                reply_markup=None
            )
        except Exception as e:
            logger.debug(f"Could not clear previous keyboard for chat {chat_id}: {e}")

def create_media_keyboard(url: str, media_info: dict = None, direct_url: str = None, file_size_mb: float = None):
    """Create a sleek dual-column inline keyboard layout with MP3 button and quick actions."""
    keyboard = []
    
    if direct_url:
        label = f"⏬ ទាញយកផ្ទាល់ ({file_size_mb:.1f} MB)" if file_size_mb else "⏬ ទាញយក Direct Link"
        keyboard.append([
            InlineKeyboardButton(label, url=direct_url)
        ])

    row_actions = []
    if media_info:
        audio_url = media_info.get("audio_url")
        if audio_url:
            import uuid
            short_id = uuid.uuid4().hex[:10]
            AUDIO_CACHE[short_id] = {
                "audio_url": audio_url,
                "title": media_info.get("title", ""),
                "author": media_info.get("author", ""),
            }
            row_actions.append(InlineKeyboardButton("🎵 ទាញយក MP3", callback_data=f"dlmp3:{short_id}"))

        image_urls = media_info.get("image_urls", [])
        if image_urls:
            import uuid
            pdf_id = uuid.uuid4().hex[:10]
            PDF_CACHE[pdf_id] = {
                "image_urls": image_urls,
                "title": media_info.get("title", ""),
            }
            row_actions.append(InlineKeyboardButton("📄 ទាញយកជា PDF", callback_data=f"dlpdf:{pdf_id}"))

    row_actions.append(InlineKeyboardButton("🔗 TikTok ដើម", url=url))
    keyboard.append(row_actions)

    keyboard.append([
        InlineKeyboardButton("📢 ចែករំលែក Bot", url="https://t.me/share/url?url=https://t.me/ratanaban_bot&text=Bot%20ទាញយក%20TikTok%20ល្បឿនលឿន!"),
        InlineKeyboardButton("⚡ ព័ត៌មាន Bot", callback_data="help_info")
    ])
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with professional card UI."""
    welcome_text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ **TIKTOK DOWNLOADER BOT v2.0** ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🟢 **ប្រព័ន្ធដំណើការ៖** 24/7 Online Cloud\n\n"
        "👋 **សូមស្វាគមន៍មកកាន់ប្រព័ន្ធទាញយក TikTok!**\n\n"
        "**លក្ខណៈពិសេស៖**\n"
        " 🎬 **HD Video** — ទាញយកគ្មាន Watermark\n"
        " 🖼️ **Photo Slides** — ទាញយករូបភាពជាអាល់ប៊ុម\n"
        " 🎵 **MP3 Audio** — រក្សាទុកបទចម្រៀង Original\n\n"
        "📌 **របៀបប្រើប្រាស់៖**\n"
        "1️⃣ ចម្លង (Copy) លីងពី TikTok\n"
        "2️⃣ ផ្ញើ (Paste & Send) លីងចូលក្នុង Chat នេះ\n"
        "3️⃣ រង់ចាំបន្តិច Bot នឹងទាញយកជូនភ្លាមៗ! 🚀\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💬 ផ្ញើ `/help` សម្រាប់ជំនួយ | `/about` ព័ត៌មាន Bot"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📖 ការណែនាំ (Help)", callback_data="help_info"),
            InlineKeyboardButton("📢 ចែករំលែក (Share)", url="https://t.me/share/url?url=https://t.me/ratanaban_bot"),
        ]
    ]
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command with styled guidance card."""
    help_text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📖 **ការណែនាំ & លីងដែលគាំទ្រ**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔗 **ទម្រង់ Link ដែលអាចប្រើបាន៖**\n"
        " ▫️ `https://www.tiktok.com/@user/video/...`\n"
        " ▫️ `https://vt.tiktok.com/xxxxxx/`\n"
        " ▫️ `https://vm.tiktok.com/xxxxxx/`\n"
        " ▫️ TikTok Photo Slideshow posts\n\n"
        "⚡ **ល្បឿនទាញយក៖** 1-3 វិនាទី (High Speed)\n"
        "🛡️ **សុវត្ថិភាព៖** គ្មាន விளம்பர / គ្មាន Ads\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "ផ្ញើលីង TikTok របស់អ្នកមកទីនេះដើម្បីចាប់ផ្តើម!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command."""
    about_text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "ℹ️ **អំពី TIKTOK DOWNLOADER BOT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🤖 **Bot Name:** @ratanaban_bot\n"
        "⚡ **Engine:** Python Async v2.0\n"
        "🌐 **Server:** 24/7 Cloud Engine\n"
        "🛡️ **Status:** Operational 100%\n\n"
        "❤️ **អរគុណសម្រាប់ការប្រើប្រាស់!**"
    )
    await update.message.reply_text(about_text, parse_mode="Markdown")

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callback queries."""
    query = update.callback_query
    data = query.data or ""
    
    if data == "help_info":
        await query.answer()
        await help_command(update, context)
        return

    if data.startswith("dlmp3:"):
        short_id = data.split(":", 1)[1]
        cache_item = AUDIO_CACHE.get(short_id)
        if not cache_item:
            await query.answer("❌ សំឡេងនេះផុតកំណត់ហើយ។ សូមផ្ញើលីងម្តងទៀត។", show_alert=True)
            return

        await query.answer("🎵 កំពុងរៀបចំទាញយក MP3...")
        status_msg = await query.message.reply_text("⏬ *កំពុងទាញយកបទចម្រៀង MP3...*", parse_mode="Markdown")
        temp_files = []
        try:
            audio_url = cache_item["audio_url"]
            title = cache_item.get("title", "")
            author = cache_item.get("author", "")
            audio_path = await download_file(audio_url, suffix=".mp3")
            temp_files.append(audio_path)
            
            with open(audio_path, "rb") as af:
                await query.message.reply_audio(
                    audio=af,
                    title=f"{title[:40]} (Audio)" if title else "TikTok Audio",
                    performer=author or "TikTok",
                    caption=None
                )
            await status_msg.delete()
        except Exception as e:
            logger.error(f"Error serving MP3 callback: {e}")
            await status_msg.edit_text("❌ មិនអាចទាញយកបទចម្រៀងបានទេ។")
        finally:
            cleanup_files(temp_files)

    if data.startswith("dlpdf:"):
        pdf_id = data.split(":", 1)[1]
        cache_item = PDF_CACHE.get(pdf_id)
        if not cache_item:
            await query.answer("❌ ឯកសារនេះផុតកំណត់ហើយ។ សូមផ្ញើលីងម្តងទៀត។", show_alert=True)
            return

        await query.answer("📄 កំពុងបង្កើតឯកសារ PDF...")
        status_msg = await query.message.reply_text(
            "📄 *កំពុងបម្លែងរូបភាពទៅជាឯកសារ PDF Document...*\n`[ ▓▓▓▓▓▓░░░░ ] 65% | Compiling Study Slides 📄`",
            parse_mode="Markdown"
        )
        temp_files = []
        try:
            import uuid
            from PIL import Image
            image_urls = cache_item.get("image_urls", [])
            title = cache_item.get("title", "TikTok Study Slides")

            downloaded_images: list[Path] = []
            for img_url in image_urls:
                try:
                    img_p = await download_file(img_url, suffix=".jpg")
                    if img_p.exists() and img_p.stat().st_size > 500:
                        downloaded_images.append(img_p)
                        temp_files.append(img_p)
                except Exception as e:
                    logger.warning(f"Could not download image slide for PDF: {e}")

            if not downloaded_images:
                await status_msg.edit_text("❌ មិនមានរូបភាពសម្រាប់បង្កើត PDF ទេ។")
                return

            # Compile images into PDF using PIL
            pil_images = []
            for p in downloaded_images:
                try:
                    img = Image.open(p)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    pil_images.append(img)
                except Exception as img_err:
                    logger.warning(f"Failed to load PIL image {p}: {img_err}")

            if not pil_images:
                await status_msg.edit_text("❌ បរាជ័យក្នុងការបម្លែងរូបភាព។")
                return

            pdf_path = downloaded_images[0].parent / f"notes_{uuid.uuid4().hex[:8]}.pdf"
            temp_files.append(pdf_path)

            pil_images[0].save(
                pdf_path,
                save_all=True,
                append_images=pil_images[1:],
                format="PDF"
            )

            await status_msg.edit_text("📤 *កំពុងផ្ញើឯកសារ PDF ជូន...*", parse_mode="Markdown")
            filename = "TikTok_Study_Notes.pdf"

            with open(pdf_path, "rb") as pf:
                await query.message.reply_document(
                    document=pf,
                    filename=filename,
                    caption=f"📄 **ឯកសារ PDF សិក្សា (TikTok Study Slides)**\n\n"
                            f"📚 *បម្លែងចេញពីរូបភាព {len(pil_images)} ទំព័រ*",
                    parse_mode="Markdown"
                )
            await status_msg.delete()
        except Exception as pdf_err:
            logger.error(f"Error serving PDF callback: {pdf_err}", exc_info=True)
            await status_msg.edit_text("❌ បរាជ័យក្នុងការបង្កើតឯកសារ PDF។")
        finally:
            cleanup_files(temp_files)

async def post_init(application: Application):
    """Set native Telegram bot command menu."""
    from telegram import BotCommand
    commands = [
        BotCommand("start", "🚀 ចាប់ផ្តើមប្រើប្រាស់ (Start)"),
        BotCommand("help", "📖 ការណែនាំអំពីការប្រើប្រាស់ (Help)"),
        BotCommand("about", "ℹ️ ព័ត៌មានអំពី Bot (About)"),
    ]
    await application.bot.set_my_commands(commands)

async def handle_tiktok_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process user messages containing TikTok links."""
    text = update.message.text or ""
    url = extract_tiktok_url(text)
    if not url:
        return

    status_msg = await update.message.reply_text(
        "⚡ *កំពុងវិភាគលីង TikTok...*\n`[ ▓▓░░░░░░░░ ] 25% | Engine Analyzing 🔍`",
        parse_mode="Markdown"
    )
    temp_files: list[Path] = []

    try:
        media_info = await fetch_tiktok_media(url)

        if media_info.get("status") != "success":
            error_text = media_info.get("error", "មិនអាចទាញយកបានទេ! សូមពិនិត្យមើលលីងរបស់អ្នកឡើងវិញ។")
            await status_msg.edit_text(f"❌ {error_text}")
            return

        chat_id = update.effective_chat.id
        title = media_info.get("title", "")
        author = media_info.get("author", "")
        media_type = media_info.get("type")

        # -----------------------------------------------------------
        # VIDEO POST
        # -----------------------------------------------------------
        if media_type == "video":
            video_url = media_info.get("video_url")
            if not video_url:
                await status_msg.edit_text("❌ មិនអាចស្វែងរកវីដេអូបានទេ។")
                return

            await status_msg.edit_text(
                "⏬ *កំពុងទាញយកវីដេអូ FHD 1080p (គ្មាន Watermark)...*\n`[ ▓▓▓▓▓▓░░░░ ] 65% | High Speed CDN 🚀`",
                parse_mode="Markdown"
            )
            
            try:
                video_path = await download_file(video_url, suffix=".mp4")
                temp_files.append(video_path)

                file_size_bytes = video_path.stat().st_size
                file_size_mb = file_size_bytes / (1024 * 1024)

                # If video exceeds Telegram's 50MB bot upload limit, immediately provide direct download button
                if file_size_mb > 50.0:
                    logger.info(f"Video size ({file_size_mb:.1f} MB) > 50MB limit. Providing instant direct download button.")
                    large_file_keyboard = create_media_keyboard(url, media_info, direct_url=video_url, file_size_mb=file_size_mb)
                    
                    await clear_previous_keyboard(context, chat_id)
                    await status_msg.edit_text(
                        f"⚠️ **វីដេអូមានទំហំធំ ({file_size_mb:.1f} MB)**\n\n"
                        f"Telegram មិនអនុញ្ញាតឱ្យ Bot ផ្ញើឯកសារធំជាង **50 MB** ដោយផ្ទាល់ក្នុង Chat ទេ។\n\n"
                        f"👇 **សូមចុចប៊ូតុងខាងក្រោមដើម្បីទាញយកវីដេអូ 4K ដើមភ្លាមៗ៖**",
                        parse_mode="Markdown",
                        reply_markup=large_file_keyboard
                    )
                    LAST_KEYBOARD_MSG[chat_id] = status_msg.message_id
                    return

                await status_msg.edit_text(
                    "📤 *កំពុងផ្ញើវីដេអូជូន...*\n`[ ▓▓▓▓▓▓▓▓▓▓ ] 99% | Finalizing Delivery ✨`",
                    parse_mode="Markdown"
                )
                await clear_previous_keyboard(context, chat_id)
                with open(video_path, "rb") as video_file:
                    video_msg = await update.message.reply_video(
                        video=video_file,
                        caption=None,
                        supports_streaming=True,
                        reply_markup=create_media_keyboard(url, media_info),
                    )
                    if video_msg:
                        LAST_KEYBOARD_MSG[chat_id] = video_msg.message_id

                await status_msg.delete()
                await update.message.reply_text(
                    "✅ **ទាញយកបានជោគជ័យ!**\n\n"
                    "🔗 សូមផ្ញើ (Paste & Send) លីង TikTok ថ្មីមួយទៀតដើម្បីទាញយកបន្ត! 🚀",
                    parse_mode="Markdown"
                )
            except Exception as dl_err:
                logger.warning(f"Local video download failed ({dl_err}). Attempting direct Telegram URL delivery...")
                try:
                    await clear_previous_keyboard(context, chat_id)
                    video_msg = await update.message.reply_video(
                        video=video_url,
                        caption=None,
                        supports_streaming=True,
                        reply_markup=create_media_keyboard(url, media_info),
                    )
                    if video_msg:
                        LAST_KEYBOARD_MSG[chat_id] = video_msg.message_id
                    await status_msg.delete()
                except Exception as tg_err:
                    logger.error(f"Direct Telegram video URL delivery failed: {tg_err}")
                    direct_kb = create_media_keyboard(url, media_info, direct_url=video_url)
                    await clear_previous_keyboard(context, chat_id)
                    card_msg = await status_msg.edit_text(
                        "🎬 **វីដេអូ TikTok គ្មាន Watermark**\n\n"
                        "👇 **សូមចុចប៊ូតុងខាងក្រោមដើម្បីទាញយក ឬមើលវីដេអូភ្លាមៗ៖**",
                        parse_mode="Markdown",
                        reply_markup=direct_kb
                    )
                    LAST_KEYBOARD_MSG[chat_id] = card_msg.message_id

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
                f"⏬ *កំពុងទាញយក {len(image_urls)} រូបភាព HD...*\n`[ ▓▓▓▓▓▓░░░░ ] 65% | High Speed CDN 🚀`",
                parse_mode="Markdown"
            )

            # Download all images
            downloaded_images: list[Path] = []
            for img_url in image_urls:
                try:
                    img_path = await download_file(img_url, suffix=".jpg")
                    if img_path.exists() and img_path.stat().st_size > 500:
                        downloaded_images.append(img_path)
                        temp_files.append(img_path)
                except Exception as e:
                    logger.warning(f"Could not download image slide {img_url}: {e}")

            await status_msg.edit_text(
                "📤 *កំពុងផ្ញើរូបភាពជូន...*\n`[ ▓▓▓▓▓▓▓▓▓▓ ] 99% | Finalizing Delivery ✨`",
                parse_mode="Markdown"
            )

            # Telegram allows max 10 media items per media group call
            chunk_size = 10
            for i in range(0, len(downloaded_images), chunk_size):
                chunk = downloaded_images[i:i + chunk_size]
                media_group = []

                for idx, img_path in enumerate(chunk):
                    with open(img_path, "rb") as f:
                        media_group.append(
                            InputMediaPhoto(media=f.read(), caption=None)
                        )

                try:
                    await update.message.reply_media_group(media=media_group)
                except Exception as mg_err:
                    logger.warning(f"Media group sending failed ({mg_err}). Falling back to individual photo delivery...")
                    for img_path in chunk:
                        try:
                            with open(img_path, "rb") as f:
                                await update.message.reply_photo(photo=f, caption=None)
                        except Exception as p_err:
                            logger.warning(f"Failed to send individual photo {img_path}: {p_err}")

            # Send audio if present and update status_msg with interactive action buttons
            if audio_url:
                try:
                    await status_msg.edit_text("🎵 *កំពុងផ្ញើបទចម្រៀង MP3...*", parse_mode="Markdown")
                    audio_path = await download_file(audio_url, suffix=".mp3")
                    temp_files.append(audio_path)
                    await clear_previous_keyboard(context, chat_id)
                    with open(audio_path, "rb") as audio_file:
                        audio_msg = await update.message.reply_audio(
                            audio=audio_file,
                            title=f"{title[:40]} (Audio)" if title else "TikTok Audio",
                            performer=author or "TikTok",
                            caption=None,
                            reply_markup=create_media_keyboard(url, media_info),
                        )
                        if audio_msg:
                            LAST_KEYBOARD_MSG[chat_id] = audio_msg.message_id
                except Exception as audio_err:
                    logger.warning(f"Failed to send audio track: {audio_err}")

            await status_msg.delete()
            await update.message.reply_text(
                "✅ **ទាញយកបានជោគជ័យ!**\n\n"
                "🔗 សូមផ្ញើ (Paste & Send) លីង TikTok ថ្មីមួយទៀតដើម្បីទាញយកបន្ត! 🚀",
                parse_mode="Markdown"
            )

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

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Health check web server running on port {port}")

def main():
    """Start the bot."""
    if not BOT_TOKEN or BOT_TOKEN == "your_telegram_bot_token_here":
        print("\n" + "=" * 60)
        print("ERROR: TELEGRAM_BOT_TOKEN is not set in .env file!")
        print("Please set your bot token from @BotFather in the .env file.")
        print("Example:\nTELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        print("=" * 60 + "\n")
        sys.exit(1)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    # Start HTTP server on PORT for Render Web Service health checks
    start_health_server()

    print("[*] Starting TikTok Downloader Telegram Bot...")
    
    # Custom request timeout for uploading larger video files
    request = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=120.0,
        write_timeout=120.0,
    )
    app = Application.builder().token(BOT_TOKEN).request(request).post_init(post_init).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r'https?://'),
            handle_tiktok_link,
        )
    )

    print("[+] Bot is running! Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
