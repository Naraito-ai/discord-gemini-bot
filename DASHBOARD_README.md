# 🤖 Discord Gemini Bot Dashboard & Telemetry Server

This guide contains the detailed technical architecture, schema specifications, Docker configurations, and deployment guides for your new Next.js 15 Web Dashboard and FastAPI Backend integration.

---

## 📂 Complete Folder Structure

```
discord-gemini-bot/
├── .env                  # local environment configs
├── .env.example          # configuration reference keys
├── .gitignore            # git ignore rules
├── Dockerfile            # docker production container file
├── Procfile              # render/railway command triggers
├── README.md             # bot documentation
├── DASHBOARD_README.md   # dashboard documentation (this file)
├── bot.py                # Discord bot client & handler hooks
├── database.py           # sqlite/postgres client manager & schema creators
├── api.py                # FastAPI server, OAuth2 authentication, WebSockets
├── requirements.txt      # python package dependencies
│
└── dashboard/            # Next.js 15 Web Dashboard (Frontend)
    ├── package.json      # npm scripts and package versions
    ├── tsconfig.json     # typescript compilation configurations
    ├── tailwind.config.ts# tailwind css configuration
    ├── postcss.config.mjs# tailwind parser config
    ├── public/           # static public image assets
    └── src/
        ├── context/
        │   └── DashboardContext.tsx # global states, session handlers, WS listeners
        ├── components/
        │   ├── Sidebar.tsx          # side navigations and dropdown switcher
        │   └── Header.tsx           # user profile header & WS pulse indicators
        └── app/
            ├── globals.css          # scrollbars, animations, glassmorphism CSS
            ├── layout.tsx           # app root layout containers
            ├── page.tsx             # landing and auth card views
            ├── console/
            │   └── page.tsx         # live terminal console logger via websockets
            ├── api/auth/callback/
            │   └── page.tsx         # OAuth2 parser and token exchanger page
            └── guilds/[guild_id]/
                ├── page.tsx         # server detail overview
                ├── analytics/
                │   └── page.tsx     # AreaChart and BarChart activity analytics
                ├── ai-usage/
                │   └── page.tsx     # AI & Groq tokens splits (PieChart)
                ├── moderation/
                │   └── page.tsx     # warnings, active timeouts, and bans
                ├── backups/
                │   └── page.tsx     # snapshot restoration and deletes
                └── settings/
                    └── page.tsx     # prefix, automod, logging channel forms
```

---

## 💾 PostgreSQL Schema Specification

The `database.py` file initializes these tables automatically on startup when connecting to Neon PostgreSQL or local SQLite:

```sql
-- Guilds metadata
CREATE TABLE IF NOT EXISTS guilds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    icon TEXT,
    owner_id TEXT,
    member_count INTEGER DEFAULT 0,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ai_enabled BOOLEAN DEFAULT TRUE,
    logging_enabled BOOLEAN DEFAULT FALSE
);

-- Guilds config variables (Key-Value)
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (guild_id, key)
);

-- Users registry
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    discriminator TEXT,
    avatar TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Command completions log
CREATE TABLE IF NOT EXISTS commands (
    id SERIAL PRIMARY KEY,
    guild_id TEXT,
    user_id TEXT,
    command_name TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL,
    latency REAL
);

-- Moderation warning events
CREATE TABLE IF NOT EXISTS warnings (
    id SERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    moderator_id TEXT NOT NULL,
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Active timeouts log
CREATE TABLE IF NOT EXISTS timeouts (
    id SERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    moderator_id TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bans registry
CREATE TABLE IF NOT EXISTS bans (
    id SERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    moderator_id TEXT NOT NULL,
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AI generation stats (Gemini / Groq)
CREATE TABLE IF NOT EXISTS ai_usage (
    id SERIAL PRIMARY KEY,
    guild_id TEXT,
    user_id TEXT,
    prompt TEXT,
    response TEXT,
    model TEXT,
    tokens_used INTEGER DEFAULT 0,
    latency REAL DEFAULT 0.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Backup layout snapshots
CREATE TABLE IF NOT EXISTS backups (
    id SERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    backup_data TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log history
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- System incidents and errors
CREATE TABLE IF NOT EXISTS errors (
    id SERIAL PRIMARY KEY,
    guild_id TEXT,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    stack_trace TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Historical daily analytics for charts
CREATE TABLE IF NOT EXISTS analytics (
    id SERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    date DATE DEFAULT CURRENT_DATE,
    messages_count INTEGER DEFAULT 0,
    commands_count INTEGER DEFAULT 0,
    joins_count INTEGER DEFAULT 0,
    leaves_count INTEGER DEFAULT 0,
    warnings_count INTEGER DEFAULT 0,
    mutes_count INTEGER DEFAULT 0,
    bans_count INTEGER DEFAULT 0,
    voice_active_seconds INTEGER DEFAULT 0
);
```

