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

# Gemini system prompt with Emoji, Topics, and Private Channel support
SYSTEM_PROMPT = """You are an expert Discord server structure generator and community architect. 
The user will describe a Discord server layout they want. 
Return ONLY a raw JSON object with no explanation, no markdown code fences, no backticks. 
Just the raw JSON and nothing else.

The JSON must follow this exact structure:
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

    # Helper to generate permission overrides
    def get_overrides(private_roles_list):
        if not private_roles_list:
            return None
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
        except Exception as e:
            logger.error(f"Failed to create category '{cat_name}': {e}")
            continue

        for chan_data in cat_data.get("channels", []):
            chan_name = chan_data.get("name")
            chan_type = chan_data.get("type", "text")
            chan_topic = chan_data.get("topic")
            if not chan_name:
                continue
            
            try:
                if discord.utils.get(category.channels, name=chan_name):
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

    logger.info(f"Server structure build completed for {guild.name}")

    # Send confirmation embed
    embed = discord.Embed(title="✅ Server Setup Complete", color=discord.Color.green())
    embed.add_field(name="Roles Created",      value=", ".join(roles_created)                          or "None", inline=False)
    embed.add_field(name="Categories Created", value=", ".join(dict.fromkeys(categories_created))      or "None", inline=False)
    embed.add_field(name="Channels Created",   value=", ".join(channels_created[:20]) + ("..." if len(channels_created) > 20 else "") or "None", inline=False)
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
        live_api_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
        if not live_api_key:
            return
        c = genai.Client(api_key=live_api_key)
        prompt = f"Write a short, warm, and exciting 2-sentence welcome greeting for user '{member.display_name}' joining our Discord community '{guild.name}'. Write it in the personality/style of: '{style}'. Use emojis and format nicely!"
        resp = c.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        if resp and resp.text:
            embed = discord.Embed(title=f"👋 Welcome to {guild.name}!", description=f"{member.mention}\n\n{resp.text.strip()}", color=discord.Color.gold())
            embed.set_thumbnail(url=member.display_avatar.url)
            await welcome_chan.send(content=member.mention, embed=embed)
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # ── Auto-Mod Check ─────────────────────────────────────────────────────
    if not message.author.bot and not message.author.guild_permissions.manage_messages:
        automod_enabled = resource_manager.get_config(message.guild.id, "automod", False)
        if automod_enabled:
            content_lower = message.content.lower()
            scam_keywords = ["discord-gift", "free nitro", "steamcommunity-free", "free robux", "airdrop claim", "crypto giveaway", "@everyone click here"]
            hate_keywords = ["nigger", "faggot", "retard", "kill yourself", "kys", "genocide"]
            
            if any(w in content_lower for w in scam_keywords + hate_keywords):
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
                        log_embed.add_field(name="Deleted Content", value=message.content[:1000], inline=False)
                        await mod_log.send(embed=log_embed)
                    return
                except Exception as e:
                    logger.error(f"Auto-Mod deletion error: {e}")

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
                await message.reply("🧠 **Gemini AI Auto-Mod is now ON!**\nScanning real-time chat for extreme toxicity, hate speech, and scam/phishing links.")
            elif arg in ("off", "false", "disable"):
                resource_manager.set_config(message.guild.id, "automod", False)
                await message.reply("🛡️ **Auto-Mod disabled.**")
            else:
                status = "ON" if resource_manager.get_config(message.guild.id, "automod", False) else "OFF"
                await message.reply(f"ℹ️ **Auto-Mod Status:** `{status}`\nUsage: `!automod on` or `!automod off`")
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
                live_api_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
                c = genai.Client(api_key=live_api_key)
                prompt = f"Write an exciting, professional Discord server announcement about: '{topic}'. Format with emojis, bold headers, bullet points, and make it highly engaging! Return ONLY the announcement text."
                resp = c.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                if resp and resp.text:
                    embed = discord.Embed(title="📢 Official Announcement", description=resp.text.strip(), color=discord.Color.brand_red())
                    embed.set_footer(text=f"Announced by {message.author.display_name} • Powered by Gemini AI", icon_url=message.author.display_avatar.url)
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
            status_msg = await message.reply(f"✨ Designing category `{desc}` with Gemini AI...")
            try:
                live_api_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
                c = genai.Client(api_key=live_api_key)
                prompt = f"The user wants to create a single Discord category: '{desc}'. Return ONLY a raw JSON object with this structure: {{\"categories\": [{{\"name\": \"Category Name\", \"private_for\": [], \"channels\": [{{\"name\": \"chan-name\", \"type\": \"text\", \"topic\": \"chan topic\"}}, {{\"name\": \"voice-chan\", \"type\": \"voice\"}}]}}]}}. Do not include markdown or code blocks. Just JSON."
                resp = c.models.generate_content(model="gemini-2.5-flash", contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json"))
                data = json.loads(resp.text.strip())
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

            status_message = await message.reply("✨ Generating server plan with Gemini AI (including channel topics & roles)... Please wait.")

            live_api_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
            if not live_api_key:
                logger.error("GEMINI_API_KEY missing in environment variables.")
                await status_message.edit(content="❌ **Missing `GEMINI_API_KEY` on Render!**\nPlease go to your **Render Dashboard** → Select this service → **Environment** tab → Add Environment Variable:\n• **Key**: `GEMINI_API_KEY`\n• **Value**: *(Your API key starting with `AIzaSy...` or `AQ.` from https://aistudio.google.com/app/apikey)*")
                return

            if not (live_api_key.startswith("AIza") or live_api_key.startswith("AQ.")):
                masked_key = live_api_key[:8] + "..." if len(live_api_key) >= 8 else live_api_key
                logger.error(f"Invalid GEMINI_API_KEY format: starts with {masked_key}")
                await status_message.edit(content=f"❌ **Invalid API Key Format on Render!**\nRender is currently using a key starting with `{masked_key}`.\nGoogle Gemini API keys typically start with `AIzaSy...` or `AQ.`.\n\n⚠️ *If you just changed your key in Render, please go to your Render Dashboard and click **Manual Deploy → Clear Build Cache & Deploy** (or Restart Service) so your bot picks up the new key!*")
                return

            try:
                dynamic_client = genai.Client(api_key=live_api_key)
                response = dynamic_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=description,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                    ),
                )
                raw_response = response.text.strip()

                if raw_response.startswith("```"):
                    lines = raw_response.splitlines()
                    lines = lines[1:] if lines[0].startswith("```") else lines
                    lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
                    raw_response = "\n".join(lines).strip()

            except Exception as e:
                logger.error(f"Gemini API error during setup: {e}")
                await status_message.edit(content=f"❌ **Gemini API Connection Failed:** `{e}`\n\n💡 *Make sure your `GEMINI_API_KEY` is a valid API key from https://aistudio.google.com/app/apikey.*")
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
    elif not GEMINI_API_KEY or GEMINI_API_KEY == "your_key_here":
        print("Error: GEMINI_API_KEY is not set in .env file.")
    else:
        print("Starting Discord bot...")
        keep_alive()
        client.run(DISCORD_TOKEN)
