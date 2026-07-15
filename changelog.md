# Changelog

All notable changes to the Discord Gemini Bot project are documented here.

## [1.2.1] - 2026-07-15

### Fixed
*   **Missing `uvicorn` Import in `api.py`**: Added `import uvicorn` to the top-level imports in [api.py](file:///D:/discord-gemini-bot/api.py). The omission caused a `NameError` when `start_fastapi()` tried to subclass `uvicorn.Server`, preventing the FastAPI web server from starting alongside the bot.
*   **Windows Unicode Encoding Crash on Startup**: Replaced the `✅` emoji in the `bot.py` startup `print()` call with an ASCII-safe `[OK]` string to fix a `UnicodeEncodeError` on Windows terminals using the `cp1252` codec.
*   **Next.js Auth Callback Suspense Boundary**: Wrapped the `useSearchParams()` hook in [callback/page.tsx](file:///D:/discord-gemini-bot/dashboard/src/app/api/auth/callback/page.tsx) inside a `<Suspense>` boundary to comply with Next.js 15 static generation requirements and fix the production build error.
*   **Incorrect `Link` Import in `Sidebar.tsx`**: Fixed a broken import — `Link` was incorrectly imported from `next/navigation` instead of `next/link`, causing a TypeScript build error during `npm run build`.

---

## [1.2.0] - 2026-07-15

### Added
*   **Production FastAPI Backend (`api.py`)**: Created a full REST + WebSocket API server (`api.py`) that runs concurrently with the Discord bot inside the **same asyncio event loop** via `setup_hook()`. This design allows both services to run within a single Render free-tier web service container, avoiding multi-container cost.
    *   **Discord OAuth2 Authentication**: Implemented a `/api/auth/callback` endpoint that exchanges Discord authorization codes for access tokens, verifies that the authenticating user has `MANAGE_GUILD` or `ADMINISTRATOR` permissions, and returns signed **JWT tokens** for session management.
    *   **Bot Health & System Stats Endpoint** (`/api/bot/stats`): Returns live CPU usage, RAM usage, bot ping latency, uptime, total guild count, and active WebSocket connection counts using `psutil`.
    *   **Guild Configuration Endpoints** (`/api/guilds/{guild_id}/config`): GET and POST endpoints to read and write per-guild settings (prefix, AutoMod status, log channels, autorole) from the database.
    *   **Moderation Logs Endpoint** (`/api/guilds/{guild_id}/moderation`): Returns paginated warning, timeout, and ban records for a given guild.
    *   **Backups Endpoint** (`/api/guilds/{guild_id}/backups`): Returns and allows deletion of layout snapshot backups stored in the database.
    *   **Live Console WebSocket** (`/api/ws/console`): Streams backend Python log output to the dashboard console viewer in real time using a custom `WebSocketLogHandler`.
    *   **Live Events WebSocket** (`/api/ws/events`): Broadcasts moderation events (warnings, bans, Auto-Mod triggers) to all connected dashboard clients in real time.
*   **Expanded Database Schema (`database.py`)**: Added **15 production tables** to the database schema: `users`, `guilds`, `guild_config`, `guild_resources`, `commands`, `warnings`, `timeouts`, `bans`, `ai_usage`, `api_usage`, `backups`, `audit_logs`, `notifications`, `errors`, `analytics`. All tables are created automatically on first startup.
*   **Database Logging Helper Methods**: Added `log_command()`, `log_ai_usage()`, `add_warning()`, `add_timeout()`, `add_ban()`, `log_audit()`, and `increment_analytics()` helper methods to `DatabaseManager` in [database.py](file:///D:/discord-gemini-bot/database.py) for structured telemetry logging across bot events.
*   **Neon PostgreSQL Integration**: Configured the bot and API to connect to a Neon free-tier PostgreSQL database (`aws-ap-southeast-1` region) in production via `DATABASE_URL`, while automatically falling back to local SQLite during development with dynamic SQL dialect translation.
*   **Next.js 15 Web Dashboard (`dashboard/`)**: Built a complete, production-compiled multi-page web dashboard with glassmorphism dark UI:
    *   **Landing / Login Page** (`page.tsx`): Discord OAuth2 login card, global stats (guilds, users, commands), live alert panel, and server selector grid.
    *   **Auth Callback Handler** (`/api/auth/callback/page.tsx`): Exchanges Discord OAuth codes with the backend and persists the JWT session.
    *   **Live Terminal Console** (`/console/page.tsx`): A streaming black-box terminal that receives and displays Python bot logs in real time over WebSocket, with auto-scroll, log-level color coding, and search filtering.
    *   **Guild Overview Page** (`/guilds/[guild_id]/page.tsx`): Server detail card showing member count, channel count, role count, and guild-level statistics.
    *   **Analytics Charts** (`/guilds/[guild_id]/analytics/page.tsx`): Recharts `AreaChart` and `BarChart` displaying message traffic, command usage, and join/leave trends over time.
    *   **AI Usage Dashboard** (`/guilds/[guild_id]/ai-usage/page.tsx`): Recharts `PieChart` showing Gemini vs Groq model distribution and token consumption breakdown.
    *   **Moderation Incident Registry** (`/guilds/[guild_id]/moderation/page.tsx`): Three-panel view displaying warnings, active timeouts, and ban records pulled from the database.
    *   **Server Layout Backups Manager** (`/guilds/[guild_id]/backups/page.tsx`): Lists and allows deletion of guild layout snapshots created via `/backup`.
    *   **Bot Settings Configuration** (`/guilds/[guild_id]/settings/page.tsx`): Form-based editor for command prefix, AutoMod mode, AI deep moderation toggle, mod logs channel, and autorole settings — saved via API POST.
*   **Responsive Sidebar & Header Components**: Built `Sidebar.tsx` with a mobile-drawer toggle, guild switcher dropdown, and active-route highlighting. Built `Header.tsx` with a user avatar, real-time WebSocket pulse beacon, and logout button.
*   **Global Dashboard Context** (`DashboardContext.tsx`): React context managing authentication state, guild selections, bot stats, and real-time WebSocket event subscriptions with automatic reconnection on disconnect.
*   **Deployment Infrastructure**:
    *   Updated [Dockerfile](file:///D:/discord-gemini-bot/Dockerfile) to copy `api.py` and `database.py` alongside `bot.py`.
    *   Created [dashboard/.env.local](file:///D:/discord-gemini-bot/dashboard/.env.local) with `NEXT_PUBLIC_BACKEND_URL` and `NEXT_PUBLIC_DISCORD_CLIENT_ID`.
    *   Created [DASHBOARD_README.md](file:///D:/discord-gemini-bot/DASHBOARD_README.md) documenting the full directory structure, PostgreSQL schema, environment variable checklist, and step-by-step free-tier deployment guides for Neon, Render, and Vercel.
*   **Auto-configured Neon Database**: Provisioned a Neon PostgreSQL project (`wild-fog-70302333`) in the `aws-ap-southeast-1` region using the Neon API, initialized all 15 schema tables, and stored the pooler connection string in `.env`.
*   **Auto-generated JWT Secret**: Generated and stored a cryptographically secure 32-byte hex JWT secret in `.env` for signing dashboard session tokens.

### Changed
*   **Replaced Flask Keep-Alive with FastAPI**: Disabled the `keep_alive()` Flask server in `bot.py.__main__` and replaced it with an integrated `uvicorn` server launched inside `setup_hook()`, eliminating the Flask dependency and merging both HTTP and WebSocket serving into a single process.
*   **Updated `requirements.txt`**: Replaced `flask` with `fastapi`, `uvicorn[standard]`, `python-multipart`, `pyjwt`, and `psutil`.

---

## [1.1.4] - 2026-07-15


### Fixed
*   **UptimeRobot API payload format**: Fixed `register_uptime_monitor` to send parameters using `application/x-www-form-urlencoded` format (`data=payload`) rather than `application/json` (`json=payload`), complying with the UptimeRobot API v2 specification and ensuring successful monitor registration.
*   **Web hosting container keep-alive**: Changed the process type in `Procfile` from `worker` to `web` so that web hosting services like Render or Railway route HTTP requests and bind `PORT` variables correctly, preventing the container from sleeping.
*   **Environment documentation updates**: Added production configurations (`DATABASE_URL`, `UPTIME_API_KEY`, and `RENDER_EXTERNAL_URL`) to `.env.example`.

## [1.1.3] - 2026-07-15


### Added
*   **Uncategorized Channels Backup & Restore**: Added support for exporting and restoring channels not belong to any category in the `/backup` and `/restore` commands.

### Fixed
*   **Log Channel View Permission Verification**: Modified `/setlogchannel` to check that the bot has `view_channel` permission in the logging channel, preventing log delivery failures.
*   **AI Auto-Mod Activation Crash**: Added checks to `/automod` and `/testautomod` to gracefully verify that AI API credentials (`GEMINI_API_KEY` or `GROQ_API_KEY`) are present in environment variables before setting AI mode, preventing unhandled runtime errors.
*   **Role Hierarchy Enforcement**: Integrated role hierarchy checks to the voice moderation commands (`/deafen`, `/undeafen`) and `/unmute` to protect administrators and moderators.
*   **Managed Role Assignment Failures**: Patched `/addrole`, `/removerole`, `/roleall`, and `/roleallremove` to reject operations on managed integration/booster roles, returning clear user-facing errors rather than API crashes.
*   **Server Owner Action Protection**: Prevented moderation actions (`/kick` and `/ban`) from being targeted against the guild's Server Owner.

## [1.1.2] - 2026-07-15

### Fixed
*   **AI Cooldown Bypass in `/embed`**: Applied rate-limiting user cooldowns, server hourly caps, and input sanitization to the `/embed` command when using AI styling to prevent API quota abuse and prompt injection.
*   **Security Lockdown Reversal Vulnerability**: Redesigned the `/lockdown` command to explicitly log and track which channels the bot locked in the database. When lifting the lockdown, only those specific channels have their permissions restored, leaving read-only/announcement channels secure.
*   **Privilege Escalation Protection**: Enforced role hierarchy checks for `/autorole` settings and prevented `/aiperms` from granting overrides that the executing member doesn't possess.
*   **Voice State DB Query Flood**: Optimized `on_voice_state_update` events by keeping temporary voice channel IDs in a memory set cache (`bot.temp_voice_channel_ids`), avoiding database calls on user voice events.
*   **Discord API Rate-Limit (429) Throttling**: Added a `0.2s` - `0.3s` backoff sleep delay inside sequential resource creations and deletions (`/setup`, `/teardown`, `/nuke`, `/lockdown`) to prevent hitting Discord's strict rate limits.

### Changed
*   **Relaxed AI Cooldown Constraints**: Adjusted the default AI user cooldown to `5` seconds (down from `30`s) and increased the server hourly limit to `100` calls (up from `10`) to allow smoother and more frequent user interactions.

## [1.1.1] - 2026-07-15

### Fixed
*   **Aesthetic Channel Styling Re-application**: Integrated `destyle_text` in [bot.py](file:///D:/discord-gemini-bot/bot.py) to strip any previously applied Unicode formatting (Small Caps, Bubbles, Spaced) and collapse spaced names before applying a new style. This enables users to freely switch between styles or revert channels back to normal lowercase via the `/stylechannels` command.

### Optimized
*   **Fast Configuration Caching**: Added an in-memory configuration cache in [database.py](file:///D:/discord-gemini-bot/database.py). This completely eliminates database reads on every single incoming chat message, dramatically improving the bot's overall response speed and reliability under load.

## [1.1.0] - 2026-07-15

### Added
*   **Database Cleanup Event Listeners**: Added `on_guild_channel_delete` and `on_guild_role_delete` listeners in [bot.py](file:///D:/discord-gemini-bot/bot.py) to automatically remove deleted channels and roles from database tracking resources, preventing errors during `/teardown`.
*   **AI Rate Limiting & Input Sanitization**: Added a multi-layered security wrapper in [bot.py](file:///D:/discord-gemini-bot/bot.py) containing user cooldowns (30 seconds), server hourly limits (10 calls/hour), maximum input length restrictions (500 characters), and detection profiles for typical prompt injection keywords to protect custom setup commands from injection/abuse.
*   **Dynamic Moderation Logging**: Added a new `/setlogchannel <channel>` command in [bot.py](file:///D:/discord-gemini-bot/bot.py) to dynamically set a target logging channel. All moderation events, slash commands, and Auto-Mod violations are logged as structured rich embeds to this configured channel.
*   **Chat Spam & Duplicate Message Protection**: Integrated memory-based rate limiters to monitor rapid message bursts (5 messages in 5s) and duplicate content spamming (3 identical messages in 15s). Message bursts are deleted and offenders are auto-muted.
*   **NSFW/Porn link filtering**: Integrated a URL scanner in the Auto-Mod filter that checks links for pornographic or adult gif content keywords (e.g., `porn`, `nsfw`, `xxx`, `rule34`, `hentai`). Flagged messages are deleted instantly.
*   **Automatic 10-Minute Timeout (Mute)**: Auto-Mod now executes an automatic 10-minute timeout/mute on users sending NSFW/Porn links or chat spam, logging the action and warning the user in chat.
*   **AI Permission Manager (`/aiperms`)**: Introduced the `/aiperms <target> <description>` command which uses AI to translate natural language configuration requests into concrete Discord permission overrides for multiple roles and/or specific members concurrently on a selected channel or category.




### Fixed
*   **Render Keep-Alive Routing**: Modified `keep_alive()` in [bot.py](file:///D:/discord-gemini-bot/bot.py) to bind to the dynamic `PORT` environment variable injected by Render, falling back to `8080` if not present. This ensures Render's port detection and routing work correctly, and prevents the web container from going to sleep when UptimeRobot pings the service.
*   **Auto-Mod Safety Bypass Protection**: Configured safety settings thresholds to `BLOCK_NONE` inside the Gemini client request configuration. This ensures toxicity moderation checks successfully return a `TOXIC` classification rather than raising a safety block error (which would bypass moderation and leave toxic messages in chat).
*   **Robust JSON Extraction**: Added an `extract_json(text)` helper in [bot.py](file:///D:/discord-gemini-bot/bot.py) to cleanly isolate layout responses between the first `{` and last `}` curly braces, preventing parsing failures if the AI model prepends introductory text.
*   **Prevented Error Information Leakage**: Replaced all instances of raw exception details (`f"{e}"`) being displayed to public users on command failure with user-safe generic error responses, logging the full debug tracebacks internally using `logger.error`.
*   **Targeted Member Resolving in `/aiperms`**: Optimized `/aiperms` context generation to search descriptions for user mentions or matching names, sending only the targeted members to the AI instead of a generic list of the first 50 members.
*   **Restricted Commands to Guilds Only**: Restricted all server-specific slash commands from execution inside bot DMs by applying the `@app_commands.guild_only()` decorator, preventing database errors and rate limit bypasses.
*   **Resolved Log Channel Cache Failures**: Added an API fallback (`await guild.fetch_channel(channel_id)`) to `get_mod_log_channel` when the configured log channel is not found in the bot's local memory cache, and wrapped the auto-mute log send block in try-except wrappers to prevent failures.



### Optimized
*   **Reusable Global Gemini Client**: Refactored the `genai.Client` instantiation logic to initialize the client object globally and reuse it via `get_gemini_client()`, avoiding heavy re-instantiation overhead on every single message/moderation scan.

### Reverted
*   **Engagement & Support Slash Commands**: Added and subsequently removed the following commands from [bot.py](file:///D:/discord-gemini-bot/bot.py) per user request to maintain the bot's concise features footprint:
    *   `/welcome` (dynamic AI welcome messages)
    *   `/announce` (AI-written server announcements)
    *   `/ticket` (persistent support button ticket panels)
    *   `/suggest` (suggestion voting)
    *   `/poll` (multi-option reaction polls)

### Changed
*   **Restricted /nuke Command to Server Owner**: Added a double layer of runtime checks (`interaction.user.id == interaction.guild.owner_id` both inside `nuke_command` and inside the `nuke_button` confirm callback in `NukeConfirmView`) in [bot.py](file:///D:/discord-gemini-bot/bot.py) to guarantee that only the server owner can invoke or confirm the nuke command under any circumstance.



