import os
import json
import asyncio
import logging
import discord
from google import genai
from google.genai import types
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

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

# Configure Google Gemini client
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Resource Manager for tracking AI-created entities (enables clean !teardown)
RESOURCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guild_resources.json")

class ResourceManager:
    def __init__(self, filepath):
        self.filepath = filepath
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving resource file: {e}")

    def add_resource(self, guild_id, res_type, res_id):
        gid = str(guild_id)
        if gid not in self.data:
            self.data[gid] = {"roles": [], "categories": [], "channels": [], "config": {}}
        if res_id not in self.data[gid][res_type]:
            self.data[gid][res_type].append(res_id)
        self._save()

    def get_config(self, guild_id, key, default=None):
        gid = str(guild_id)
        if gid not in self.data or "config" not in self.data[gid]:
            return default
        return self.data[gid]["config"].get(key, default)

    def set_config(self, guild_id, key, value):
        gid = str(guild_id)
        if gid not in self.data:
            self.data[gid] = {"roles": [], "categories": [], "channels": [], "config": {}}
        if "config" not in self.data[gid]:
            self.data[gid]["config"] = {}
        self.data[gid]["config"][key] = value
        self._save()

    async def teardown_guild(self, guild):
        gid = str(guild.id)
        stats = {"roles": 0, "categories": 0, "channels": 0}
        if gid not in self.data:
            return stats

        logger.info(f"Starting teardown for guild {guild.name} ({gid})...")

        # 1. Delete channels first
        for cid in self.data[gid].get("channels", []):
            channel = guild.get_channel(cid)
            if channel:
                try:
                    await channel.delete(reason="Gemini Bot Teardown")
                    stats["channels"] += 1
                except Exception as e:
                    logger.warning(f"Failed to delete channel {cid}: {e}")

        # 2. Delete categories
        for cid in self.data[gid].get("categories", []):
            cat = guild.get_channel(cid)
            if cat:
                try:
                    await cat.delete(reason="Gemini Bot Teardown")
                    stats["categories"] += 1
                except Exception as e:
                    logger.warning(f"Failed to delete category {cid}: {e}")

        # 3. Delete roles
        for rid in self.data[gid].get("roles", []):
            role = guild.get_role(rid)
            if role and role != guild.default_role:
                try:
                    await role.delete(reason="Gemini Bot Teardown")
                    stats["roles"] += 1
                except Exception as e:
                    logger.warning(f"Failed to delete role {rid}: {e}")

        logger.info(f"Teardown completed for {guild.name}: {stats}")

        self.data[gid] = {"roles": [], "categories": [], "channels": []}
        self._save()
        return stats

    async def nuke_guild(self, guild):
        gid = str(guild.id)
        stats = {"roles": 0, "categories": 0, "channels": 0}
        logger.info(f"Starting TOTAL NUKE for guild {guild.name} ({gid})...")

        # Create a clean default channel so server isn't 100% empty
        clean_channel = None
        try:
            clean_channel = await guild.create_text_channel(
                name="💥-server-nuked",
                topic="Server wiped clean by Gemini Bot !nuke command. Ready for !setup!",
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

        self.data[gid] = {"roles": [], "categories": [], "channels": []}
        self._save()
        return stats, clean_channel

resource_manager = ResourceManager(RESOURCE_FILE)

# Configure Discord Client
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)


def call_ai_generation(prompt, system_instruction, json_mode=False):
    # Detect which API key is available
    groq_key = os.getenv("GROQ_API_KEY", "").strip().strip('"').strip("'")
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    
    # If GEMINI_API_KEY is actually a Groq key (starts with gsk_)
    if gemini_key.startswith("gsk_"):
        groq_key = gemini_key
        gemini_key = ""
        
    if groq_key:
        logger.info(f"Using Groq API for content generation (JSON Mode: {json_mode})")
        import requests
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
            
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        res_data = r.json()
        return res_data["choices"][0]["message"]["content"]
        
    elif gemini_key:
        logger.info(f"Using Gemini API for content generation (JSON Mode: {json_mode})")
        c = genai.Client(api_key=gemini_key)
        if json_mode:
            resp = c.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.3
                ),
            )
        else:
            resp = c.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.3
                ),
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


