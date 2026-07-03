# 🤖 Discord Gemini Server Builder Bot

A Discord bot that uses **Google Gemini AI** to automatically generate and set up an entire Discord server structure (roles, categories, channels) from a simple text description.

## ✨ Features

- **Interactive Setup Preview (`!setup <description>`)**: AI generates a complete server layout preview embed with **Confirm (✅)** and **Cancel (❌)** buttons before creating any channels.
- **AI-Powered via Gemini 2.0 (`gemini-2.0-flash`)**: Automatically structures roles, categories, and channels.
- **Emoji & Formatting Support**: Generates aesthetic channel names with fitting emojis (e.g., `📣-announcements`, `🎮-lfg`).
- **Private Channels & Permission Overrides**: Can create restricted categories or channels (e.g., staff-only rooms restricted to `Admin` or `Moderator` roles).
- **Safe & Reversible (`!teardown`)**: Tracks AI-created resources so you can easily reset or delete generated roles and channels with `!teardown` or `!cleanup`.
- **Built-in Help Command (`!help`)**: View available commands and usage instructions inside Discord.

## 🚀 Usage

### 1. Preview & Build Server Structure
```
!setup community gaming server with esports news, lfg, voice lounges, and private staff channels
```
*Review the generated layout in Discord, then click **Confirm & Build**.*

### 2. Teardown / Reset AI-Created Channels
```
!teardown
```
*Asks for confirmation before cleanly removing roles, categories, and channels created by the bot.*

### 3. Help
```
!help
```

Only users with **Manage Server** permission can use these commands.

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
