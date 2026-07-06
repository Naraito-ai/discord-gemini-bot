import os
import json
import asyncio
import logging
import re
import io
import datetime
import discord
from discord.ext import commands
from discord import app_commands
from google import genai
from google.genai import types
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from database import db

# ── Logging Setup ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("GeminiBot")

# ── Keep-alive server so Render / Railway / UptimeRobot can ping us ────────
_flask_app = Flask(__name__)

@_flask_app.route('/')
def _home():
    return "✅ Discord Gemini Bot is alive and running!"

def keep_alive():
    t = Thread(target=lambda: _flask_app.run(host='0.0.0.0', port=8080), daemon=True)
    t.start()
# ───────────────────────────────────────────────────────────────────────────

# Load environment variables from .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def call_ai_generation(prompt, system_instruction, json_mode=False):
    """Generates content asynchronously using Groq (via aiohttp) or Gemini (via google-genai async)."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip().strip('"').strip("'")
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    
    if gemini_key.startswith("gsk_"):
        groq_key = gemini_key
        gemini_key = ""
        
    if groq_key:
        logger.info(f"Using Groq API for content generation (JSON Mode: {json_mode})")
        import aiohttp
        headers = {
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
            
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30) as r:
                r.raise_for_status()
                res_data = await r.json()
                return res_data["choices"][0]["message"]["content"]
        
    elif gemini_key:
        logger.info(f"Using Gemini API for content generation (JSON Mode: {json_mode})")
        c = genai.Client(api_key=gemini_key)
        
        config_args = {
            "system_instruction": system_instruction,
            "temperature": 0.3
        }
        if json_mode:
            config_args["response_mime_type"] = "application/json"
            
        config = types.GenerateContentConfig(**config_args)
        
        resp = await c.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config
        )
        return resp.text
        
    else:
        raise ValueError("No valid GROQ_API_KEY or GEMINI_API_KEY found in environment variables.")

# Gemini system prompt with Emoji, Topics, and Private Channel support
SYSTEM_PROMPT = """You are an expert Discord server structure generator and community architect. 
The user will describe a Discord server layout they want. 
Return ONLY a raw JSON object with no explanation, no markdown code fences, no backticks. 
Just the raw JSON and nothing else.

The JSON must follow this schema structure (which must represent the ENTIRE requested server layout with all categories and channels generated in the arrays):
{
  "roles": [
    {"name": "string", "color": "#HEXCODE", "hoist": true}
  ],
  "categories": [
    {
      "name": "string",
      "private_for": ["RoleName"],
      "channels": [
        {"name": "string", "type": "text or voice", "private_for": ["RoleName"], "topic": "string"}
      ]
    }
  ]
}

