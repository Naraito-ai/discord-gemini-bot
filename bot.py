import os
import json
import discord
from google import genai
from google.genai import types
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# ── Keep-alive server so Render / UptimeRobot can ping us ──────────────────
_flask_app = Flask(__name__)

@_flask_app.route('/')
def _home():
    return "✅ Discord bot is alive!"

def keep_alive():
    t = Thread(target=lambda: _flask_app.run(host='0.0.0.0', port=8080), daemon=True)
    t.start()
# ───────────────────────────────────────────────────────────────────────────

# Load environment variables from .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Google Gemini client (new SDK)
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Use discord.Intents.default() with message_content intent enabled
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# Gemini system prompt
SYSTEM_PROMPT = """You are a Discord server structure generator. 
The user will describe a Discord server they want. 
Return ONLY a raw JSON object with no explanation, no markdown, no code fences, no backticks. 
Just the raw JSON and nothing else.

The JSON must follow this exact structure:
{
  "roles": [
    {"name": "string", "color": "#HEXCODE", "hoist": true or false}
  ],
  "categories": [
    {
      "name": "string",
      "channels": [
        {"name": "string", "type": "text or voice"}
      ]
    }
  ]
}

Rules:
- color must always be a valid hex code like #FF5733, never a color name
- channel names must be lowercase with hyphens instead of spaces, no special characters
- role names can have normal capitalization
- hoist true means the role shows separately in the member list
- always include at least one Admin role with color #FF0000 and hoist true
- always include a General category with a general-chat text channel"""


@client.event
async def on_ready():
    print(f"Bot logged in as {client.user} (ID: {client.user.id})")
    print("------")


@client.event
async def on_message(message):
    # Avoid responding to ourselves
    if message.author == client.user:
        return

    # Only respond to messages starting with !setup
    if not message.content.startswith("!setup"):
        return

    # Permission check
    if not message.author.guild_permissions.manage_guild:
        await message.reply("❌ You don't have permission to do this.")
        return

    # Extract description
    description = message.content[len("!setup"):].strip()
    if not description:
        await message.reply("❌ Please provide a description. Example: `!setup gaming server with clips and chat`")
        return

    # 1. Acknowledge immediately
    status_message = await message.channel.send("⚙️ Setting up your server, please wait...")

    # 2. Call Gemini
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

        # Strip markdown code fences if present
        if raw_response.startswith("```"):
            lines = raw_response.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
            raw_response = "\n".join(lines).strip()

    except Exception as e:
        print(f"Gemini API error: {e}")
        await status_message.edit(content="❌ Failed to connect to Gemini API. Check your GEMINI_API_KEY.")
        return

    # 3. Parse JSON
    try:
        data = json.loads(raw_response)
    except Exception as e:
        print(f"JSON parse error: {e}\nRaw: {raw_response}")
        await status_message.edit(content="❌ Couldn't understand that, try rephrasing your description.")
        return

    roles_created = []
    categories_created = []
    channels_created = []
    guild = message.guild

    try:
        # 4a. Create roles
        for role_data in data.get("roles", []):
            role_name = role_data.get("name")
            if not role_name:
                continue
            if discord.utils.get(guild.roles, name=role_name):
                continue  # skip existing

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

        # 4b. Create categories & channels
        for cat_data in data.get("categories", []):
            cat_name = cat_data.get("name")
            if not cat_name:
                continue

            category = discord.utils.get(guild.categories, name=cat_name)
            if category is None:
                category = await guild.create_category(name=cat_name, reason="Gemini Discord Bot Setup")
            categories_created.append(category.name)

            for chan_data in cat_data.get("channels", []):
                chan_name = chan_data.get("name")
                chan_type = chan_data.get("type", "text")
                if not chan_name:
                    continue
                if discord.utils.get(category.channels, name=chan_name):
                    continue  # skip existing

                if chan_type == "text":
                    new_chan = await guild.create_text_channel(name=chan_name, category=category, reason="Gemini Discord Bot Setup")
                    channels_created.append(f"#{new_chan.name}")
                elif chan_type == "voice":
                    new_chan = await guild.create_voice_channel(name=chan_name, category=category, reason="Gemini Discord Bot Setup")
                    channels_created.append(f"🔊 {new_chan.name}")

    except Exception as e:
        print(f"Creation error: {e}")
        await status_message.edit(content=f"❌ An error occurred during setup: {e}")
        return

    # Delete status message
    try:
        await status_message.delete()
    except Exception:
        pass

    # 5. Confirmation embed
    embed = discord.Embed(title="✅ Server Setup Complete", color=discord.Color.green())
    embed.add_field(name="Roles Created",      value=", ".join(roles_created)                          or "None", inline=False)
    embed.add_field(name="Categories Created", value=", ".join(dict.fromkeys(categories_created))      or "None", inline=False)
    embed.add_field(name="Channels Created",   value=", ".join(channels_created)                       or "None", inline=False)
    embed.set_footer(text="Powered by Gemini")

    await message.channel.send(embed=embed)


if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_token_here":
        print("Error: DISCORD_TOKEN is not set in .env file.")
    elif not GEMINI_API_KEY or GEMINI_API_KEY == "your_key_here":
        print("Error: GEMINI_API_KEY is not set in .env file.")
    else:
        print("Starting Discord bot...")
        keep_alive()
        client.run(DISCORD_TOKEN)
