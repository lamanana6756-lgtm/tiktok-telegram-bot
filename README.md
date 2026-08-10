# 🤖 TikTok Video & Photo Downloader Telegram Bot

A fast, async Python Telegram bot to download **TikTok videos (without watermark)** and **TikTok photo posts (slideshows)** with background music.

---

## ✨ Features

- 🎬 **No-Watermark Video Download**: Downloads high-definition MP4 videos directly.
- 🖼️ **Photo / Slideshow Post Support**: Extracts all images from photo posts and sends them as a clean Telegram album.
- 🎵 **Audio Extraction**: Automatically sends background music for photo slideshows.
- ⚡ **Asynchronous & Fast**: Powered by `python-telegram-bot` and `httpx`.
- 🔥 **Firebase Serverless Ready**: Deploy to Firebase Cloud Functions for 100% free serverless hosting.

---

## 🔥 How to Deploy to Firebase Cloud Functions (100% Free)

Firebase Cloud Functions provides 2,000,000 free invocations per month, making it a great free choice for hosting your Telegram Bot using Webhooks!

### Step 1: Install Firebase Tools CLI
Make sure Node.js is installed, then run:
```bash
npm install -g firebase-tools
```

### Step 2: Login to Firebase & Initialize Project
```bash
firebase login
firebase init functions
```
- Select your Firebase Project.
- Select **Python** as the language.

### Step 3: Deploy to Firebase
Deploy your HTTP webhook function:
```bash
firebase deploy --only functions
```

After deployment finishes, Firebase CLI will output your Function URL:
`https://us-central1-your-project-id.cloudfunctions.net/telegram_webhook`

### Step 4: Register Webhook with Telegram
Tell Telegram to route all bot messages directly to your Firebase Function:

Open your web browser or run this command in terminal (replace `YOUR_BOT_TOKEN` and your Firebase URL):
```text
https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=https://us-central1-your-project-id.cloudfunctions.net/telegram_webhook
```

You will see: `{"ok":true,"result":true,"description":"Webhook was set"}`.
🎉 Your bot is now running on Firebase 24/7 for free!

---

## 🌐 Other Online Deployment Options (Render / Railway / VPS)

### Option A: Render.com (Background Worker)
1. Push code to GitHub repository.
2. Create **Background Worker** on [Render.com](https://render.com).
3. Set Start Command: `python bot.py`.
4. Add environment variable `TELEGRAM_BOT_TOKEN`.

### Option B: Railway.app
1. Connect GitHub repository to [Railway.app](https://railway.app).
2. Set `TELEGRAM_BOT_TOKEN` in Variables tab.

---

## 📁 Project Files

```text
bottelegram/
├── main.py          # Firebase Cloud Functions entrypoint (Webhook mode)
├── bot.py           # Long-polling entrypoint for local / Render / VPS
├── downloader.py    # TikTok media extractor
├── config.py        # Environment configuration
├── firebase.json    # Firebase Cloud Functions setup
├── requirements.txt # Python package dependencies
├── Dockerfile       # Container setup
├── Procfile         # Platform deployment configuration
└── README.md        # Documentation
```
