import os
import json
import asyncio
import logging
import re
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
    
    # If GEMINI_API_KEY is actually a Groq key (starts with gsk_)
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
        
        # Use client.aio for non-blocking async execution
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

    # Create a clean default channel so server isn't 100% empty
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
        embed.add_field(name="Next Step", value="Use `/setup <description>` right here to build your new server layout on a clean slate!", inline=False)
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


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="gemini_bot:close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 **Closing and deleting ticket room in 3 seconds...**")
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason="Ticket Closed")
        except Exception as e:
            logger.error(f"Failed to delete ticket channel: {e}")


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎟️ Open Support Ticket", style=discord.ButtonStyle.primary, emoji="🎟️", custom_id="gemini_bot:open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Support ticket operations can take some time, so we defer first
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        
        category = discord.utils.get(guild.categories, name="🎟️ SUPPORT TICKETS")
        if not category:
            try:
                category = await guild.create_category("🎟️ SUPPORT TICKETS", reason="Ticket System Category")
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to create ticket category: {e}", ephemeral=True)
                return

        chan_name = f"ticket-{user.name.lower()}".replace(" ", "-").replace("#", "")
        if discord.utils.get(category.text_channels, name=chan_name):
            await interaction.followup.send("❌ You already have an open support ticket!", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        for r in guild.roles:
            if any(w in r.name.lower() for w in ["admin", "mod", "staff", "officer", "guild master"]):
                overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            ticket_chan = await guild.create_text_channel(
                name=chan_name,
                category=category,
                overwrites=overwrites,
                topic=f"Support ticket for {user.display_name} (ID: {user.id})",
                reason="User opened support ticket"
            )
            embed = discord.Embed(
                title=f"🎟️ Support Ticket — {user.display_name}",
                description=f"Hello {user.mention}!\nThank you for reaching out. A staff member or moderator will be with you shortly.\n\nTo close this ticket when your issue is resolved, click the **🔒 Close Ticket** button below.",
                color=discord.Color.green()
            )
            await ticket_chan.send(content=f"{user.mention} | Staff Notification", embed=embed, view=TicketCloseView())
            await interaction.followup.send(f"✅ Your support ticket has been opened: {ticket_chan.mention}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            await interaction.followup.send(f"❌ Could not create ticket room: {e}", ephemeral=True)
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
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        # 1. Connect database & create tables
        await db.initialize()
        
        # 2. Register persistent views
        self.add_view(TicketView())
        self.add_view(TicketCloseView())
        
    async def on_ready(self):
        logger.info(f"Bot logged in as {self.user} (ID: {self.user.id})")
        # Sync slash commands globally
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
        title="🤖 Discord Gemini Server Builder & Community Shield", 
        description="An all-in-one AI Architect, Auto-Mod, and Community Management Bot powered by Gemini 2.5 Flash / Groq!", 
        color=discord.Color.blurple()
    )
    embed.add_field(name="🏗️ **AI Server Architect**", value="• `/setup <desc>` — Build full server with roles & topics\n• `/addcategory <desc>` — AI builds & adds 1 category\n• `/teardown` — Delete only bot-created items\n• `/nuke` — **DANGER:** Wipe entire server clean", inline=False)
    embed.add_field(name="🛡️ **Security & Moderation**", value="• `/automod <status> [mode]` — Configures Toxic & Scam Shield\n• `/testautomod <text>` — Evaluates a text string\n• `/lockdown <status>` — Emergency chat freeze\n• `/purge <num>` — Instant spam/chat cleaner", inline=False)
    embed.add_field(name="💬 **Community & Engagement**", value="• `/welcome <style>` — AI Dynamic Join Greeter\n• `/announce <topic>` — AI Announcement Writer\n• `/ticket` — Create interactive Support Ticket button\n• `/suggest <idea>` — Interactive suggestion box\n• `/poll <question> <options>` — Reaction poll", inline=False)
    embed.set_footer(text="Powered by Google Gemini 2.5 Flash / Groq")
    await interaction.response.send_message(embed=embed)


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


@bot.tree.command(name="welcome", description="Configure the AI welcome message style for new members")
@app_commands.describe(style="The personality/style of the greeting (e.g. 'anime', 'funny', 'gamer', 'off' to disable)")
@app_commands.default_permissions(manage_guild=True)
async def welcome_command(interaction: discord.Interaction, style: str):
    if style.lower() in ("off", "disable", "false"):
        await db.set_config(interaction.guild_id, "welcome", "off")
        await interaction.response.send_message("👋 **AI Welcome Greeter disabled.**")
    else:
        await db.set_config(interaction.guild_id, "welcome", style)
        await interaction.response.send_message(f"👋 **AI Welcome Greeter Enabled!**\nPersonality/Style set to: **`{style}`**.\nWhen new members join, AI will dynamically generate a unique greeting in your welcome/general channel!")


@bot.tree.command(name="announce", description="Generate an engaging server announcement using AI")
@app_commands.describe(topic="The subject of the announcement (e.g., 'weekend Valorant tournament')")
@app_commands.default_permissions(manage_messages=True)
async def announce_command(interaction: discord.Interaction, topic: str):
    await interaction.response.defer(thinking=True)
    try:
        prompt = f"Write an exciting, professional Discord server announcement about: '{topic}'. Format with emojis, bold headers, bullet points, and make it highly engaging! Return ONLY the announcement text."
        text = await call_ai_generation(prompt, "You are a professional Discord community manager.")
        if text:
            embed = discord.Embed(title="📢 Official Announcement", description=text.strip(), color=discord.Color.brand_red())
            embed.set_footer(text=f"Announced by {interaction.user.display_name} • Powered by AI", icon_url=interaction.user.display_avatar.url)
            await interaction.channel.send(content="@everyone", embed=embed)
            await interaction.followup.send("✅ Announcement posted!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to generate announcement: {e}")


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


@bot.tree.command(name="ticket", description="Send the interactive Support Ticket panel into this channel")
@app_commands.default_permissions(manage_guild=True)
async def ticket_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎟️ Support & Help Desk",
        description="Need assistance from our moderators or staff team?\n\nClick the **🎟️ Open Support Ticket** button below to create a private, secure chat room with our team!",
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Private 1-on-1 Support • Powered by AI")
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ Support ticket panel posted!", ephemeral=True)


@bot.tree.command(name="suggest", description="Submit a suggestion to the community suggestion box")
@app_commands.describe(idea="Your suggestion or idea for the server")
async def suggest_command(interaction: discord.Interaction, idea: str):
    guild = interaction.guild
    sug_chan = discord.utils.get(guild.text_channels, name="💡-suggestions") or discord.utils.get(guild.text_channels, name="suggestions") or discord.utils.get(guild.text_channels, name="server-suggestions") or interaction.channel
    
    embed = discord.Embed(title="💡 Community Suggestion", description=f"**{idea}**", color=discord.Color.gold())
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    embed.set_footer(text="Status: [UNDER REVIEW] • Vote with 👍 or 👎 below!")
    
    try:
        sug_msg = await sug_chan.send(embed=embed)
        await sug_msg.add_reaction("👍")
        await sug_msg.add_reaction("👎")
        if sug_chan.id != interaction.channel_id:
            await interaction.response.send_message(f"✅ Your suggestion was posted in {sug_chan.mention}!", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Suggestion posted!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to post suggestion: {e}", ephemeral=True)


@bot.tree.command(name="poll", description="Create a public poll with up to 10 options")
@app_commands.describe(
    question="The question for the poll",
    options="The choices, separated by | or comma (e.g. 'Yes | No' or 'Blue, Red, Green')"
)
async def poll_command(interaction: discord.Interaction, question: str, options: str):
    if "|" in options:
        parts = [p.strip() for p in options.split("|") if p.strip()]
    else:
        parts = [p.strip() for p in options.split(",") if p.strip()]
        
    if len(parts) < 2:
        await interaction.response.send_message("❌ Please provide at least 2 options!", ephemeral=True)
        return
        
    options_list = parts[:10]
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    desc_lines = [f"{emojis[i]} **{opt}**" for i, opt in enumerate(options_list)]
    
    embed = discord.Embed(title=f"📊 {question}", description="\n\n".join(desc_lines), color=discord.Color.teal())
    embed.set_footer(text=f"Poll created by {interaction.user.display_name} • React to vote!", icon_url=interaction.user.display_avatar.url)
    
    try:
        poll_msg = await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Poll created!", ephemeral=True)
        for i in range(len(options_list)):
            await poll_msg.add_reaction(emojis[i])
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to create poll: {e}", ephemeral=True)


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


@bot.tree.command(name="setup", description="Generate a server structure preview from text and build it")
@app_commands.describe(description="Description of the server (e.g. 'community server for anime lovers with art showcase')")
@app_commands.default_permissions(manage_guild=True)
async def setup_command(interaction: discord.Interaction, description: str):
    await interaction.response.defer(thinking=True)
    try:
        raw_response = await call_ai_generation(description, SYSTEM_PROMPT, json_mode=True)
        raw_response = raw_response.strip()

        if raw_response.startswith("```"):
            lines = raw_response.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
            raw_response = "\n".join(lines).strip()
    except Exception as e:
        logger.error(f"AI API error during setup: {e}")
        await interaction.followup.send(f"❌ **AI API Connection Failed:** `{e}`\n\n💡 *Make sure your API key in environment variables is valid!*")
        return

    try:
        data = json.loads(raw_response)
    except Exception as e:
        logger.error(f"JSON parse error: {e}\nRaw response: {raw_response}")
        await interaction.followup.send("❌ Couldn't understand the generated structure. Try rephrasing your prompt.")
        return

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

    embed = discord.Embed(title="📋 Server Structure Preview", description="Review the AI-generated layout below before creating channels and roles.\n*(Channels marked with 💬 include automatic topics & descriptions!)*", color=discord.Color.gold())
    embed.add_field(name="🎭 Roles to Create", value=", ".join(roles_summary) or "None", inline=False)
    embed.add_field(name=f"📁 Categories & Channels ({total_channels} channels total)", value="\n".join(categories_summary) or "None", inline=False)
    embed.set_footer(text="Click Confirm & Build below to execute this plan.")

    view = SetupConfirmView(interaction.user, interaction.guild, data, interaction)
    await interaction.followup.send(embed=embed, view=view)


# ── Discord Event Listeners ─────────────────────────────────────────────────

@bot.event
async def on_member_join(member):
    guild = member.guild
    style = await db.get_config(guild.id, "welcome", "off")
    if not style or style.lower() == "off":
        return

    logger.info(f"New member {member.name} joined {guild.name}. Welcome style: {style}")
    
    welcome_chan = (
        discord.utils.get(guild.text_channels, name="👋-welcome") or
        discord.utils.get(guild.text_channels, name="welcome") or
        discord.utils.get(guild.text_channels, name="💬-general-chat") or
        discord.utils.get(guild.text_channels, name="general") or
        guild.system_channel or
        (guild.text_channels[0] if guild.text_channels else None)
    )
    if not welcome_chan:
        return

    try:
        prompt = f"Write a short, warm, and exciting 2-sentence welcome greeting for user '{member.display_name}' joining our Discord community '{guild.name}'. Write it in the personality/style of: '{style}'. Use emojis and format nicely!"
        text = await call_ai_generation(prompt, "You are a professional, friendly Discord welcome greeter.")
        if text:
            embed = discord.Embed(title=f"👋 Welcome to {guild.name}!", description=f"{member.mention}\n\n{text.strip()}", color=discord.Color.gold())
            embed.set_thumbnail(url=member.display_avatar.url)
            await welcome_chan.send(content=member.mention, embed=embed)
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # ── Auto-Mod Check ─────────────────────────────────────────────────────
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

    # Process traditional commands if any are still defined via bot.command() (optional)
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