# ── Interactive UI Views ───────────────────────────────────────────────────
class SetupConfirmView(discord.ui.View):
    def __init__(self, author, guild, plan_data, original_message):
        super().__init__(timeout=180.0)
        self.author = author
        self.guild = guild
        self.plan_data = plan_data
        self.original_message = original_message

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
        
        stats = await resource_manager.teardown_guild(self.guild)
        
        embed = discord.Embed(title="🗑️ Teardown Complete", color=discord.Color.red())
        embed.add_field(name="Channels Deleted", value=str(stats['channels']), inline=True)
        embed.add_field(name="Categories Deleted", value=str(stats['categories']), inline=True)
        embed.add_field(name="Roles Deleted", value=str(stats['roles']), inline=True)
        embed.set_footer(text="Powered by Gemini")
        
        await interaction.channel.send(embed=embed)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(content="🚫 **Teardown cancelled.**", embed=None, view=self)
        self.stop()
# ───────────────────────────────────────────────────────────────────────────


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
        
        stats, clean_channel = await resource_manager.nuke_guild(self.guild)
        
        embed = discord.Embed(title="💥 Server Completely Nuked", description="All old channels, categories, and roles have been wiped clean!", color=discord.Color.red())
        embed.add_field(name="Channels Deleted", value=str(stats['channels']), inline=True)
        embed.add_field(name="Categories Deleted", value=str(stats['categories']), inline=True)
        embed.add_field(name="Roles Deleted", value=str(stats['roles']), inline=True)
        embed.add_field(name="Next Step", value="Type `!setup <description>` right here to build your new server on a 100% clean slate!", inline=False)
        embed.set_footer(text="Powered by Gemini")
        
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


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒")
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

    @discord.ui.button(label="🎟️ Open Support Ticket", style=discord.ButtonStyle.primary, emoji="🎟️")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        
        category = discord.utils.get(guild.categories, name="🎟️ SUPPORT TICKETS")
        if not category:
            try:
                category = await guild.create_category("🎟️ SUPPORT TICKETS", reason="Ticket System Category")
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to create ticket category: {e}", ephemeral=True)
                return

        chan_name = f"ticket-{user.name.lower()}"
        if discord.utils.get(category.text_channels, name=chan_name):
            await interaction.response.send_message("❌ You already have an open support ticket!", ephemeral=True)
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
            await interaction.response.send_message(f"✅ Your support ticket has been opened: {ticket_chan.mention}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            await interaction.response.send_message(f"❌ Could not create ticket room: {e}", ephemeral=True)
# ───────────────────────────────────────────────────────────────────────────


async def build_server_structure(guild, data, response_channel):
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
            resource_manager.add_resource(guild.id, "roles", new_role.id)
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
                resource_manager.add_resource(guild.id, "categories", category.id)
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
                    resource_manager.add_resource(guild.id, "channels", new_chan.id)
                    logger.info(f"Created text channel: #{new_chan.name} (Topic: {chan_topic})")
                elif chan_type == "voice":
                    new_chan = await guild.create_voice_channel(
                        name=chan_name,
                        category=category,
                        overwrites=chan_overrides,
                        reason="Gemini Discord Bot Setup"
                    )
                    channels_created.append(f"🔊 {new_chan.name}")
                    resource_manager.add_resource(guild.id, "channels", new_chan.id)
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

    embed.set_footer(text="Powered by Gemini • Use !teardown to reset AI-created items")

    await response_channel.send(embed=embed)


@client.event
async def on_ready():
    logger.info(f"Bot logged in as {client.user} (ID: {client.user.id})")
    logger.info("------")


@client.event
async def on_member_join(member):
    guild = member.guild
    style = resource_manager.get_config(guild.id, "welcome", "off")
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
        text = call_ai_generation(prompt, "You are a professional, friendly Discord welcome greeter.")
        if text:
            embed = discord.Embed(title=f"👋 Welcome to {guild.name}!", description=f"{member.mention}\n\n{text.strip()}", color=discord.Color.gold())
            embed.set_thumbnail(url=member.display_avatar.url)
            await welcome_chan.send(content=member.mention, embed=embed)
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # ── Auto-Mod Check ─────────────────────────────────────────────────────
    if not message.author.bot:
        automod_enabled = resource_manager.get_config(message.guild.id, "automod", True)
        if automod_enabled:
            content = message.content.strip()
            if content and not content.startswith("!"):
                # 1. Instant Local Filter (Free and uses ZERO Gemini API quota)
                import re
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
                        warn_msg = await message.channel.send(f"⚠️ {message.author.mention}, your message was deleted by **Gemini Auto-Mod (Local Shield)** for violating community safety rules.")
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
                automod_mode = resource_manager.get_config(message.guild.id, "automod_mode", "local")
                if automod_mode == "ai":
                    try:
                        prompt = f"Analyze if this chat message contains extreme toxicity, slurs, hate speech, severe harassment, or scam/phishing links: '{content}'."
                        text = call_ai_generation(prompt, "You are an expert content moderator. Respond with ONLY the word SAFE or TOXIC. Do not add any other text.")
                        result = text.strip().upper()
                        if "TOXIC" in result:
                                try:
                                    await message.delete()
                                    warn_msg = await message.channel.send(f"⚠️ {message.author.mention}, your message was deleted by **Gemini AI Auto-Mod** for violating community safety rules.")
                                    await asyncio.sleep(5)
                                    await warn_msg.delete()
                                    
                                    mod_log = discord.utils.get(message.guild.text_channels, name="🚨-mod-logs") or discord.utils.get(message.guild.text_channels, name="mod-logs") or discord.utils.get(message.guild.text_channels, name="🚨-admin-chat")
                                    if mod_log:
                                        log_embed = discord.Embed(title="🚨 Auto-Mod Flagged Message", color=discord.Color.red())
                                        log_embed.add_field(name="Author", value=f"{message.author} ({message.author.id})", inline=True)
                                        log_embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                                        log_embed.add_field(name="Deleted Content", value=content[:1000], inline=False)
                                        log_embed.add_field(name="Reason", value="Flagged as TOXIC by Gemini AI", inline=True)
                                        await mod_log.send(embed=log_embed)
                                    return
                                except Exception as del_err:
                                    logger.error(f"Auto-Mod AI delete failed: {del_err}")
                                    return
                    except Exception as e:
                        # Log error but don't spam the chat with 429 quota exceptions!
                        logger.error(f"Auto-Mod Gemini evaluation error: {e}")



    try:
        # Command: !help
        if message.content.strip().lower() in ("!help", "!setuphelp"):
            logger.info(f"Help command triggered by {message.author} in {message.guild.name}")
            embed = discord.Embed(title="🤖 Discord Gemini Server Builder & Community Shield", description="An all-in-one AI Architect, Auto-Mod, and Community Management Bot powered by Gemini 2.5 Flash!", color=discord.Color.blurple())
            embed.add_field(name="🏗️ **AI Server Architect**", value="• `!setup <desc>` — Build full server with roles & topics\n• `!addcategory <desc>` — AI builds & adds 1 category\n• `!teardown` — Delete only bot-created items\n• `!nuke` — **DANGER:** Wipe entire server clean", inline=False)
            embed.add_field(name="🛡️ **Security & Moderation**", value="• `!automod <on/off>` — AI Toxic & Scam Shield\n• `!lockdown <on/off>` — Emergency chat freeze\n• `!purge <num>` — Instant spam/chat cleaner", inline=False)
            embed.add_field(name="💬 **Community & Engagement**", value="• `!welcome <style/off>` — AI Dynamic Join Greeter\n• `!announce <topic>` — AI Announcement Writer\n• `!ticket` — Create interactive Support Ticket button\n• `!suggest <idea>` — Interactive suggestion box\n• `!poll <question> | <opt1> | <opt2>` — Reaction poll", inline=False)
            embed.set_footer(text="Powered by Google Gemini 2.5 Flash")
            await message.reply(embed=embed)
            return

        # Command: !automod <on/off>
        if message.content.strip().lower().startswith("!automod"):
            if not message.author.guild_permissions.manage_guild:
                await message.reply("❌ You need **Manage Server** permissions to configure Auto-Mod.")
                return
            arg = message.content[len("!automod"):].strip().lower()
            if arg in ("on", "true", "enable"):
                resource_manager.set_config(message.guild.id, "automod", True)
                resource_manager.set_config(message.guild.id, "automod_mode", "local")
                await message.reply("🧠 **Auto-Mod is now ON (Local Shield)!**\nScanning real-time chat instantly for curse words, slurs, and spam links without using API key quota.")
            elif arg == "ai":
                resource_manager.set_config(message.guild.id, "automod", True)
                resource_manager.set_config(message.guild.id, "automod_mode", "ai")
                await message.reply("🧠 **Auto-Mod set to AI Mode!**\nReal-time messages will be scanned using Google Gemini AI. *(Note: This uses your Gemini API key quota!)*")
            elif arg == "local":
                resource_manager.set_config(message.guild.id, "automod", True)
                resource_manager.set_config(message.guild.id, "automod_mode", "local")
                await message.reply("🛡️ **Auto-Mod set to Local Mode.**\nUsing instant local filter to save API quota.")
            elif arg in ("off", "false", "disable"):
                resource_manager.set_config(message.guild.id, "automod", False)
                await message.reply("🛡️ **Auto-Mod disabled.**")
            else:
                enabled = "ON" if resource_manager.get_config(message.guild.id, "automod", True) else "OFF"
                mode = resource_manager.get_config(message.guild.id, "automod_mode", "local").upper()
                await message.reply(f"ℹ️ **Auto-Mod Status:** `{enabled}` (Mode: `{mode}`)\n\nUsage:\n• `!automod on` / `!automod off` — Enable/Disable Auto-Mod\n• `!automod local` — Use free local filter (instant)\n• `!automod ai` — Use advanced Gemini AI toxicity scanner")
            return

        # Command: !testautomod <text>
        if message.content.strip().lower().startswith("!testautomod"):
            if not message.author.guild_permissions.manage_guild:
                await message.reply("❌ You need **Manage Server** permissions to test Auto-Mod.")
                return
            test_text = message.content[len("!testautomod"):].strip()
            if not test_text:
                await message.reply("❌ Please provide the text to test.\nExample: `!testautomod you are a stupid idiot`")
                return
            status_msg = await message.reply("🔍 Evaluating text with Gemini Auto-Mod AI...")
            try:
                prompt = f"Analyze if this chat message contains extreme toxicity, slurs, hate speech, severe harassment, or scam/phishing links: '{test_text}'."
                text = call_ai_generation(prompt, "You are an expert content moderator. Respond with ONLY the word SAFE or TOXIC. Do not add any other text.")
                result = text.strip().upper()
                if "TOXIC" in result:
                    await status_msg.edit(content=f"🚨 **Gemini Auto-Mod Result:** `TOXIC`\n\n*If sent by a regular member, this message would have been **deleted**, and logged in `#mod-logs`!*")
                else:
                    await status_msg.edit(content=f"✅ **Gemini Auto-Mod Result:** `SAFE`\n\n*This message would be allowed in chat.*")
            except Exception as e:
                await status_msg.edit(content=f"❌ Evaluation failed: {e}")
            return

        # Command: !welcome <style>
        if message.content.strip().lower().startswith("!welcome"):
            if not message.author.guild_permissions.manage_guild:
                await message.reply("❌ You need **Manage Server** permissions to configure Welcome Architect.")
                return
            style = message.content[len("!welcome"):].strip()
            if not style or style.lower() in ("off", "disable", "false"):
                resource_manager.set_config(message.guild.id, "welcome", "off")
                await message.reply("👋 **AI Welcome Greeter disabled.**")
            else:
                resource_manager.set_config(message.guild.id, "welcome", style)
                await message.reply(f"👋 **AI Welcome Greeter Enabled!**\nPersonality/Style set to: **`{style}`**.\nWhen new members join, Gemini will dynamically generate a unique greeting in your welcome/general channel!")
            return

        # Command: !announce <topic>
        if message.content.strip().lower().startswith("!announce"):
            if not message.author.guild_permissions.mention_everyone and not message.author.guild_permissions.manage_messages:
                await message.reply("❌ You need **Manage Messages** or **Mention Everyone** permissions to make AI announcements.")
                return
            topic = message.content[len("!announce"):].strip()
            if not topic:
                await message.reply("❌ Please specify what to announce.\nExample: `!announce weekend valorant tournament with $100 prize pool`")
                return
            status_msg = await message.reply("📢 Crafting announcement with Gemini AI...")
            try:
                prompt = f"Write an exciting, professional Discord server announcement about: '{topic}'. Format with emojis, bold headers, bullet points, and make it highly engaging! Return ONLY the announcement text."
                text = call_ai_generation(prompt, "You are a professional Discord community manager.")
                if text:
                    embed = discord.Embed(title="📢 Official Announcement", description=text.strip(), color=discord.Color.brand_red())
                    embed.set_footer(text=f"Announced by {message.author.display_name} • Powered by AI", icon_url=message.author.display_avatar.url)
                    await status_msg.delete()
                    await message.channel.send(content="@everyone", embed=embed)
                    await message.delete()
            except Exception as e:
                await status_msg.edit(content=f"❌ Failed to generate announcement: {e}")
            return

        # Command: !lockdown <on/off>
        if message.content.strip().lower().startswith("!lockdown"):
            if not message.author.guild_permissions.manage_channels and not message.author.guild_permissions.administrator:
                await message.reply("❌ You need **Manage Channels** or **Administrator** permissions to toggle server lockdown.")
                return
            arg = message.content[len("!lockdown"):].strip().lower()
            if arg == "on":
                locked = 0
                for chan in message.guild.text_channels:
                    try:
                        await chan.set_permissions(message.guild.default_role, send_messages=False, reason="Emergency Lockdown")
                        locked += 1
                    except Exception:
                        pass
                await message.reply(f"🚨 **EMERGENCY LOCKDOWN INITIATED!** 🚨\nLocked `{locked}` public text channels. Regular members cannot type until you run `!lockdown off`.")
            elif arg == "off":
                unlocked = 0
                for chan in message.guild.text_channels:
                    try:
                        await chan.set_permissions(message.guild.default_role, send_messages=None, reason="Lockdown Lifted")
                        unlocked += 1
                    except Exception:
                        pass
                await message.reply(f"🔓 **LOCKDOWN LIFTED!** Unlocked `{unlocked}` channels. Public chat is reopened.")
            else:
                await message.reply("Usage: `!lockdown on` or `!lockdown off`")
            return

        # Command: !purge <number> or !clear <number>
        if message.content.strip().lower().startswith("!purge") or message.content.strip().lower().startswith("!clear"):
            if not message.author.guild_permissions.manage_messages:
                await message.reply("❌ You need **Manage Messages** permissions to purge chat.")
                return
            parts = message.content.split()
            if len(parts) < 2 or not parts[1].isdigit():
                await message.reply("❌ Please specify the number of messages to delete.\nExample: `!purge 30`")
                return
            num = min(int(parts[1]), 100)
            try:
                deleted = await message.channel.purge(limit=num + 1)
                conf = await message.channel.send(f"🧹 Successfully purged `{len(deleted) - 1}` messages.")
                await asyncio.sleep(4)
                await conf.delete()
            except Exception as e:
                await message.reply(f"❌ Purge failed: {e}")
            return

        # Command: !ticket or !setuptickets
        if message.content.strip().lower() in ("!ticket", "!setuptickets"):
            if not message.author.guild_permissions.manage_guild:
                await message.reply("❌ You need **Manage Server** permissions to setup the ticket panel.")
                return
            embed = discord.Embed(
                title="🎟️ Support & Help Desk",
                description="Need assistance from our moderators or staff team?\n\nClick the **🎟️ Open Support Ticket** button below to create a private, secure chat room with our team!",
                color=discord.Color.blurple()
            )
            embed.set_footer(text="Private 1-on-1 Support • Powered by Gemini Bot")
            await message.channel.send(embed=embed, view=TicketView())
            await message.delete()
            return

        # Command: !suggest <idea>
        if message.content.strip().lower().startswith("!suggest"):
            idea = message.content[len("!suggest"):].strip()
            if not idea:
                await message.reply("❌ Please include your suggestion!\nExample: `!suggest add an anime movie night every Saturday`")
                return
            sug_chan = discord.utils.get(message.guild.text_channels, name="💡-suggestions") or discord.utils.get(message.guild.text_channels, name="suggestions") or discord.utils.get(message.guild.text_channels, name="server-suggestions") or message.channel
            embed = discord.Embed(title="💡 Community Suggestion", description=f"**{idea}**", color=discord.Color.gold())
            embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
            embed.set_footer(text="Status: [UNDER REVIEW] • Vote with 👍 or 👎 below!")
            sug_msg = await sug_chan.send(embed=embed)
            await sug_msg.add_reaction("👍")
            await sug_msg.add_reaction("👎")
            if sug_chan.id != message.channel.id:
                await message.reply(f"✅ Your suggestion was posted in {sug_chan.mention}!")
            await message.delete()
            return

        # Command: !poll <question> | <opt1> | <opt2>
        if message.content.strip().lower().startswith("!poll"):
            content = message.content[len("!poll"):].strip()
            if "|" not in content:
                await message.reply("❌ Please format your poll with `|` separating question and options!\nExample: `!poll What game should we play? | Valorant | CS2 | Apex Legends`")
                return
            parts = [p.strip() for p in content.split("|") if p.strip()]
            if len(parts) < 3:
                await message.reply("❌ Please provide a question and at least 2 options!")
                return
            question = parts[0]
            options = parts[1:11]
            emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            desc_lines = [f"{emojis[i]} **{opt}**" for i, opt in enumerate(options)]
            embed = discord.Embed(title=f"📊 {question}", description="\n\n".join(desc_lines), color=discord.Color.teal())
            embed.set_footer(text=f"Poll created by {message.author.display_name} • React to vote!", icon_url=message.author.display_avatar.url)
            poll_msg = await message.channel.send(embed=embed)
            for i in range(len(options)):
                await poll_msg.add_reaction(emojis[i])
            await message.delete()
            return

        # Command: !addcategory <description>
        if message.content.strip().lower().startswith("!addcategory"):
            if not message.author.guild_permissions.manage_guild:
                await message.reply("❌ You need **Manage Server** permissions to use this command.")
                return
            desc = message.content[len("!addcategory"):].strip()
            if not desc:
                await message.reply("❌ Please describe the category.\nExample: `!addcategory VIP anime watch party lounge with 4k stream rooms`")
                return
            status_msg = await message.reply(f"✨ Designing category `{desc}` with AI...")
            try:
                sys_inst = f"The user wants to create a single Discord category: '{desc}'. Return ONLY a raw JSON object with this structure: {{\"categories\": [{{\"name\": \"Category Name\", \"private_for\": [], \"channels\": [{{\"name\": \"chan-name\", \"type\": \"text\", \"topic\": \"chan topic\"}}, {{\"name\": \"voice-chan\", \"type\": \"voice\"}}]}}]}}. Do not include markdown or code blocks. Just JSON."
                text = call_ai_generation(desc, sys_inst, json_mode=True)
                data = json.loads(text.strip())
                await status_msg.edit(content="⚙️ **Building new category and channels...**")
                await build_server_structure(message.guild, data, message.channel)
                await status_msg.delete()
            except Exception as e:
                await status_msg.edit(content=f"❌ Failed to build category: {e}")
            return

        # Command: !help
        if message.content.strip().lower() in ("!help", "!setuphelp"):
            logger.info(f"Help command triggered by {message.author} in {message.guild.name}")
            embed = discord.Embed(title="🤖 Discord Gemini Server Builder", description="Generate and manage your Discord server layout using AI!", color=discord.Color.blurple())
            embed.add_field(name="✨ `!setup <description>`", value="Generate a server structure preview from text. Includes emojis, channel topics, roles, and private channels.\n*Example:* `!setup gaming guild with clips, lfg, welcome lounge, and private staff channels`", inline=False)
            embed.add_field(name="🗑️ `!teardown` or `!cleanup`", value="Delete only the roles, categories, and channels created by this bot.", inline=False)
            embed.add_field(name="💥 `!nuke` or `!cleanall`", value="**⚠️ DANGER:** Wipes **ALL** channels, categories, and roles in the entire server for a complete reset!", inline=False)
            embed.set_footer(text="Requires Manage Server permissions")
            await message.reply(embed=embed)
            return

        # Command: !teardown or !cleanup
        if message.content.strip().lower() in ("!teardown", "!cleanup"):
            logger.info(f"Teardown command triggered by {message.author} in {message.guild.name}")
            if not message.author.guild_permissions.manage_guild:
                await message.reply("❌ You need **Manage Server** permissions to use this command.")
                return

            embed = discord.Embed(
                title="⚠️ Confirm Teardown",
                description="Are you sure you want to delete all roles, categories, and channels created by the Gemini Bot in this server?",
                color=discord.Color.orange()
            )
            view = TeardownConfirmView(message.author, message.guild)
            await message.reply(embed=embed, view=view)
            return

        # Command: !nuke or !cleanall
        if message.content.strip().lower() in ("!nuke", "!cleanall", "!resetserver"):
            logger.info(f"Nuke command triggered by {message.author} in {message.guild.name}")
            if not message.author.guild_permissions.administrator:
                await message.reply("❌ You need **Administrator** permissions to use the complete server nuke command.")
                return

            embed = discord.Embed(
                title="⚠️ DANGER: COMPLETE SERVER NUKE ⚠️",
                description="Are you sure you want to delete **EVERY SINGLE CHANNEL, CATEGORY, AND ROLE** in this entire server?\n\nThis will wipe all existing rooms and create a fresh `#💥-server-nuked` channel so you can run `!setup` on a 100% clean slate.\n\n**THIS CANNOT BE UNDONE!**",
                color=discord.Color.red()
            )
            view = NukeConfirmView(message.author, message.guild)
            await message.reply(embed=embed, view=view)
            return

        # Command: !setup <description>
        if message.content.startswith("!setup"):
            logger.info(f"Setup command triggered by {message.author} in {message.guild.name}: {message.content}")
            if not message.author.guild_permissions.manage_guild:
                await message.reply("❌ You need **Manage Server** permissions to use this command.")
                return

            description = message.content[len("!setup"):].strip()
            if not description:
                await message.reply("❌ Please provide a description.\nExample: `!setup community server for anime lovers with art showcase and VIP lounge`")
                return

            status_message = await message.reply("✨ Generating server plan with AI (including channel topics & roles)... Please wait.")
            try:
                raw_response = call_ai_generation(description, SYSTEM_PROMPT, json_mode=True)
                raw_response = raw_response.strip()

                if raw_response.startswith("```"):
                    lines = raw_response.splitlines()
                    lines = lines[1:] if lines[0].startswith("```") else lines
                    lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
                    raw_response = "\n".join(lines).strip()
            except Exception as e:
                logger.error(f"AI API error during setup: {e}")
                await status_message.edit(content=f"❌ **AI API Connection Failed:** `{e}`\n\n💡 *Make sure your API key in Render environment variables is valid!*")
                return

            try:
                data = json.loads(raw_response)
            except Exception as e:
                logger.error(f"JSON parse error: {e}\nRaw response: {raw_response}")
                await status_message.edit(content="❌ Couldn't understand the generated structure. Try rephrasing your prompt.")
                return

            # Prepare Preview Embed
            roles_summary = [f"`{r['name']}` ({r.get('color', '#fff')})" for r in data.get("roles", [])]
            categories_summary = []
            total_channels = 0

            for cat in data.get("categories", []):
                chans = cat.get("channels", [])
                total_channels += len(chans)
                private_tag = " 🔒" if cat.get("private_for") else ""
                
                # Highlight channels that have topics generated
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

            await status_message.delete()
            view = SetupConfirmView(message.author, message.guild, data, message)
            await message.channel.send(embed=embed, view=view)

    except Exception as e:
        logger.exception(f"Unhandled exception in on_message: {e}")
        try:
            await message.reply(f"⚠️ An unexpected error occurred: `{e}`")
        except Exception:
            pass


if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_token_here":
        print("Error: DISCORD_TOKEN is not set in .env file.")
    elif not GEMINI_API_KEY and not os.getenv("GROQ_API_KEY"):
        print("Error: Neither GEMINI_API_KEY nor GROQ_API_KEY is set in environment variables.")
    else:
        print("Starting Discord bot...")
        keep_alive()
        client.run(DISCORD_TOKEN)