Rules:
- Generate ALL categories and channels requested by the user. Do NOT truncate, summarize, or only return a subset. If the user wants 6 categories, you MUST generate all 6 categories in the "categories" array.
- Generate multiple text and voice channels for each category as requested by the user.
- color must always be a valid hex code like #FF5733, #5865F2, #2ECC71, never a color name.
- channel names for text channels must be lowercase with hyphens instead of spaces. Include fitting emojis at the beginning (e.g., "📣-announcements", "💬-general-chat", "🎮-lfg", "👋-welcome").
- category names should be uppercase or well-formatted, preferably preceded by an emoji (e.g., "📌 INFORMATION", "💬 TEXT CHANNELS", "🔒 ADMIN ONLY").
- role names can have normal capitalization (e.g., "Admin", "Moderator", "VIP Member").
- hoist true means the role shows separately in the member list. Set hoist to true for staff or important roles.
- always include at least one staff/admin role with an appropriate color and hoist set to true.
- private_for is an optional list of role names that should have exclusive access to this category or channel. For example, if a category or channel is meant only for staff/admins, include "private_for": ["Admin", "Moderator"].
- topic is an optional but highly recommended string (max 1024 chars) describing the purpose of text channels. For example: "👋 Welcome new members! Please check out the rules." or "💬 General discussion about gaming and life." Always include engaging topics for text channels!
"""

# ── Preset Themes Data ──────────────────────────────────────────────────────

THEME_PRESETS = {
    "gaming": {
        "roles": [
            {"name": "Guild Master", "color": "#FF0000", "hoist": True},
            {"name": "Officer", "color": "#0000FF", "hoist": True},
            {"name": "Esports Team", "color": "#00FF00", "hoist": True},
            {"name": "Member", "color": "#808080", "hoist": False}
        ],
        "categories": [
            {
                "name": "📌 INFORMATION",
                "channels": [
                    {"name": "👋-rules", "type": "text", "topic": "Please read and follow the server rules!"},
                    {"name": "📢-announcements", "type": "text", "topic": "Official guild announcements and news."},
                    {"name": "🎁-giveaways", "type": "text", "topic": "Participate in server giveaways here!"}
                ]
            },
            {
                "name": "💬 TEXT LOUNGES",
                "channels": [
                    {"name": "💬-general-chat", "type": "text", "topic": "General chat for members."},
                    {"name": "🎮-lfg-gaming", "type": "text", "topic": "Looking for group! Find teammates here."},
                    {"name": "📸-clips-and-highlights", "type": "text", "topic": "Share your best gaming moments!"},
                    {"name": "🤖-bot-commands", "type": "text", "topic": "Execute commands for discord bots."}
                ]
            },
            {
                "name": "🔊 VOICE LOUNGES",
                "channels": [
                    {"name": "Lounge 1", "type": "voice"},
                    {"name": "Squad Room A", "type": "voice"},
                    {"name": "Squad Room B", "type": "voice"},
                    {"name": "Duo Room", "type": "voice"}
                ]
            },
            {
                "name": "🔒 STAFF ZONE",
                "private_for": ["Guild Master", "Officer"],
                "channels": [
                    {"name": "🚨-staff-chat", "type": "text", "topic": "Private discussions for the staff team."},
                    {"name": "🚨-mod-logs", "type": "text", "topic": "Logging moderation events."}
                ]
            }
        ]
    },
    "anime": {
        "roles": [
            {"name": "Sensei", "color": "#8A2BE2", "hoist": True},
            {"name": "Senpai", "color": "#FF69B4", "hoist": True},
            {"name": "Otaku", "color": "#00FFFF", "hoist": True},
            {"name": "Weeb", "color": "#808080", "hoist": False}
        ],
        "categories": [
            {
                "name": "📌 ANNOUNCEMENTS",
                "channels": [
                    {"name": "👋-rules", "type": "text", "topic": "Read the community rules and code of conduct!"},
                    {"name": "📢-announcements", "type": "text", "topic": "Server updates and events announcements."},
                    {"name": "🌸-welcome", "type": "text", "topic": "Welcome room for new Otaku joining us!"}
                ]
            },
            {
                "name": "🌸 ANIME ZONE",
                "channels": [
                    {"name": "💬-general-chat", "type": "text", "topic": "General chat about anime, manga, and gaming."},
                    {"name": "📺-current-season", "type": "text", "topic": "Discussion on currently airing anime series!"},
                    {"name": "🎨-art-showcase", "type": "text", "topic": "Share your drawings, edits, and fanart."},
                    {"name": "🍥-ramen-lounge", "type": "text", "topic": "Casual discussion and food pictures."}
                ]
            },
            {
                "name": "🔊 VOICE CHATS",
                "channels": [
                    {"name": "Stage Room", "type": "voice"},
                    {"name": "Watch Party 1", "type": "voice"},
                    {"name": "Watch Party 2", "type": "voice"},
                    {"name": "Chill Lounge", "type": "voice"}
                ]
            },
            {
                "name": "🔒 SENSEI ROOM",
                "private_for": ["Sensei", "Senpai"],
                "channels": [
                    {"name": "🔒-staff-only", "type": "text", "topic": "Private lounge for Sensei & Senpai."}
                ]
            }
        ]
    },
    "study": {
        "roles": [
            {"name": "Professor", "color": "#006400", "hoist": True},
            {"name": "Tutor", "color": "#FFD700", "hoist": True},
            {"name": "Study Partner", "color": "#008080", "hoist": True},
            {"name": "Student", "color": "#808080", "hoist": False}
        ],
        "categories": [
            {
                "name": "📌 WELCOME & RULES",
                "channels": [
                    {"name": "📚-rules", "type": "text", "topic": "Community guidelines for study sessions."},
                    {"name": "📢-news-and-updates", "type": "text", "topic": "Important study announcements and schedules."}
                ]
            },
            {
                "name": "📝 STUDY ROOMS",
                "channels": [
                    {"name": "💬-study-lounge", "type": "text", "topic": "General study discussions and planning."},
                    {"name": "🙋-ask-for-help", "type": "text", "topic": "Ask questions about homework or study topics."},
                    {"name": "📓-resources-share", "type": "text", "topic": "Share useful study websites, PDFs, and notes."},
                    {"name": "🎯-study-goals", "type": "text", "topic": "Post your daily study goals and track progress!"}
                ]
            },
            {
                "name": "🔊 CO-WORKING VOICES",
                "channels": [
                    {"name": "Focus Room (Muted)", "type": "voice"},
                    {"name": "Study Session A", "type": "voice"},
                    {"name": "Study Session B", "type": "voice"},
                    {"name": "Chill Lounge", "type": "voice"}
                ]
            },
            {
                "name": "🔒 FACULTY OFFICE",
                "private_for": ["Professor", "Tutor"],
                "channels": [
                    {"name": "🔒-staff-only", "type": "text", "topic": "Private faculty meeting room."}
                ]
            }
        ]
    },
    "creator": {
        "roles": [
            {"name": "Streamer", "color": "#FF0000", "hoist": True},
            {"name": "Moderator", "color": "#0000FF", "hoist": True},
            {"name": "VIP", "color": "#FFD700", "hoist": True},
            {"name": "Subscribers", "color": "#FF69B4", "hoist": True},
            {"name": "Fan", "color": "#808080", "hoist": False}
        ],
        "categories": [
            {
                "name": "📌 BROADCAST INFO",
                "channels": [
                    {"name": "👋-welcome", "type": "text", "topic": "Welcome to the fan guild!"},
                    {"name": "📢-stream-announcements", "type": "text", "topic": "Get notified when we go live!"},
                    {"name": "🎥-youtube-videos", "type": "text", "topic": "New YouTube video updates."}
                ]
            },
            {
                "name": "💬 FAN LOUNGE",
                "channels": [
                    {"name": "💬-general-chat", "type": "text", "topic": "Chat with the community here!"},
                    {"name": "💡-suggestions", "type": "text", "topic": "Suggest video or stream ideas."},
                    {"name": "📸-memes", "type": "text", "topic": "Post memes and funny pictures."},
                    {"name": "🎮-play-with-me", "type": "text", "topic": "LFG to play games during fan streams!"}
                ]
            },
            {
                "name": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "Lounge", "type": "voice"},
                    {"name": "Gaming with Fans", "type": "voice"},
                    {"name": "Sub Lounge", "type": "voice"}
                ]
            },
            {
                "name": "🔒 STAFF CONTROL",
                "private_for": ["Streamer", "Moderator"],
                "channels": [
                    {"name": "🚨-staff-chat", "type": "text", "topic": "Private channel for staff and streamer."},
                    {"name": "🚨-mod-logs", "type": "text", "topic": "Moderation bot logs."}
                ]
            }
        ]
    },
    "business": {
        "roles": [
            {"name": "Director", "color": "#1A5276", "hoist": True},
            {"name": "Manager", "color": "#5DADE2", "hoist": True},
            {"name": "Employee", "color": "#808080", "hoist": False}
        ],
        "categories": [
            {
                "name": "📌 GENERAL INFO",
                "channels": [
                    {"name": "📢-announcements", "type": "text", "topic": "Important corporate announcements."},
                    {"name": "📅-schedule", "type": "text", "topic": "Upcoming company events and schedules."},
                    {"name": "🏢-company-info", "type": "text", "topic": "General company links and resources."}
                ]
            },
            {
                "name": "💬 WORKSPACE",
                "channels": [
                    {"name": "💬-general-discussion", "type": "text", "topic": "General workspace discussion."},
                    {"name": "💡-project-ideas", "type": "text", "topic": "Brainstorming new projects."},
                    {"name": "📎-file-sharing", "type": "text", "topic": "Share project mockups and docs here."},
                    {"name": "🤝-client-feedback", "type": "text", "topic": "Post client feedback and suggestions."}
                ]
            },
            {
                "name": "🔊 MEETING ROOMS",
                "channels": [
                    {"name": "Conference Room A", "type": "voice"},
                    {"name": "Conference Room B", "type": "voice"},
                    {"name": "Watercooler (Casual)", "type": "voice"}
                ]
            },
            {
                "name": "🔒 EXEC ZONE",
                "private_for": ["Director", "Manager"],
                "channels": [
                    {"name": "🔒-directors-only", "type": "text", "topic": "Confidential management discussions."}
                ]
            }
        ]
    }
}

# ── Aesthetic Letter Converters ─────────────────────────────────────────────

SMALL_CAPS_MAP = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ',
    'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ',
    's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
    'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ꜰ', 'G': 'ɢ', 'H': 'ʜ', 'I': 'ɪ',
    'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ǫ', 'R': 'ʀ',
    'S': 'ꜱ', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x', 'Y': 'ʏ', 'Z': 'ᴢ'
}

BUBBLE_MAP = {
    'a': 'ⓐ', 'b': 'ⓑ', 'c': 'ⓒ', 'd': 'ⓓ', 'e': 'ⓔ', 'f': 'ⓕ', 'g': 'ⓖ', 'h': 'ⓗ', 'i': 'ⓘ',
    'j': 'ⓙ', 'k': 'ⓚ', 'l': 'ⓛ', 'm': 'ⓜ', 'n': 'ⓝ', 'o': 'ⓞ', 'p': 'ⓟ', 'q': 'ⓠ', 'r': 'ⓡ',
    's': 'ⓢ', 't': 'ⓣ', 'u': 'ⓤ', 'v': 'ⓥ', 'w': 'ⓦ', 'x': 'ⓧ', 'y': 'ⓨ', 'z': 'ⓩ',
    'A': 'ⓐ', 'B': 'ⓑ', 'C': 'ⓒ', 'D': 'ⓓ', 'E': 'ⓔ', 'F': 'ⓕ', 'G': 'ⓖ', 'H': 'ⓗ', 'I': 'ⓘ',
    'J': 'ⓙ', 'K': 'ⓚ', 'L': 'ⓛ', 'M': 'ⓜ', 'N': 'ⓝ', 'O': 'ⓞ', 'P': 'ⓟ', 'Q': 'ⓠ', 'R': 'ⓡ',
    'S': 'ⓢ', 'T': 'ⓣ', 'U': 'ⓤ', 'V': 'ⓥ', 'W': 'ⓦ', 'X': 'ⓧ', 'Y': 'ⓨ', 'Z': 'ⓩ',
    '0': '⓪', '1': '①', '2': '②', '3': '③', '4': '④', '5': '⑤', '6': '⑥', '7': '⑦', '8': '⑧', '9': '⑨'
}

def style_text(text: str, style_type: str) -> str:
    if style_type == "lowercase":
        return text.lower().replace(" ", "-")
    elif style_type == "uppercase":
        return text.upper().replace(" ", "-")
    elif style_type == "small_caps":
        res = []
        for char in text:
            res.append(SMALL_CAPS_MAP.get(char, char))
        return "".join(res)
    elif style_type == "bubble":
        res = []
        for char in text:
            res.append(BUBBLE_MAP.get(char, char))
        return "".join(res)
    elif style_type == "spaced":
        chars = [char for char in text]
        return " ".join(chars)
    return text

# ── Teardown & Nuke Handlers ───────────────────────────────────────────────

async def teardown_guild(guild):
    """Deletes only the roles, categories, and channels created by this bot in the guild."""
    stats = {"roles": 0, "categories": 0, "channels": 0}
    logger.info(f"Starting teardown for guild {guild.name} ({guild.id})...")

    resources = await db.get_resources(guild.id)
    if not resources:
        logger.info(f"No tracked resources found for guild {guild.name}.")
        return stats

    channels = [r["resource_id"] for r in resources if r["resource_type"] == "channels"]
    categories = [r["resource_id"] for r in resources if r["resource_type"] == "categories"]
    roles = [r["resource_id"] for r in resources if r["resource_type"] == "roles"]

    # 1. Delete channels first
    for cid in channels:
        channel = guild.get_channel(cid)
        if channel:
            try:
                await channel.delete(reason="Gemini Bot Teardown")
                stats["channels"] += 1
            except Exception as e:
                logger.warning(f"Failed to delete channel {cid}: {e}")

    # 2. Delete categories
    for cid in categories:
        cat = guild.get_channel(cid)
        if cat:
            try:
                await cat.delete(reason="Gemini Bot Teardown")
                stats["categories"] += 1
            except Exception as e:
                logger.warning(f"Failed to delete category {cid}: {e}")

    # 3. Delete roles
    for rid in roles:
        role = guild.get_role(rid)
        if role and role != guild.default_role:
            try:
                await role.delete(reason="Gemini Bot Teardown")
                stats["roles"] += 1
            except Exception as e:
                logger.warning(f"Failed to delete role {rid}: {e}")

    logger.info(f"Teardown completed for {guild.name}: {stats}")
    await db.clear_resources(guild.id)
    return stats

async def nuke_guild(guild):
    """Deletes ALL roles, categories, and channels in the guild to start completely fresh."""
    stats = {"roles": 0, "categories": 0, "channels": 0}
    logger.info(f"Starting TOTAL NUKE for guild {guild.name} ({guild.id})...")

    clean_channel = None
    try:
        clean_channel = await guild.create_text_channel(
            name="💥-server-nuked",
            topic="Server wiped clean by Gemini Bot. Ready for /setup!",
            reason="Gemini Bot Complete Nuke"
        )
    except Exception as e:
        logger.error(f"Could not create clean channel during nuke: {e}")

    # 1. Delete all channels and categories (except clean_channel)
    for channel in list(guild.channels):
        if clean_channel and channel.id == clean_channel.id:
            continue
        try:
            await channel.delete(reason="Gemini Bot Complete Nuke")
            if isinstance(channel, discord.CategoryChannel):
                stats["categories"] += 1
            else:
                stats["channels"] += 1
        except Exception as e:
            logger.warning(f"Could not delete channel/category {channel.name}: {e}")

    # 2. Delete all roles (except default, managed, and higher than bot)
    for role in list(guild.roles):
        if role == guild.default_role or role.managed:
            continue
        if guild.me.top_role <= role:
            continue
        try:
            await role.delete(reason="Gemini Bot Complete Nuke")
            stats["roles"] += 1
        except Exception as e:
            logger.warning(f"Could not delete role {role.name}: {e}")

    await db.clear_resources(guild.id)
    return stats, clean_channel

# ── Interactive UI Views ───────────────────────────────────────────────────

class SetupConfirmView(discord.ui.View):
    def __init__(self, author, guild, plan_data, original_interaction):
        super().__init__(timeout=180.0)
        self.author = author
        self.guild = guild
        self.plan_data = plan_data
        self.original_interaction = original_interaction

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the command author can confirm or cancel this setup.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm & Build", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(content="⚙️ **Building server structure...** Please wait while roles and channels are generated.", embed=None, view=self)
        self.stop()
        await build_server_structure(self.guild, self.plan_data, interaction.channel)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(content="🚫 **Server setup cancelled.**", embed=None, view=self)
        self.stop()


class TeardownConfirmView(discord.ui.View):
    def __init__(self, author, guild):
        super().__init__(timeout=60.0)
        self.author = author
        self.guild = guild

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the command author can perform teardown.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, Delete AI Resources", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(content="🗑️ **Deleting AI-created roles, categories, and channels...**", embed=None, view=self)
        
        stats = await teardown_guild(self.guild)
        
        embed = discord.Embed(title="🗑️ Teardown Complete", color=discord.Color.red())
        embed.add_field(name="Channels Deleted", value=str(stats['channels']), inline=True)
        embed.add_field(name="Categories Deleted", value=str(stats['categories']), inline=True)
        embed.add_field(name="Roles Deleted", value=str(stats['roles']), inline=True)
        embed.set_footer(text="Powered by AI")
        
        await interaction.channel.send(embed=embed)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(content="🚫 **Teardown cancelled.**", embed=None, view=self)
        self.stop()


class NukeConfirmView(discord.ui.View):
    def __init__(self, author, guild):
        super().__init__(timeout=60.0)
        self.author = author
        self.guild = guild

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the command author can perform server nuke.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="💥 YES, NUKE ENTIRE SERVER", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def nuke_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(content="💥 **NUKING ENTIRE SERVER... Deleting all channels, categories, and roles!**", embed=None, view=self)
        
        stats, clean_channel = await nuke_guild(self.guild)
        
        embed = discord.Embed(title="💥 Server Completely Nuked", description="All old channels, categories, and roles have been wiped clean!", color=discord.Color.red())
        embed.add_field(name="Channels Deleted", value=str(stats['channels']), inline=True)
        embed.add_field(name="Categories Deleted", value=str(stats['categories']), inline=True)
        embed.add_field(name="Roles Deleted", value=str(stats['roles']), inline=True)
        embed.add_field(name="Next Step", value="Use `/setup` or select a preset theme to build your new layout on a clean slate!", inline=False)
        embed.set_footer(text="Powered by AI")
        
        if clean_channel:
            await clean_channel.send(embed=embed)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(content="🚫 **Server nuke cancelled.**", embed=None, view=self)
        self.stop()
# ───────────────────────────────────────────────────────────────────────────


async def build_server_structure(guild, data, response_channel):
    """Parses structural plan data and creates corresponding roles, categories, and channels."""
    logger.info(f"Starting AI server build for guild: {guild.name} ({guild.id})")
    roles_created = []
    categories_created = []
    channels_created = []
    errors_encountered = []
    role_objects = {}

    # 1. Create Roles (with individual error resilience)
    for role_data in data.get("roles", []):
        role_name = role_data.get("name")
        if not role_name:
            continue
        
        try:
            existing_role = discord.utils.get(guild.roles, name=role_name)
            if existing_role:
                role_objects[role_name] = existing_role
                roles_created.append(f"{role_name} (reused)")
                continue

            color_hex = role_data.get("color", "#FFFFFF")
            try:
                colour_obj = discord.Colour(int(color_hex.strip('#'), 16))
            except ValueError:
                colour_obj = discord.Colour.default()

            new_role = await guild.create_role(
                name=role_name,
                colour=colour_obj,
                hoist=role_data.get("hoist", False),
                reason="Gemini Discord Bot Setup",
            )
            roles_created.append(new_role.name)
            role_objects[role_name] = new_role
            await db.add_resource(guild.id, "roles", new_role.id)
            logger.info(f"Created role: {new_role.name}")
        except Exception as e:
            logger.error(f"Failed to create role '{role_name}': {e}")
            errors_encountered.append(f"Role '{role_name}': {e}")

    # Helper to generate permission overrides
    def get_overrides(private_roles_list):
        if not private_roles_list:
            return {}
        overrides = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False)
        }
        for r_name in private_roles_list:
            role_obj = role_objects.get(r_name) or discord.utils.get(guild.roles, name=r_name)
            if role_obj:
                overrides[role_obj] = discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True)
        return overrides

    # 2. Create Categories & Channels (with individual error resilience)
    for cat_data in data.get("categories", []):
        cat_name = cat_data.get("name")
        if not cat_name:
            continue

        try:
            category = discord.utils.get(guild.categories, name=cat_name)
            cat_overrides = get_overrides(cat_data.get("private_for"))

            if category is None:
                category = await guild.create_category(
                    name=cat_name,
                    overwrites=cat_overrides,
                    reason="Gemini Discord Bot Setup"
                )
                categories_created.append(category.name)
                await db.add_resource(guild.id, "categories", category.id)
                logger.info(f"Created category: {category.name}")
            else:
                categories_created.append(f"{category.name} (reused)")
        except Exception as e:
            logger.error(f"Failed to create category '{cat_name}': {e}")
            errors_encountered.append(f"Category '{cat_name}': {e}")
            continue

        for chan_data in cat_data.get("channels", []):
            chan_name = chan_data.get("name")
            chan_type = chan_data.get("type", "text")
            chan_topic = chan_data.get("topic")
            if not chan_name:
                continue
            
            try:
                existing_chan = discord.utils.get(category.channels, name=chan_name)
                if existing_chan:
                    prefix = "🔊 " if isinstance(existing_chan, discord.VoiceChannel) else "#"
                    channels_created.append(f"{prefix}{chan_name} (reused)")
                    continue

                chan_overrides = get_overrides(chan_data.get("private_for")) or cat_overrides

                if chan_type == "text":
                    new_chan = await guild.create_text_channel(
                        name=chan_name,
                        category=category,
                        overwrites=chan_overrides,
                        topic=chan_topic or None,
                        reason="Gemini Discord Bot Setup"
                    )
                    channels_created.append(f"#{new_chan.name}")
                    await db.add_resource(guild.id, "channels", new_chan.id)
                    logger.info(f"Created text channel: #{new_chan.name} (Topic: {chan_topic})")
                elif chan_type == "voice":
                    new_chan = await guild.create_voice_channel(
                        name=chan_name,
                        category=category,
                        overwrites=chan_overrides,
                        reason="Gemini Discord Bot Setup"
                    )
                    channels_created.append(f"🔊 {new_chan.name}")
                    await db.add_resource(guild.id, "channels", new_chan.id)
                    logger.info(f"Created voice channel: 🔊 {new_chan.name}")
            except Exception as e:
                logger.error(f"Failed to create channel '{chan_name}' in '{cat_name}': {e}")
                errors_encountered.append(f"Channel '{chan_name}' in '{cat_name}': {e}")

    logger.info(f"Server structure build completed for {guild.name}")

    # Send confirmation embed
    embed = discord.Embed(title="✅ Server Setup Complete", color=discord.Color.green())
    embed.add_field(name="Roles Created / Verified",      value=", ".join(dict.fromkeys(roles_created))                          or "None", inline=False)
    embed.add_field(name="Categories Created / Verified", value=", ".join(dict.fromkeys(categories_created))      or "None", inline=False)
    embed.add_field(name="Channels Created / Verified",   value=", ".join(channels_created[:20]) + ("..." if len(channels_created) > 20 else "") or "None", inline=False)
    
    if errors_encountered:
        errors_str = "\n".join(errors_encountered[:5]) + ("\n..." if len(errors_encountered) > 5 else "")
        embed.add_field(name="⚠️ Errors Encountered", value=f"```\n{errors_str}\n```", inline=False)

    embed.set_footer(text="Powered by AI • Use /teardown to reset AI-created items")

    await response_channel.send(embed=embed)


# ── Bot Client Initialization ───────────────────────────────────────────────

class GeminiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True  # Required for Join-to-Create dynamic voice
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        # Connect database & create tables
        await db.initialize()
        
    async def on_ready(self):
        logger.info(f"Bot logged in as {self.user} (ID: {self.user.id})")
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands globally.")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

bot = GeminiBot()


# ── App Slash Commands ──────────────────────────────────────────────────────

@bot.tree.command(name="help", description="Show all available commands and help options")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Discord Gemini Server Builder & Shield", 
        description="An all-in-one AI Architect, Auto-Mod, and Community Restorer Bot powered by Gemini 2.5 Flash / Groq!", 
        color=discord.Color.blurple()
    )
    embed.add_field(name="🏗️ **AI Server Architect**", value="• `/setup [theme] [desc]` — Build full server with roles & topics\n• `/addcategory <desc>` — AI builds & adds 1 category\n• `/stylechannels <style>` — Apply aesthetic styles to all text channels\n• `/backup` — Export server layout as a JSON file\n• `/restore <file>` — Load a backup file to restore server structure\n• `/dynamicvoice` — Setup a dynamic Join-to-Create voice system\n• `/teardown` — Delete only bot-created items\n• `/nuke` — **DANGER:** Wipe entire server clean", inline=False)
    embed.add_field(name="🛡️ **Security & Moderation**", value="• `/automod <status> [mode]` — Configures Toxic & Scam Shield\n• `/testautomod <text>` — Evaluates a text string\n• `/lockdown <status>` — Emergency chat freeze\n• `/purge <num>` — Instant spam/chat cleaner\n• `/kick <user> [reason]` — Kick a member\n• `/ban <user> [reason]` — Ban a user\n• `/unban <user_id> [reason]` — Unban a user\n• `/mute <user> <duration> [reason]` — Timeout a member\n• `/unmute <user> [reason]` — Remove timeout\n• `/deafen <user> [reason]` — Voice deafen member\n• `/undeafen <user> [reason]` — Voice undeafen member", inline=False)
    embed.set_footer(text="Powered by Google Gemini 2.5 Flash / Groq")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="setup", description="Generate a server structure preview and build it (Theme or Custom)")
@app_commands.describe(
    theme="An instant, ready-made preset theme for your server (Gaming, Anime, Study, Creator, Business)",
    description="Custom server description to generate via AI (e.g., 'art portfolio server with critiques')"
)
@app_commands.choices(
    theme=[
        app_commands.Choice(name="Gaming Guild", value="gaming"),
        app_commands.Choice(name="Anime Community", value="anime"),
        app_commands.Choice(name="Study Group", value="study"),
        app_commands.Choice(name="Content Creator / Streamer", value="creator"),
        app_commands.Choice(name="Business / Team Workspace", value="business")
    ]
)
@app_commands.default_permissions(manage_guild=True)
async def setup_command(interaction: discord.Interaction, theme: str = None, description: str = None):
    if not theme and not description:
        await interaction.response.send_message("❌ Please provide a preset `theme` OR a custom `description` to set up your server.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    data = None
    
    # Case 1: Preset Theme only (runs instantly, zero quota usage)
    if theme and not description:
        logger.info(f"Loading preset theme '{theme}' for guild '{interaction.guild.name}'")
        data = THEME_PRESETS.get(theme)
        
    # Case 2: Custom Description or Hybrid Prompt (runs AI)
    else:
        try:
            prompt = description
            sys_prompt = SYSTEM_PROMPT
            
            if theme:
                theme_data = THEME_PRESETS.get(theme)
                prompt = f"Using this preset layout as a reference: {json.dumps(theme_data)}, please modify and expand it to match the user's custom request: '{description}'."
                
            raw_response = await call_ai_generation(prompt, sys_prompt, json_mode=True)
            raw_response = raw_response.strip()

            if raw_response.startswith("```"):
                lines = raw_response.splitlines()
                lines = lines[1:] if lines[0].startswith("```") else lines
                lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
                raw_response = "\n".join(lines).strip()
                
            data = json.loads(raw_response)
        except Exception as e:
            logger.error(f"AI API error during setup: {e}")
            await interaction.followup.send(f"❌ **AI Generation Failed:** `{e}`\n\n💡 *If your API key is invalid or not loaded, try selecting a preset theme directly without a description!*")
            return

    if not data:
        await interaction.followup.send("❌ Error loading or generating the server layout.", ephemeral=True)
        return

    # Prepare Preview Embed
    roles_summary = [f"`{r['name']}` ({r.get('color', '#fff')})" for r in data.get("roles", [])]
    categories_summary = []
    total_channels = 0

    for cat in data.get("categories", []):
        chans = cat.get("channels", [])
        total_channels += len(chans)
        private_tag = " 🔒" if cat.get("private_for") else ""
        
        chan_names = []
        for c in chans:
            c_name = c.get('name', 'channel')
            if c.get('topic'):
                chan_names.append(f"#{c_name} 💬")
            else:
                chan_names.append(f"#{c_name}")
                
        categories_summary.append(f"**{cat.get('name')}**{private_tag} ({len(chans)} channels: {', '.join(chan_names[:5])}{'...' if len(chan_names)>5 else ''})")

    embed = discord.Embed(title="📋 Server Structure Preview", description="Review the generated layout below before creating channels and roles.\n*(Channels marked with 💬 include automatic topics & descriptions!)*", color=discord.Color.gold())
    embed.add_field(name="🎭 Roles to Create", value=", ".join(roles_summary) or "None", inline=False)
    embed.add_field(name=f"📁 Categories & Channels ({total_channels} channels total)", value="\n".join(categories_summary) or "None", inline=False)
    embed.set_footer(text="Click Confirm & Build below to execute this plan.")

    view = SetupConfirmView(interaction.user, interaction.guild, data, interaction)
    await interaction.followup.send(embed=embed, view=view)


@bot.tree.command(name="stylechannels", description="Apply a custom text styling aesthetic to all text channels in the server")
@app_commands.describe(style="The aesthetic style to apply")
@app_commands.choices(
    style=[
        app_commands.Choice(name="ɢᴇɴᴇʀᴀʟ-ᴄʜᴀᴛ (Small Caps)", value="small_caps"),
        app_commands.Choice(name="ⓖⓔⓝⓔⓡⓐⓛ-ⓒⓗⓐⓣ (Bubbles)", value="bubble"),
        app_commands.Choice(name="general-chat (Lowercase)", value="lowercase"),
        app_commands.Choice(name="GENERAL-CHAT (Uppercase)", value="uppercase"),
        app_commands.Choice(name="g e n e r a l - c h a t (Spaced)", value="spaced")
    ]
)
@app_commands.default_permissions(manage_channels=True)
async def stylechannels_command(interaction: discord.Interaction, style: str):
    await interaction.response.defer(thinking=True)
    success_count = 0
    fail_count = 0
    
    for channel in interaction.guild.text_channels:
        old_name = channel.name
        
        match = re.match(r"^([\u2000-\u32ff\ud83c-\udbff\udf00-\udfff]+[-#|]*)?(.*)$", old_name)
        if match:
            emoji_prefix = match.group(1) or ""
            core_name = match.group(2) or ""
        else:
            emoji_prefix = ""
            core_name = old_name
            
        styled_core = style_text(core_name, style)
        new_name = f"{emoji_prefix}{styled_core}"
        
        if old_name == new_name:
            continue
            
        try:
            await channel.edit(name=new_name, reason="Style Channels Command")
            success_count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Failed to style channel {old_name}: {e}")
            fail_count += 1
            
    await interaction.followup.send(f"✅ Re-styled `{success_count}` text channels to chosen style! (Failed: `{fail_count}` due to permissions/limits)")


@bot.tree.command(name="backup", description="Export the current server structure (roles, categories, channels) as a JSON template")
@app_commands.default_permissions(manage_guild=True)
async def backup_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    
    # 1. Export Roles
    roles_list = []
    for role in guild.roles:
        if role == guild.default_role or role.managed:
            continue
        roles_list.append({
            "name": role.name,
            "color": f"#{role.color.value:06x}",
            "hoist": role.hoist
        })
        
    # 2. Export Categories & Channels
    categories_list = []
    sorted_categories = sorted(guild.categories, key=lambda c: c.position)
    
    for cat in sorted_categories:
        cat_data = {
            "name": cat.name,
            "private_for": [],
            "channels": []
        }
        
        default_overwrite = cat.overwrites_for(guild.default_role)
        if default_overwrite.read_messages is False or default_overwrite.connect is False:
            for target, overwrite in cat.overwrites:
                if isinstance(target, discord.Role) and target != guild.default_role:
                    if overwrite.read_messages is True or overwrite.connect is True:
                        cat_data["private_for"].append(target.name)
                        
        sorted_chans = sorted(cat.channels, key=lambda c: c.position)
        for chan in sorted_chans:
            chan_type = "text" if isinstance(chan, discord.TextChannel) else "voice"
            chan_topic = getattr(chan, "topic", "")
            
            chan_data = {
                "name": chan.name,
                "type": chan_type,
                "topic": chan_topic or ""
            }
            
            chan_default_overwrite = chan.overwrites_for(guild.default_role)
            if chan_default_overwrite.read_messages is False or chan_default_overwrite.connect is False:
                chan_data["private_for"] = []
                for target, overwrite in chan.overwrites:
                    if isinstance(target, discord.Role) and target != guild.default_role:
                        if overwrite.read_messages is True or overwrite.connect is True:
                            chan_data["private_for"].append(target.name)
                            
            cat_data["channels"].append(chan_data)
            
        categories_list.append(cat_data)
        
    backup_data = {
        "roles": roles_list,
        "categories": categories_list
    }
    
    json_bytes = io.BytesIO(json.dumps(backup_data, indent=2, ensure_ascii=False).encode('utf-8'))
    discord_file = discord.File(json_bytes, filename=f"backup_{guild.name.replace(' ', '_')}.json")
    
    await interaction.followup.send(
        content="✅ **Server layout successfully exported!** Save this file to restore or clone this layout later using `/restore`.",
        file=discord_file,
        ephemeral=True
    )


@bot.tree.command(name="restore", description="Restore or clone a server structure from a backup JSON file")
@app_commands.describe(file="The backup JSON file generated by the /backup command")
@app_commands.default_permissions(manage_guild=True)
async def restore_command(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(".json"):
        await interaction.response.send_message("❌ Please upload a valid JSON template file (.json).", ephemeral=True)
        return
        
    await interaction.response.defer(thinking=True)
    try:
        file_bytes = await file.read()
        raw_data = file_bytes.decode("utf-8")
        data = json.loads(raw_data)
    except Exception as e:
        logger.error(f"Failed to read backup file: {e}")
        await interaction.followup.send(f"❌ Failed to parse the backup file: `{e}`")
        return
        
    if "categories" not in data:
        await interaction.followup.send("❌ Invalid template format. Missing the `categories` array.")
        return
        
    # Prepare Preview Embed
    roles_summary = [f"`{r['name']}` ({r.get('color', '#fff')})" for r in data.get("roles", [])]
    categories_summary = []
    total_channels = 0

    for cat in data.get("categories", []):
        chans = cat.get("channels", [])
        total_channels += len(chans)
        private_tag = " 🔒" if cat.get("private_for") else ""
        
        chan_names = []
        for c in chans:
            c_name = c.get('name', 'channel')
            if c.get('topic'):
                chan_names.append(f"#{c_name} 💬")
            else:
                chan_names.append(f"#{c_name}")
                
        categories_summary.append(f"**{cat.get('name')}**{private_tag} ({len(chans)} channels: {', '.join(chan_names[:5])}{'...' if len(chan_names)>5 else ''})")

    embed = discord.Embed(title="📋 Server Structure Preview (Restore)", description="Review the backup template layout below before creating channels and roles.", color=discord.Color.gold())
    embed.add_field(name="🎭 Roles to Create", value=", ".join(roles_summary) or "None", inline=False)
    embed.add_field(name=f"📁 Categories & Channels ({total_channels} channels total)", value="\n".join(categories_summary) or "None", inline=False)
    embed.set_footer(text="Click Confirm & Build below to restore this layout.")

    view = SetupConfirmView(interaction.user, interaction.guild, data, interaction)
    await interaction.followup.send(embed=embed, view=view)


@bot.tree.command(name="dynamicvoice", description="Set up a dynamic Join-to-Create voice channel system")
@app_commands.default_permissions(manage_guild=True)
async def dynamicvoice_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    guild = interaction.guild
    
    try:
        category = await guild.create_category("🔊 DYNAMIC VOICE", reason="Dynamic Voice Setup")
        generator_channel = await guild.create_voice_channel(
            name="➕ Join to Create",
            category=category,
            reason="Dynamic Voice Setup"
        )
        
        await db.add_resource(guild.id, "categories", category.id)
        await db.add_resource(guild.id, "channels", generator_channel.id)
        await db.set_config(guild.id, "voice_generator_id", generator_channel.id)
        
        await interaction.followup.send(f"✅ **Dynamic Voice System set up successfully!**\nMembers joining {generator_channel.mention} will automatically get their own temporary voice rooms.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to set up dynamic voice system: {e}")


@bot.tree.command(name="automod", description="Configure the Auto-Mod security and scam shield")
@app_commands.describe(
    status="Enable or disable Auto-Mod",
    mode="Choose between Local mode (free/instant) and AI mode (requires API key)"
)
@app_commands.choices(
    status=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off")
    ],
    mode=[
        app_commands.Choice(name="Local Shield (Free)", value="local"),
        app_commands.Choice(name="AI Scanner (Advanced)", value="ai")
    ]
)
@app_commands.default_permissions(manage_guild=True)
async def automod_command(interaction: discord.Interaction, status: str, mode: str = "local"):
    if status == "on":
        await db.set_config(interaction.guild_id, "automod", True)
        await db.set_config(interaction.guild_id, "automod_mode", mode)
        if mode == "local":
            await interaction.response.send_message("🧠 **Auto-Mod is now ON (Local Shield)!**\nScanning real-time chat instantly for curse words, slurs, and spam links without using API key quota.")
        else:
            await interaction.response.send_message("🧠 **Auto-Mod is now ON (AI Scanner)!**\nReal-time messages will be scanned using AI. *(Note: This uses your API key quota!)*")
    else:
        await db.set_config(interaction.guild_id, "automod", False)
        await interaction.response.send_message("🛡️ **Auto-Mod disabled.**")


@bot.tree.command(name="testautomod", description="Test how the AI Auto-Mod rates a specific text block")
@app_commands.describe(text="The message content to test")
@app_commands.default_permissions(manage_guild=True)
async def testautomod_command(interaction: discord.Interaction, text: str):
    await interaction.response.defer(thinking=True)
    try:
        prompt = f"Analyze if this chat message contains extreme toxicity, slurs, hate speech, severe harassment, or scam/phishing links: '{text}'."
        res = await call_ai_generation(prompt, "You are an expert content moderator. Respond with ONLY the word SAFE or TOXIC. Do not add any other text.")
        result = res.strip().upper()
        if "TOXIC" in result:
            await interaction.followup.send(f"🚨 **Auto-Mod Result:** `TOXIC`\n\n*If sent by a member, this message would have been deleted and logged.*")
        else:
            await interaction.followup.send(f"✅ **Auto-Mod Result:** `SAFE`\n\n*This message would be allowed in chat.*")
    except Exception as e:
        await interaction.followup.send(f"❌ Evaluation failed: {e}")


@bot.tree.command(name="lockdown", description="Freeze or unfreeze public chat channels in an emergency")
@app_commands.describe(status="Lock or unlock the channels")
@app_commands.choices(
    status=[
        app_commands.Choice(name="Lock (Freeze)", value="on"),
        app_commands.Choice(name="Unlock (Unfreeze)", value="off")
    ]
)
@app_commands.default_permissions(manage_channels=True)
async def lockdown_command(interaction: discord.Interaction, status: str):
    await interaction.response.defer(thinking=True)
    guild = interaction.guild
    if status == "on":
        locked = 0
        for chan in guild.text_channels:
            try:
                await chan.set_permissions(guild.default_role, send_messages=False, reason="Emergency Lockdown")
                locked += 1
            except Exception:
                pass
        await interaction.followup.send(f"🚨 **EMERGENCY LOCKDOWN INITIATED!** 🚨\nLocked `{locked}` public text channels. Regular members cannot type until unlocked.")
    else:
        unlocked = 0
        for chan in guild.text_channels:
            try:
                await chan.set_permissions(guild.default_role, send_messages=None, reason="Lockdown Lifted")
                unlocked += 1
            except Exception:
                pass
        await interaction.followup.send(f"🔓 **LOCKDOWN LIFTED!** Unlocked `{unlocked}` channels. Public chat is reopened.")


@bot.tree.command(name="purge", description="Quickly delete a specified number of messages from this channel")
@app_commands.describe(amount="Number of messages to delete (max 100)")
@app_commands.default_permissions(manage_messages=True)
async def purge_command(interaction: discord.Interaction, amount: int):
    amount = max(1, min(amount, 100))
    await interaction.response.defer(ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🧹 Successfully purged `{len(deleted)}` messages.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Purge failed: {e}", ephemeral=True)


@bot.tree.command(name="addcategory", description="Ask AI to design and add a single category with custom channels")
@app_commands.describe(description="Description of the category (e.g. 'VIP anime lounge with 4k stream rooms')")
@app_commands.default_permissions(manage_guild=True)
async def addcategory_command(interaction: discord.Interaction, description: str):
    await interaction.response.defer(thinking=True)
    try:
        sys_inst = f"The user wants to create a single Discord category: '{description}'. Return ONLY a raw JSON object with this structure: {{\"categories\": [{{\"name\": \"Category Name\", \"private_for\": [], \"channels\": [{{\"name\": \"chan-name\", \"type\": \"text\", \"topic\": \"chan topic\"}}, {{\"name\": \"voice-chan\", \"type\": \"voice\"}}]}}]}}. Do not include markdown or code blocks. Just JSON."
        text = await call_ai_generation(description, sys_inst, json_mode=True)
        
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
            text = "\n".join(lines).strip()
            
        data = json.loads(text)
        await interaction.edit_original_response(content="⚙️ **Building new category and channels...**")
        await build_server_structure(interaction.guild, data, interaction.channel)
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Failed to build category: {e}")


@bot.tree.command(name="teardown", description="Delete only the roles, categories, and channels created by this bot")
@app_commands.default_permissions(manage_guild=True)
async def teardown_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚠️ Confirm Teardown",
        description="Are you sure you want to delete all roles, categories, and channels created by the Gemini Bot in this server?",
        color=discord.Color.orange()
    )
    view = TeardownConfirmView(interaction.user, interaction.guild)
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="nuke", description="⚠️ COMPLETE SERVER NUKE — Wipes all channels, categories, and roles")
@app_commands.default_permissions(administrator=True)
async def nuke_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚠️ DANGER: COMPLETE SERVER NUKE ⚠️",
        description="Are you sure you want to delete **EVERY SINGLE CHANNEL, CATEGORY, AND ROLE** in this entire server?\n\nThis will wipe all existing rooms and create a fresh `#💥-server-nuked` channel so you can run `/setup` on a clean slate.\n\n**THIS CANNOT BE UNDONE!**",
        color=discord.Color.red()
    )
    view = NukeConfirmView(interaction.user, interaction.guild)
    await interaction.response.send_message(embed=embed, view=view)


# ── Administration & Moderation Commands ────────────────────────────────────

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="The member to kick", reason="The reason for kicking")
@app_commands.default_permissions(kick_members=True)
async def kick_command(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ You cannot kick this member because they have a higher or equal role than you.", ephemeral=True)
        return
    if member.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message("❌ I cannot kick this member because they have a higher or equal role than me.", ephemeral=True)
        return
        
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"✅ **{member.display_name}** has been kicked from the server. (Reason: {reason})")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to kick member: {e}", ephemeral=True)


@bot.tree.command(name="ban", description="Ban a user from the server")
@app_commands.describe(
    member="The member/user to ban", 
    reason="The reason for the ban", 
    delete_message_days="Number of days of messages to delete (0-7)"
)
@app_commands.choices(
    delete_message_days=[
        app_commands.Choice(name="Don't delete any", value=0),
        app_commands.Choice(name="Previous 24 hours", value=1),
        app_commands.Choice(name="Previous 7 days", value=7)
    ]
)
@app_commands.default_permissions(ban_members=True)
async def ban_command(interaction: discord.Interaction, member: discord.User, reason: str = "No reason provided", delete_message_days: int = 0):
    guild_member = interaction.guild.get_member(member.id)
    if guild_member:
        if guild_member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You cannot ban this member because they have a higher or equal role than you.", ephemeral=True)
            return
        if guild_member.top_role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ I cannot ban this member because they have a higher or equal role than me.", ephemeral=True)
            return
            
    try:
        seconds = delete_message_days * 86400
        await interaction.guild.ban(member, reason=reason, delete_message_seconds=seconds)
        await interaction.response.send_message(f"✅ **{member.display_name}** has been banned from the server. (Reason: {reason})")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to ban user: {e}", ephemeral=True)


@bot.tree.command(name="unban", description="Unban a user from the server")
@app_commands.describe(user_id="The Discord ID of the user to unban", reason="The reason for unbanning")
@app_commands.default_permissions(ban_members=True)
async def unban_command(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
    try:
        uid = int(user_id)
        user = await bot.fetch_user(uid)
        await interaction.guild.unban(user, reason=reason)
        await interaction.response.send_message(f"✅ **{user.display_name}** (ID: {user_id}) has been unbanned. (Reason: {reason})")
    except ValueError:
        await interaction.response.send_message("❌ Please provide a valid numerical User ID.", ephemeral=True)
    except discord.NotFound:
        await interaction.response.send_message("❌ That user was not found or is not banned.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to unban user: {e}", ephemeral=True)


@bot.tree.command(name="mute", description="Timeout (mute) a member in the server")
@app_commands.describe(
    member="The member to mute", 
    duration_minutes="Mute duration in minutes (max 40320 - 28 days)", 
    reason="The reason for muting"
)
@app_commands.default_permissions(moderate_members=True)
async def mute_command(interaction: discord.Interaction, member: discord.Member, duration_minutes: int, reason: str = "No reason provided"):
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ You cannot mute this member because they have a higher or equal role than you.", ephemeral=True)
        return
    if member.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message("❌ I cannot mute this member because they have a higher or equal role than me.", ephemeral=True)
        return
        
    duration = datetime.timedelta(minutes=duration_minutes)
    try:
        await member.timeout(duration, reason=reason)
        await interaction.response.send_message(f"✅ **{member.display_name}** has been timed out for `{duration_minutes}` minutes. (Reason: {reason})")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to mute member: {e}", ephemeral=True)


@bot.tree.command(name="unmute", description="Remove timeout (unmute) from a member in the server")
@app_commands.describe(member="The member to unmute", reason="The reason for unmuting")
@app_commands.default_permissions(moderate_members=True)
async def unmute_command(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not member.is_timed_out():
        await interaction.response.send_message(f"ℹ️ **{member.display_name}** is not timed out.", ephemeral=True)
        return
        
    try:
        await member.timeout(None, reason=reason)
        await interaction.response.send_message(f"✅ **{member.display_name}** is no longer timed out. (Reason: {reason})")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to unmute member: {e}", ephemeral=True)


@bot.tree.command(name="deafen", description="Deafen a member in a voice channel")
@app_commands.describe(member="The member to deafen", reason="The reason for deafening")
@app_commands.default_permissions(deafen_members=True)
async def deafen_command(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not member.voice or not member.voice.channel:
        await interaction.response.send_message(f"❌ **{member.display_name}** is not in a voice channel.", ephemeral=True)
        return
        
    try:
        await member.edit(deafen=True, reason=reason)
        await interaction.response.send_message(f"✅ **{member.display_name}** has been voice deafened. (Reason: {reason})")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to deafen member: {e}", ephemeral=True)


@bot.tree.command(name="undeafen", description="Undeafen a member in a voice channel")
@app_commands.describe(member="The member to undeafen", reason="The reason for undeafening")
@app_commands.default_permissions(deafen_members=True)
async def undeafen_command(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not member.voice or not member.voice.channel:
        await interaction.response.send_message(f"❌ **{member.display_name}** is not in a voice channel.", ephemeral=True)
        return
        
    try:
        await member.edit(deafen=False, reason=reason)
        await interaction.response.send_message(f"✅ **{member.display_name}** has been voice undeafened. (Reason: {reason})")
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to undeafen member: {e}", ephemeral=True)


# ── Discord Event Listeners ─────────────────────────────────────────────────

@bot.event
async def on_voice_state_update(member, before, after):
    """Event listener to handle Join-to-Create dynamic voice channels."""
    guild = member.guild
    generator_id = await db.get_config(guild.id, "voice_generator_id")
    
    # 1. User joins the generator channel
    if after.channel and after.channel.id == generator_id:
        category = after.channel.category
        temp_channel_name = f"🔊 {member.display_name}'s Room"
        
        try:
            temp_channel = await guild.create_voice_channel(
                name=temp_channel_name,
                category=category,
                reason=f"Temporary room for {member.display_name}"
            )
            await db.add_resource(guild.id, "temp_voice_channels", temp_channel.id)
            await member.move_to(temp_channel)
        except Exception as e:
            logger.error(f"Error creating temp voice channel: {e}")
            
    # 2. User leaves a temporary voice channel
    if before.channel:
        temp_channels = await db.get_resources(guild.id, "temp_voice_channels")
        temp_ids = [r["resource_id"] for r in temp_channels]
        
        if before.channel.id in temp_ids:
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Temporary voice channel empty")
                    await db.execute("DELETE FROM guild_resources WHERE guild_id = ? AND resource_id = ?", str(guild.id), before.channel.id)
                except Exception as e:
                    logger.error(f"Error deleting empty temp channel: {e}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if not message.author.bot and message.guild:
        automod_enabled = await db.get_config(message.guild.id, "automod", True)
        if automod_enabled:
            content = message.content.strip()
            if content:
                # 1. Instant Local Filter (Free and uses ZERO API quota)
                profanities = [
                    "fuck", "bastard", "asshole", "bitch", "cunt", "motherfucker", "mother fucker", 
                    "nigger", "faggot", "retard", "kys", "kill yourself", "dickhead", "pussy", 
                    "whore", "slut", "crap", "bullshit", "jackass"
                ]
                scams = [
                    "discord-gift", "free nitro", "steamcommunity-free", "free robux", 
                    "airdrop claim", "crypto giveaway", "@everyone click here"
                ]
                
                is_toxic_local = False
                matched_reason = ""
                content_lower = content.lower()
                
                for word in profanities:
                    pattern = rf"\b{re.escape(word)}\b"
                    if re.search(pattern, content_lower):
                        is_toxic_local = True
                        matched_reason = "Flagged as Prohibited Language (Profanity/Abuse)"
                        break
                        
                if not is_toxic_local:
                    for scam in scams:
                        if scam in content_lower:
                            is_toxic_local = True
                            matched_reason = "Flagged as Prohibited Content (Spam/Scam/Phishing link)"
                            break
                            
                if is_toxic_local:
                    try:
                        await message.delete()
                        warn_msg = await message.channel.send(f"⚠️ {message.author.mention}, your message was deleted by **Auto-Mod (Local Shield)** for violating community safety rules.")
                        await asyncio.sleep(5)
                        await warn_msg.delete()
                        
                        mod_log = discord.utils.get(message.guild.text_channels, name="🚨-mod-logs") or discord.utils.get(message.guild.text_channels, name="mod-logs") or discord.utils.get(message.guild.text_channels, name="🚨-admin-chat")
                        if mod_log:
                            log_embed = discord.Embed(title="🚨 Auto-Mod Flagged Message", color=discord.Color.red())
                            log_embed.add_field(name="Author", value=f"{message.author} ({message.author.id})", inline=True)
                            log_embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                            log_embed.add_field(name="Deleted Content", value=content[:1000], inline=False)
                            log_embed.add_field(name="Reason", value=matched_reason, inline=True)
                            await mod_log.send(embed=log_embed)
                        return
                    except Exception as del_err:
                        logger.error(f"Auto-Mod local delete failed: {del_err}")
                        return

                # 2. Optional AI Fallback Filter (Requires automod_mode set to 'ai')
                automod_mode = await db.get_config(message.guild.id, "automod_mode", "local")
                if automod_mode == "ai":
                    try:
                        prompt = f"Analyze if this chat message contains extreme toxicity, slurs, hate speech, severe harassment, or scam/phishing links: '{content}'."
                        text = await call_ai_generation(prompt, "You are an expert content moderator. Respond with ONLY the word SAFE or TOXIC. Do not add any other text.")
                        result = text.strip().upper()
                        if "TOXIC" in result:
                                try:
                                    await message.delete()
                                    warn_msg = await message.channel.send(f"⚠️ {message.author.mention}, your message was deleted by **AI Auto-Mod** for violating community safety rules.")
                                    await asyncio.sleep(5)
                                    await warn_msg.delete()
                                    
                                    mod_log = discord.utils.get(message.guild.text_channels, name="🚨-mod-logs") or discord.utils.get(message.guild.text_channels, name="mod-logs") or discord.utils.get(message.guild.text_channels, name="🚨-admin-chat")
                                    if mod_log:
                                        log_embed = discord.Embed(title="🚨 Auto-Mod Flagged Message", color=discord.Color.red())
                                        log_embed.add_field(name="Author", value=f"{message.author} ({message.author.id})", inline=True)
                                        log_embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                                        log_embed.add_field(name="Deleted Content", value=content[:1000], inline=False)
                                        log_embed.add_field(name="Reason", value="Flagged as TOXIC by AI", inline=True)
                                        await mod_log.send(embed=log_embed)
                                    return
                                except Exception as del_err:
                                    logger.error(f"Auto-Mod AI delete failed: {del_err}")
                                    return
                    except Exception as e:
                        logger.error(f"Auto-Mod AI evaluation error: {e}")

    await bot.process_commands(message)


# ── Main Entry Point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_token_here":
        print("Error: DISCORD_TOKEN is not set in .env file.")
    elif not GEMINI_API_KEY and not os.getenv("GROQ_API_KEY"):
        print("Error: Neither GEMINI_API_KEY nor GROQ_API_KEY is set in environment variables.")
    else:
        print("Starting Discord bot...")
        keep_alive()
        bot.run(DISCORD_TOKEN)
