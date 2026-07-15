# Changelog

All notable changes to the Discord Gemini Bot project are documented here.

## [1.1.0] - 2026-07-15

### Added
*   **Database Cleanup Event Listeners**: Added `on_guild_channel_delete` and `on_guild_role_delete` listeners in [bot.py](file:///D:/discord-gemini-bot/bot.py) to automatically remove deleted channels and roles from database tracking resources, preventing errors during `/teardown`.
*   **AI Rate Limiting & Input Sanitization**: Added a multi-layered security wrapper in [bot.py](file:///D:/discord-gemini-bot/bot.py) containing user cooldowns (30 seconds), server hourly limits (10 calls/hour), maximum input length restrictions (500 characters), and detection profiles for typical prompt injection keywords to protect custom setup commands from injection/abuse.


### Fixed
*   **Render Keep-Alive Routing**: Modified `keep_alive()` in [bot.py](file:///D:/discord-gemini-bot/bot.py) to bind to the dynamic `PORT` environment variable injected by Render, falling back to `8080` if not present. This ensures Render's port detection and routing work correctly, and prevents the web container from going to sleep when UptimeRobot pings the service.
*   **Auto-Mod Safety Bypass Protection**: Configured safety settings thresholds to `BLOCK_NONE` inside the Gemini client request configuration. This ensures toxicity moderation checks successfully return a `TOXIC` classification rather than raising a safety block error (which would bypass moderation and leave toxic messages in chat).
*   **Robust JSON Extraction**: Added an `extract_json(text)` helper in [bot.py](file:///D:/discord-gemini-bot/bot.py) to cleanly isolate layout responses between the first `{` and last `}` curly braces, preventing parsing failures if the AI model prepends introductory text.

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



