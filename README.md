# 🤖 Discord Gemini Bot

An enterprise-ready, high-performance Discord bot powered by **Google Gemini 2.5 Flash** (and **Groq**) that automatically designs, sets up, and secures Discord servers using AI.

---

## ✨ Premium Features

*   **⚡ Slash Commands (`/`)**: Native application commands with autocomplete, validation, and Discord permission controls.
*   **🏗️ AI Server Architect (`/setup <description>`)**: AI generates a complete server layout preview embed with **Confirm (✅)** and **Cancel (❌)** buttons before creating any roles or channels. Includes:
    *   **Emoji-rich text & voice channels** (e.g. `📣-announcements`, `💬-general-chat`).
    *   **Engaging channel topics** written dynamically by AI.
    *   **Role creation** with custom permissions and colors.
    *   **Private channels** (e.g. staff-only categories restricted to custom Admin/Moderator roles).
*   **🛡️ Multi-Tier Auto-Mod (`/automod <status> <mode>`)**:
    *   **Local Shield (Free & Instant)**: Uses zero API key quota, scanning chat in real-time for slurs, insults, and scam links.
    *   **AI Scanner (Advanced)**: Dynamically evaluates questionable posts using the AI content safety filter.
*   **🎟️ Persistent Support Tickets (`/ticket`)**: Spawns an interactive button panel. Clicking the button creates a private staff-support channel that remains functional even after bot restarts.
*   **👋 AI Join Welcome Greetings (`/welcome <style>`)**: AI dynamically crafts unique welcome greetings for new members.
*   **🗑️ Safe Reversibility (`/teardown` & `/nuke`)**:
    *   `/teardown`: Cleanly deletes *only* roles, categories, and channels built by the bot, leaving user-created channels intact.
    *   `/nuke`: Full server wipe for developers starting with a clean slate.

---

## 🛠️ Installation & Setup

### Local Run

1.  **Clone the repository**.
2.  **Create a `.env` file** (copy from `.env.example`):
    ```env
    DISCORD_TOKEN=your_discord_bot_token
    GEMINI_API_KEY=your_gemini_api_key
    # Optional: If you prefer using Groq
    GROQ_API_KEY=your_groq_api_key
    # Optional: PostgreSQL Database URL for production persistence
    DATABASE_URL=postgresql://user:pass@host:port/dbname
    ```
3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Launch the bot**:
    ```bash
    python bot.py
    ```

---

## 💾 Database Persistence (SQLite & PostgreSQL)

The bot supports a dual-storage model:
*   **SQLite (Default)**: Automatically used if no `DATABASE_URL` env variable is set. Stores guild settings in a local `bot_data.db` file.
*   **PostgreSQL (Recommended for Render/Production)**: If `DATABASE_URL` is configured, the bot connects to PostgreSQL (e.g., Supabase or Render DB). **This prevents data loss on Render free tier restarts.**

---

## 🚀 Deploying to Render (24/7 Hosting)

Since Render free plans restart frequently and have ephemeral storage, configure PostgreSQL to save state.

1.  **Create a Web Service** on Render.
2.  **Link your GitHub repository**.
3.  **Use the following configurations**:
    *   **Runtime**: Python
    *   **Build Command**: `pip install -r requirements.txt`
    *   **Start Command**: `python bot.py`
4.  **Add environment variables** under the **Environment** tab:
    *   `DISCORD_TOKEN`
    *   `GROQ_API_KEY` or `GEMINI_API_KEY`
    *   `DATABASE_URL` (Retrieve from a free Supabase PostgreSQL database or a Render PostgreSQL database).
5.  *(Optional)* Use a ping service (like UptimeRobot) to ping the Render URL (port `8080`) to keep the service awake.

---

## 📋 Slash Commands Reference

| Command | Permission Required | Description |
|---------|---------------------|-------------|
| `/help` | Everyone | View bot guide and commands. |
| `/setup <description>` | Manage Server | Generate and preview a server layout, then build it. |
| `/addcategory <description>` | Manage Server | AI designs and creates a single category and channels. |
| `/teardown` | Manage Server | Delete only roles/channels created by this bot. |
| `/nuke` | Administrator | **DANGER:** Wipe entire server clean. |
| `/automod <on/off> <local/ai>` | Manage Server | Toggle chat protection filter. |
| `/testautomod <text>` | Manage Server | Run a test string through the toxic/scam filter. |
| `/welcome <style/off>` | Manage Server | Enable/disable dynamic AI welcome messages. |
| `/announce <topic>` | Manage Messages | Drafts and posts an AI official server announcement. |
| `/lockdown <on/off>` | Manage Channels | Lock/unlock text channels in an emergency. |
| `/purge <amount>` | Manage Messages | Delete up to 100 recent messages. |
| `/ticket` | Manage Server | Setup the support ticket button panel. |
| `/suggest <idea>` | Everyone | Submit a suggestion to the suggestions channel. |
| `/poll <question> <options>` | Everyone | Create a poll (options separated by `,` or `\|`). |
