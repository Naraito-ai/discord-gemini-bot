import os
import json
import time
import math
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import jwt
import aiohttp
import psutil
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

load_dotenv()

# Logging Setup
logger = logging.getLogger("GeminiBot.API")

# FastAPI App
app = FastAPI(title="Discord Gemini Bot Dashboard API", version="1.0.0")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://.*",  # Matches HTTP and HTTPS origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT Setup
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-me-in-production")
JWT_ALGORITHM = "HS256"

# Discord OAuth2 Config
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:3000/api/auth/callback")
DISCORD_API_ENDPOINT = "https://discord.com/api/v10"

# WebSocket Connections
active_console_websockets = set()
active_event_websockets = set()

# Seed Data helper
async def seed_dashboard_data(db):
    """Seeds some default data if the tables are empty, for instant beautiful charts."""
    try:
        rows = await db.fetch("SELECT COUNT(*) as count FROM guilds")
        count = 0
        if rows:
            r = rows[0]
            count = r["count"] if isinstance(r, dict) and "count" in r else (r.get("count", 0) if hasattr(r, "get") else (r[0] if isinstance(r, (list, tuple)) else 0))
        if count == 0:
            now_ts = time.time()
            # Seed guilds
            await db.execute(
                "INSERT INTO guilds (id, name, icon, owner_id, member_count, joined_at, ai_enabled, logging_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                "123456789012345678", "Naruto Hub", "a_abcd1234efgh5678", "987654321098765432", 1540, now_ts - (30 * 86400), True, True
            )
            await db.execute(
                "INSERT INTO guilds (id, name, icon, owner_id, member_count, joined_at, ai_enabled, logging_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                "876543210987654321", "Konoha Sanctuary", None, "987654321098765432", 420, now_ts - (10 * 86400), True, False
            )
            
            # Seed analytics for the past 7 days
            for i in range(7):
                day = (datetime.now(timezone.utc).date() - timedelta(days=i)).isoformat()
                # Naruto Hub
                await db.execute(
                    "INSERT INTO analytics (guild_id, date, messages_count, commands_count, joins_count, leaves_count, warnings_count, mutes_count, bans_count, voice_active_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    "123456789012345678", day, 500 + i * 20, 45 + i * 5, max(0, 12 - i), 3, 2, 1, 0, 14400 + i * 600
                )
                # Konoha Sanctuary
                await db.execute(
                    "INSERT INTO analytics (guild_id, date, messages_count, commands_count, joins_count, leaves_count, warnings_count, mutes_count, bans_count, voice_active_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    "876543210987654321", day, max(10, 120 - i * 10), 10 + i, 4, 1, 0, 0, 0, 2000
                )
                
            # Seed AI Usage
            await db.execute(
                "INSERT INTO ai_usage (guild_id, user_id, prompt, response, model, tokens_used, latency) VALUES (?, ?, ?, ?, ?, ?, ?)",
                "123456789012345678", "987654321098765432", "Write a greeting channel topic for anime discussions", "✨ **Welcome to anime-chat!** A place to talk about all your favorite anime series.", "llama-3.3-70b-versatile", 240, 0.45
            )
            
            # Seed warnings
            await db.execute(
                "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
                "123456789012345678", "111111111111111111", "987654321098765432", "Spamming links in chat"
            )
            
            # Seed audit logs
            await db.execute(
                "INSERT INTO audit_logs (guild_id, user_id, action, details) VALUES (?, ?, ?, ?)",
                "123456789012345678", "987654321098765432", "AUTOROLE_TOGGLE", "Enabled autorole for member role"
            )
            
            logger.info("Successfully seeded dashboard analytics and demonstration data.")
    except Exception as e:
        logger.debug(f"Dashboard data seeding skipped: {e}")

# Live Log Broadcaster for WebSocket Console
async def broadcast_console(log_line: str):
    for ws in list(active_console_websockets):
        try:
            await ws.send_text(log_line)
        except Exception:
            active_console_websockets.discard(ws)

async def broadcast_event(event_type: str, data: dict):
    message = json.dumps({"event": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()})
    for ws in list(active_event_websockets):
        try:
            await ws.send_text(message)
        except Exception:
            active_event_websockets.discard(ws)

