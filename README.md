# 🤖 Discord Gemini Server Builder Bot

A Discord bot that uses **Google Gemini AI** to automatically generate and set up an entire Discord server structure (roles, categories, channels) from a simple text description.

## ✨ Features

- Type `!setup <description>` and the bot builds your whole server
- AI-powered via Gemini `gemini-2.0-flash`
- Creates roles with custom colors and hoisting
- Creates categories and text/voice channels
- Skips anything that already exists (safe to re-run)
- Sends a confirmation embed when done

## 🚀 Usage

```
!setup make a gaming server with channels for clips, chat, and roles for admin mod member
```

Only users with **Manage Server** permission can use this command.

## 🛠️ Setup

### Local

1. Clone the repo
2. Copy `.env.example` to `.env` and fill in your keys
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run:
   ```bash
   python bot.py
   ```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DISCORD_TOKEN` | Your Discord bot token |
| `GEMINI_API_KEY` | Your Google Gemini API key |

## ☁️ Deploy to Railway (24/7)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select this repo
4. Add environment variables in Railway dashboard
5. Done — bot runs forever!

## 📋 Requirements

- Python 3.10+
- `discord.py`
- `google-generativeai`
- `python-dotenv`
