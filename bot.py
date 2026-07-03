import os
import json
import asyncio
import discord
from google import genai
from google.genai import types
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

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
            print(f"Error saving resource file: {e}")

    def add_resource(self, guild_id, res_type, res_id):
        gid = str(guild_id)
        if gid not in self.data:
            self.data[gid] = {"roles": [], "categories": [], "channels": []}
        if res_id not in self.data[gid][res_type]:
            self.data[gid][res_type].append(res_id)
        self._save()

    async def teardown_guild(self, guild):
        gid = str(guild.id)
        stats = {"roles": 0, "categories": 0, "channels": 0}
        if gid not in self.data:
            return stats

        # 1. Delete channels first
        for cid in self.data[gid].get("channels", []):
            channel = guild.get_channel(cid)
            if channel:
                try:
                    await channel.delete(reason="Gemini Bot Teardown")
                    stats["channels"] += 1
                except Exception as e:
                    print(f"Failed to delete channel {cid}: {e}")

        # 2. Delete categories
        for cid in self.data[gid].get("categories", []):
            cat = guild.get_channel(cid)
            if cat:
                try:
                    await cat.delete(reason="Gemini Bot Teardown")
                    stats["categories"] += 1
                except Exception as e:
                    print(f"Failed to delete category {cid}: {e}")

        # 3. Delete roles
        for rid in self.data[gid].get("roles", []):
            role = guild.get_role(rid)
            if role and role != guild.default_role:
                try:
                    await role.delete(reason="Gemini Bot Teardown")
                    stats["roles"] += 1
                except Exception as e:
                    print(f"Failed to delete role {rid}: {e}")

        self.data[gid] = {"roles": [], "categories": [], "channels": []}
        self._save()
        return stats

resource_manager = ResourceManager(RESOURCE_FILE)