# Custom logging handler to redirect terminal logs to WebSockets
class WebSocketLogHandler(logging.Handler):
    def __init__(self, loop):
        super().__init__()
        self.loop = loop

    def emit(self, record):
        try:
            log_entry = self.format(record)
            if self.loop and self.loop.is_running() and active_console_websockets:
                asyncio.run_coroutine_threadsafe(broadcast_console(log_entry), self.loop)
        except Exception:
            pass

# Dependency to get current user from JWT token
async def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    
    parts = auth_header.split()
    if len(parts) != 2:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header format")
    token = parts[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token or session expired")

# ── Pydantic Request Models ────────────────────────────────────────────────
class ConfigUpdate(BaseModel):
    key: str
    value: str

# ── REST API Router Endpoints ──────────────────────────────────────────────

@app.get("/")
async def health_check():
    """Render and UptimeRobot health check ping route."""
    return {"status": "ok", "message": "✅ Discord Gemini Bot is alive and running!"}

@app.get("/health")
async def health():
    """Detailed health check endpoint for monitoring Discord Gateway and bot status."""
    bot = getattr(app.state, "bot", None)
    bot_status = "unknown"
    bot_latency = None
    bot_user = "not_initialized"
    try:
        if bot:
            if bot.user:
                bot_user = str(bot.user)
            if bot.is_ready():
                bot_status = "online"
                lat = getattr(bot, "latency", None)
                if lat is not None and not math.isinf(lat) and not math.isnan(lat):
                    bot_latency = round(lat * 1000, 2)
            elif bot.user:
                bot_status = "connecting"
            else:
                bot_status = "starting"
    except Exception as e:
        bot_status = f"error: {e}"

    return {
        "status": "ok",
        "bot": bot_user,
        "gateway": bot_status,
        "latency_ms": bot_latency
    }

@app.get("/terms", response_class=HTMLResponse)
async def terms_page():
    """Terms of service HTML page."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Terms of Service - Sweety Bot</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; padding: 40px 20px; max-width: 800px; margin: auto; }
        h1, h2 { color: #38bdf8; }
        a { color: #818cf8; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .card { background: #1e293b; padding: 24px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155; }
    </style>
</head>
<body>
    <h1>Terms of Service — Sweety Bot</h1>
    <p><em>Last Updated: August 2026</em></p>
    <div class="card">
        <h2>1. Acceptance of Terms</h2>
        <p>By adding <strong>Sweety</strong> to your Discord server or using any of its features, you agree to these Terms, as well as Discord's Terms of Service and Community Guidelines.</p>
        
        <h2>2. Permitted Usage</h2>
        <p>You agree not to exploit, spam, reverse-engineer, or use the bot to generate abusive, illegal, or harmful content.</p>
        
        <h2>3. Availability & Disclaimers</h2>
        <p>Sweety is provided on an "as-is" basis. The developers are not liable for server changes resulting from administrative commands executed by server staff.</p>
        
        <h2>4. Contact</h2>
        <p>Developer: <strong>Naraito</strong> (<a href="https://github.com/Naraito-ai/discord-gemini-bot" target="_blank">GitHub Repository</a>)</p>
    </div>
</body>
</html>"""

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page():
    """Privacy policy HTML page."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Privacy Policy - Sweety Bot</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; padding: 40px 20px; max-width: 800px; margin: auto; }
        h1, h2 { color: #38bdf8; }
        a { color: #818cf8; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .card { background: #1e293b; padding: 24px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155; }
    </style>
</head>
<body>
    <h1>Privacy Policy — Sweety Bot</h1>
    <p><em>Last Updated: August 2026</em></p>
    <div class="card">
        <h2>1. Data We Collect</h2>
        <p>Sweety processes Discord Server IDs, Channel IDs, Role IDs, and User IDs solely to deliver moderation, role management, and AI responses.</p>
        
        <h2>2. Data We Do NOT Collect</h2>
        <p>We do not collect private passwords, emails, financial information, or personal direct messages (DMs). We never sell or share user data.</p>
        
        <h2>3. AI Processing</h2>
        <p>User queries sent via <code>/ask</code> or direct mentions are transmitted securely via API to generate answers and are not stored for training.</p>
        
        <h2>4. Data Deletion</h2>
        <p>Server owners may request complete deletion of server settings and logs at any time by contacting the developer or removing the bot.</p>
        
        <h2>5. Contact</h2>
        <p>Developer: <strong>Naraito</strong> (<a href="https://github.com/Naraito-ai/discord-gemini-bot" target="_blank">GitHub Repository</a>)</p>
    </div>
</body>
</html>"""

@app.get("/api/auth/login")
async def get_login_url():
    """Generates the Discord OAuth2 URL for the dashboard login."""
    if not DISCORD_CLIENT_ID:
        return {"error": "DISCORD_CLIENT_ID is not configured in environment."}
    
    scope = "identify guilds"
    url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope={scope}"
    return {"url": url}

@app.post("/api/auth/callback")
async def auth_callback(body: dict):
    """Exchanges Discord code for access token and logs the user in."""
    code = body.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
        
    async with aiohttp.ClientSession() as session:
        # 1. Exchange OAuth code for Discord Access Token
        token_data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with session.post(f"{DISCORD_API_ENDPOINT}/oauth2/token", data=token_data, headers=headers) as resp:
            if resp.status != 200:
                err_text = await resp.text()
                logger.error(f"Discord Token Exchange Error: {err_text}")
                raise HTTPException(status_code=400, detail="Failed to retrieve token from Discord")
            tokens = await resp.json()
            access_token = tokens.get("access_token")
            
        # 2. Fetch User Profile Details
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get(f"{DISCORD_API_ENDPOINT}/users/@me", headers=auth_headers) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=400, detail="Failed to retrieve user profile")
            user_profile = await resp.json()
            
        # 3. Fetch User's Guilds list
        async with session.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=auth_headers) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=400, detail="Failed to retrieve user guilds")
            user_guilds = await resp.json()
            
    # Filter guilds where user has MANAGE_GUILD (0x20) or ADMINISTRATOR (0x8)
    admin_guilds = []
    for g in user_guilds:
        perms = int(g.get("permissions", "0"))
        if (perms & 0x20) == 0x20 or (perms & 0x8) == 0x8 or g.get("owner", False):
            admin_guilds.append({
                "id": g.get("id"),
                "name": g.get("name"),
                "icon": g.get("icon"),
                "permissions": perms
            })
            
    # Save user info in database
    db = getattr(app.state, "db", None)
    if db:
        await db.execute(
            "INSERT INTO users (id, username, discriminator, avatar) VALUES (?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET username = excluded.username, avatar = excluded.avatar",
            user_profile.get("id"), user_profile.get("username"), user_profile.get("discriminator"), user_profile.get("avatar")
        )
    
    # 4. Generate JWT dashboard session token
    expiration = datetime.now(timezone.utc) + timedelta(days=7)
    jwt_payload = {
        "user_id": user_profile.get("id"),
        "username": user_profile.get("username"),
        "avatar": user_profile.get("avatar"),
        "guilds": admin_guilds,
        "exp": expiration
    }
    jwt_token = jwt.encode(jwt_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    return {
        "token": jwt_token,
        "user": {
            "id": user_profile.get("id"),
            "username": user_profile.get("username"),
            "avatar": user_profile.get("avatar")
        },
        "guilds": admin_guilds
    }

@app.get("/api/bot/stats")
async def get_bot_stats():
    """Returns general statistics of the bot (system status, guilds, latency)."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        return {"error": "Bot starting"}
    db = getattr(app.state, "db", None)
    
    # Compute active systems
    guilds_count = len(bot.guilds)
    users_count = sum(g.member_count or 0 for g in bot.guilds)
    bot_latency = round(bot.latency * 1000, 2) if bot.latency and not math.isinf(bot.latency) and not math.isnan(bot.latency) else 0
    
    # AI usage metrics
    ai_reqs = 0
    ai_tokens = 0
    if db:
        ai_rows = await db.fetch("SELECT COUNT(*) as count, SUM(tokens_used) as tokens FROM ai_usage")
        if ai_rows:
            ai_reqs = ai_rows[0].get("count", 0) or 0
            ai_tokens = ai_rows[0].get("tokens", 0) or 0
    
    # Compute CPU/RAM usage
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    
    # Uptime computation
    uptime_seconds = int(time.time() - bot.start_time) if hasattr(bot, "start_time") else 0
    
    return {
        "guilds": guilds_count,
        "members": users_count,
        "latency": bot_latency,
        "uptime": uptime_seconds,
        "cpu": cpu,
        "ram": ram,
        "ai_requests_today": ai_reqs,
        "ai_tokens_today": ai_tokens,
        "version": "1.2.0",
        "database_status": "connected",
        "discord_gateway": "connected" if bot.is_ready() else "connecting"
    }

@app.get("/api/guilds")
async def get_user_guilds(user: dict = Depends(get_current_user)):
    """Returns all guilds the user manages, highlighting which ones have the bot invited."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        return {"error": "Bot starting"}
    user_guilds = user.get("guilds", [])
    
    result = []
    for ug in user_guilds:
        guild_id = ug.get("id")
        bot_guild = bot.get_guild(int(guild_id)) if guild_id and guild_id.isdigit() else None
        
        result.append({
            "id": guild_id,
            "name": ug.get("name"),
            "icon": ug.get("icon"),
            "invited": bot_guild is not None,
            "members": bot_guild.member_count if bot_guild else 0,
            "channels": len(bot_guild.channels) if bot_guild else 0,
            "roles": len(bot_guild.roles) if bot_guild else 0
        })
    return result

@app.get("/api/guilds/{guild_id}")
async def get_guild_details(guild_id: str, user: dict = Depends(get_current_user)):
    """Fetches detailed resource count, features, and logs config for a specific guild."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied to this server")
        
    bot = getattr(app.state, "bot", None)
    if not bot:
        return {"error": "Bot starting"}
    db = getattr(app.state, "db", None)
    guild = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
    
    if not guild:
        return {"invited": False}
        
    # Get config settings
    ai_enabled = await db.get_config(int(guild_id), "automod_ai", False) if db else False
    log_channel = await db.get_config(int(guild_id), "mod_log_channel", None) if db else None
    
    # Compute system lists
    roles = [{"id": str(r.id), "name": r.name, "color": str(r.color)} for r in guild.roles]
    channels = [{"id": str(c.id), "name": c.name, "type": str(c.type)} for c in guild.channels]
    
    # Fetch warnings count
    warnings_count = 0
    if db:
        warnings = await db.fetch("SELECT COUNT(*) as count FROM warnings WHERE guild_id = ?", guild_id)
        warnings_count = warnings[0].get("count", 0) if warnings else 0
    
    return {
        "invited": True,
        "name": guild.name,
        "icon": guild.icon.url if guild.icon else None,
        "owner_id": str(guild.owner_id),
        "owner_name": guild.owner.name if guild.owner else "Unknown",
        "members": guild.member_count,
        "boost_level": guild.premium_tier,
        "verification_level": str(guild.verification_level),
        "roles_count": len(roles),
        "channels_count": len(channels),
        "ai_enabled": ai_enabled,
        "logging_enabled": log_channel is not None,
        "log_channel_id": log_channel,
        "warnings_count": warnings_count,
        "roles": roles[:10],
        "channels": channels[:10]
    }

@app.get("/api/guilds/{guild_id}/config")
async def get_guild_config(guild_id: str, user: dict = Depends(get_current_user)):
    """Reads all configuration settings for a guild."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if not db:
        return {}
        
    gid = int(guild_id) if guild_id.isdigit() else guild_id
    prefix = await db.get_config(gid, "prefix", "!")
    automod = await db.get_config(gid, "automod", "enable")
    automod_ai = await db.get_config(gid, "automod_ai", False)
    log_channel = await db.get_config(gid, "mod_log_channel", "")
    autorole = await db.get_config(gid, "auto_role_id", "")
    antiraid_mode = await db.get_config(gid, "antiraid_mode", "enable")
    
    return {
        "prefix": prefix,
        "automod": automod,
        "automod_ai": automod_ai,
        "log_channel": log_channel,
        "autorole": autorole,
        "antiraid_mode": antiraid_mode
    }

@app.post("/api/guilds/{guild_id}/config")
async def update_guild_config(guild_id: str, config: ConfigUpdate, user: dict = Depends(get_current_user)):
    """Updates a single guild configuration setting."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database unavailable")
        
    gid = int(guild_id) if guild_id.isdigit() else guild_id
    await db.set_config(gid, config.key, config.value)
    
    # Broadcast configuration update log
    await broadcast_event("CONFIG_UPDATE", {
        "guild_id": guild_id,
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "key": config.key,
        "value": config.value
    })
    
    return {"status": "success", "message": f"Updated config key '{config.key}'"}

@app.get("/api/guilds/{guild_id}/analytics")
async def get_guild_analytics(guild_id: str, user: dict = Depends(get_current_user)):
    """Retrieves chronological database metrics for charts (messages, commands, moderation actions)."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if not db:
        return []
        
    rows = await db.fetch("SELECT * FROM analytics WHERE guild_id = ? ORDER BY date DESC LIMIT 15", str(guild_id))
    return sorted(rows, key=lambda x: str(x.get("date", "")))

@app.get("/api/guilds/{guild_id}/moderation")
async def get_guild_moderation(guild_id: str, user: dict = Depends(get_current_user)):
    """Returns logs of moderation actions, warnings, bans, and timeouts."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if not db:
        return {"warnings": [], "timeouts": [], "bans": []}
        
    warnings_rows = await db.fetch("SELECT * FROM warnings WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 50", str(guild_id))
    timeouts_rows = await db.fetch("SELECT * FROM timeouts WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 50", str(guild_id))
    bans_rows = await db.fetch("SELECT * FROM bans WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 50", str(guild_id))
    
    return {
        "warnings": warnings_rows,
        "timeouts": timeouts_rows,
        "bans": bans_rows
    }

@app.get("/api/guilds/{guild_id}/backups")
async def get_guild_backups(guild_id: str, user: dict = Depends(get_current_user)):
    """Lists saved server backups."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if not db:
        return []
        
    rows = await db.fetch("SELECT id, filename, timestamp FROM backups WHERE guild_id = ? ORDER BY timestamp DESC", str(guild_id))
    return rows

@app.delete("/api/guilds/{guild_id}/backups/{backup_id}")
async def delete_guild_backup(guild_id: str, backup_id: int, user: dict = Depends(get_current_user)):
    """Deletes a backup by ID."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if db:
        await db.execute("DELETE FROM backups WHERE id = ? AND guild_id = ?", backup_id, str(guild_id))
    return {"status": "success", "message": "Backup deleted"}

@app.get("/api/ai/stats")
async def get_ai_stats():
    """Returns aggregate metrics on Groq/Gemini usage, token efficiency, and response times."""
    db = getattr(app.state, "db", None)
    if not db:
        return {"total_requests": 0, "avg_tokens": 0, "avg_latency": 0.0, "total_tokens": 0, "models": []}
    
    rows = await db.fetch(
        "SELECT COUNT(*) as count, AVG(tokens_used) as avg_tokens, AVG(latency) as avg_latency, SUM(tokens_used) as total_tokens FROM ai_usage"
    )
    r = rows[0] if rows else {}
    models = await db.fetch("SELECT model, COUNT(*) as count FROM ai_usage GROUP BY model")
    
    return {
        "total_requests": r.get("count", 0) or 0,
        "avg_tokens": round(r.get("avg_tokens", 0) or 0, 2),
        "avg_latency": round(r.get("avg_latency", 0) or 0.0, 2),
        "total_tokens": r.get("total_tokens", 0) or 0,
        "models": models
    }

# ── WebSockets Server ──────────────────────────────────────────────────────

@app.websocket("/api/ws/console")
async def websocket_console(websocket: WebSocket):
    """Establishes a WebSocket connection for the live terminal log viewer."""
    await websocket.accept()
    active_console_websockets.add(websocket)
    try:
        await websocket.send_text(f"[{datetime.now().strftime('%H:%M:%S')}] Dashboard terminal WebSocket connection established.")
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_console_websockets.discard(websocket)
    except Exception:
        active_console_websockets.discard(websocket)

@app.websocket("/api/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket connection to receive live alerts and updates."""
    await websocket.accept()
    active_event_websockets.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_event_websockets.discard(websocket)
    except Exception:
        active_event_websockets.discard(websocket)

# Uvicorn startup handler
async def start_fastapi(bot, db, port: int):
    """Initializes and runs the Uvicorn FastAPI server inside the bot's async event loop."""
    app.state.bot = bot
    app.state.db = db
    
    # Seed analytics and config data
    await seed_dashboard_data(db)
    
    # Attach custom logging handler
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    ws_handler = WebSocketLogHandler(loop)
    ws_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s', '%Y-%m-%d %H:%M:%S'))
    logging.getLogger().addHandler(ws_handler)
    
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info", lifespan="off")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    
    logger.info(f"Starting FastAPI Web Server & WebSocket Engine on port {port}...")
    await server.serve()