---

## 🔑 Environment Variables Checklist

### Backend & Bot (`.env`)
```env
# Discord Developer Portal variables
DISCORD_TOKEN=your_discord_bot_token
DISCORD_CLIENT_ID=your_discord_developer_app_client_id
DISCORD_CLIENT_SECRET=your_discord_developer_app_client_secret

# AI Models
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key

# PostgreSQL (Neon Database URL)
DATABASE_URL=postgresql://user:pass@host/dbname

# JWT Session Encryption
JWT_SECRET=generate_a_random_32_character_hex_key

# Dashboard callback redirect
DISCORD_REDIRECT_URI=http://localhost:3000/api/auth/callback
```

### Frontend (`dashboard/.env.local`)
```env
# URL where the backend FastAPI runs
NEXT_PUBLIC_BACKEND_URL=http://localhost:8080
# Client ID for Discord Redirects
NEXT_PUBLIC_DISCORD_CLIENT_ID=your_discord_developer_app_client_id
```

---

## 🚀 Free Tier Deployment Guide

This setup is optimized to run **completely free** on Render, Neon, and Vercel.

### 1. Database (Neon PostgreSQL Free Tier)
1. Go to [Neon.tech](https://neon.tech/) and create a free PostgreSQL project.
2. Retrieve the connection string (`postgresql://...`).
3. Set the `DATABASE_URL` environment variable inside your Render app to this connection string.

### 2. Backend & Discord Bot (Render Free Tier Web Service)
Render Free Tier allows you to run a single service 24/7. Because our FastAPI server and Discord Bot are run **under the same process and same event loop**, you only need to deploy **one** web service!

1. Go to [Render Dashboard](https://dashboard.render.com/) and create a new **Web Service**.
2. Connect your GitHub repository.
3. Configure the following deployment fields:
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
4. Add all environment variables listed in the backend section above to the Render Dashboard **Environment** panel.
5. Setup UptimeRobot (Free) to ping your Render URL `https://your-service.onrender.com/` every 5 minutes. This ensures that the web container does not sleep.

### 3. Frontend Dashboard (Vercel Free Tier)
1. Import your GitHub repository to [Vercel](https://vercel.com/).
2. Change the directory target to `dashboard`.
3. Add the two environment variables listed in the Frontend section:
   - `NEXT_PUBLIC_BACKEND_URL`: Set this to your Render service URL (e.g. `https://your-app.onrender.com`).
   - `NEXT_PUBLIC_DISCORD_CLIENT_ID`: Set this to your Discord Bot client ID.
4. Deploy the application.
5. **IMPORTANT:** Copy your deployed Vercel URL (e.g. `https://your-dashboard.vercel.app`) and update the `DISCORD_REDIRECT_URI` environment variable inside the **Render Dashboard** to `https://your-dashboard.vercel.app/api/auth/callback`, and add the exact same callback URL inside your **Discord Developer Portal** under **OAuth2 -> Redirects**.