# Configure Discord Client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Gemini system prompt with Emoji and Private Channel support
SYSTEM_PROMPT = """You are an expert Discord server structure generator. 
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
        {"name": "string", "type": "text or voice", "private_for": ["RoleName"]}
      ]
    }
  ]
}

Rules:
- color must always be a valid hex code like #FF5733, #5865F2, #2ECC71, never a color name.
- channel names for text channels must be lowercase with hyphens instead of spaces. Include fitting emojis at the beginning (e.g., "📣-announcements", "💬-general-chat", "🎮-lfg").
- category names should be uppercase or well-formatted, preferably preceded by an emoji (e.g., "📌 INFORMATION", "💬 TEXT CHANNELS", "🔒 ADMIN ONLY").
- role names can have normal capitalization (e.g., "Admin", "Moderator", "VIP Member").
- hoist true means the role shows separately in the member list. Set hoist to true for staff or important roles.
- always include at least one staff/admin role with an appropriate color and hoist set to true.
- private_for is an optional list of role names that should have exclusive access to this category or channel. For example, if a category or channel is meant only for staff/admins, include "private_for": ["Admin", "Moderator"].
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


async def build_server_structure(guild, data, response_channel):
    roles_created = []
    categories_created = []
    channels_created = []
    role_objects = {}

    try:
        # 1. Create Roles
        for role_data in data.get("roles", []):
            role_name = role_data.get("name")
            if not role_name:
                continue
            
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

        # 2. Create Categories & Channels
        for cat_data in data.get("categories", []):
            cat_name = cat_data.get("name")
            if not cat_name:
                continue

            category = discord.utils.get(guild.categories, name=cat_name)
            cat_overrides = get_overrides(cat_data.get("private_for"))

            if category is None:
                category = await guild.create_category(
                    name=cat_name,
                    overrides=cat_overrides,
                    reason="Gemini Discord Bot Setup"
                )
                categories_created.append(category.name)
                resource_manager.add_resource(guild.id, "categories", category.id)

            for chan_data in cat_data.get("channels", []):
                chan_name = chan_data.get("name")
                chan_type = chan_data.get("type", "text")
                if not chan_name:
                    continue
                
                if discord.utils.get(category.channels, name=chan_name):
                    continue

                chan_overrides = get_overrides(chan_data.get("private_for")) or cat_overrides

                if chan_type == "text":
                    new_chan = await guild.create_text_channel(
                        name=chan_name,
                        category=category,
                        overrides=chan_overrides,
                        reason="Gemini Discord Bot Setup"
                    )
                    channels_created.append(f"#{new_chan.name}")
                    resource_manager.add_resource(guild.id, "channels", new_chan.id)
                elif chan_type == "voice":
                    new_chan = await guild.create_voice_channel(
                        name=chan_name,
                        category=category,
                        overrides=chan_overrides,
                        reason="Gemini Discord Bot Setup"
                    )
                    channels_created.append(f"🔊 {new_chan.name}")
                    resource_manager.add_resource(guild.id, "channels", new_chan.id)

    except Exception as e:
        print(f"Creation error: {e}")
        await response_channel.send(f"❌ An error occurred during setup: {e}")
        return

    # Send confirmation embed
    embed = discord.Embed(title="✅ Server Setup Complete", color=discord.Color.green())
    embed.add_field(name="Roles Created",      value=", ".join(roles_created)                          or "None", inline=False)
    embed.add_field(name="Categories Created", value=", ".join(dict.fromkeys(categories_created))      or "None", inline=False)
    embed.add_field(name="Channels Created",   value=", ".join(channels_created[:20]) + ("..." if len(channels_created) > 20 else "") or "None", inline=False)
    embed.set_footer(text="Powered by Gemini • Use !teardown to reset AI-created items")

    await response_channel.send(embed=embed)


@client.event
async def on_ready():
    print(f"Bot logged in as {client.user} (ID: {client.user.id})")
    print("------")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Command: !help
    if message.content.strip().lower() in ("!help", "!setuphelp"):
        embed = discord.Embed(title="🤖 Discord Gemini Server Builder", description="Generate and manage your Discord server layout using AI!", color=discord.Color.blurple())
        embed.add_field(name="✨ `!setup <description>`", value="Generate a server structure preview from text. Includes emojis, roles, and private channels.\n*Example:* `!setup gaming guild with clips, lfg, and private staff channels`", inline=False)
        embed.add_field(name="🗑️ `!teardown` or `!cleanup`", value="Delete all roles, categories, and channels created by this bot in this server.", inline=False)
        embed.set_footer(text="Requires Manage Server permissions")
        await message.reply(embed=embed)
        return

    # Command: !teardown or !cleanup
    if message.content.strip().lower() in ("!teardown", "!cleanup"):
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

    # Command: !setup <description>
    if message.content.startswith("!setup"):
        if not message.author.guild_permissions.manage_guild:
            await message.reply("❌ You need **Manage Server** permissions to use this command.")
            return

        description = message.content[len("!setup"):].strip()
        if not description:
            await message.reply("❌ Please provide a description.\nExample: `!setup community server for anime lovers with art showcase and VIP lounge`")
            return

        status_message = await message.reply("✨ Generating server plan with Gemini AI... Please wait.")

        if not GEMINI_API_KEY or not gemini_client:
            await status_message.edit(content="❌ **Missing `GEMINI_API_KEY` on Render!**\nPlease go to your **Render Dashboard** → Select this service → **Environment** tab → Add Environment Variable:\n• **Key**: `GEMINI_API_KEY`\n• **Value**: *(Your API key starting with `AIzaSy...` from https://aistudio.google.com/app/apikey)*")
            return

        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
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
            print(f"Gemini API error: {e}")
            await status_message.edit(content=f"❌ **Gemini API Connection Failed:** `{e}`\n\n💡 *Tip: If you see `401 UNAUTHENTICATED`, make sure your `GEMINI_API_KEY` in Render starts with `AIzaSy...` (get a free key at https://aistudio.google.com/app/apikey).*")
            return

        try:
            data = json.loads(raw_response)
        except Exception as e:
            print(f"JSON parse error: {e}\nRaw: {raw_response}")
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
            categories_summary.append(f"**{cat.get('name')}**{private_tag} ({len(chans)} channels)")

        embed = discord.Embed(title="📋 Server Structure Preview", description="Review the AI-generated layout below before creating channels and roles.", color=discord.Color.gold())
        embed.add_field(name="🎭 Roles to Create", value=", ".join(roles_summary) or "None", inline=False)
        embed.add_field(name=f"📁 Categories & Channels ({total_channels} channels total)", value="\n".join(categories_summary) or "None", inline=False)
        embed.set_footer(text="Click Confirm & Build below to execute this plan.")

        await status_message.delete()
        view = SetupConfirmView(message.author, message.guild, data, message)
        await message.channel.send(embed=embed, view=view)


if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_token_here":
        print("Error: DISCORD_TOKEN is not set in .env file.")
    elif not GEMINI_API_KEY or GEMINI_API_KEY == "your_key_here":
        print("Error: GEMINI_API_KEY is not set in .env file.")
    else:
        print("Starting Discord bot...")
        keep_alive()
        client.run(DISCORD_TOKEN)
