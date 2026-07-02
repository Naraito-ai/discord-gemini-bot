import os
import json
import discord
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Google Generative AI
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("Warning: GEMINI_API_KEY is not set in the environment.")

# Use discord.Intents.default() with message_content intent enabled
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# Gemini system prompt to use
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

    # Only allow users who have Manage Guild permission to use !setup
    # Reply with "❌ You don't have permission to do this." otherwise
    if not message.author.guild_permissions.manage_guild:
        await message.reply("❌ You don't have permission to do this.")
        return

    # Extract user's server description
    description = message.content[len("!setup"):].strip()
    if not description:
        await message.reply("❌ Please provide a description of the server you want to set up. Example: `!setup gaming server with chat and clips`")
        return

    # 1. Immediately replies with "⚙️ Setting up your server, please wait..." to acknowledge the command
    status_message = await message.channel.send("⚙️ Setting up your server, please wait...")

    # 2. Sends the description to Gemini gemini-2.0-flash
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=SYSTEM_PROMPT,
            generation_config={"response_mime_type": "application/json"}
        )
        
        response = model.generate_content(description)
        raw_response = response.text.strip()
        
        # Clean up any potential markdown code blocks if the model included them
        if raw_response.startswith("```"):
            lines = raw_response.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw_response = "\n".join(lines).strip()
            
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        await status_message.edit(content="❌ Failed to connect to Gemini API. Please check your GEMINI_API_KEY and try again.")
        return

    # 3. Parses the JSON response (with try/except wrapping json.loads())
    try:
        data = json.loads(raw_response)
    except Exception as e:
        print(f"JSON parsing error: {e}")
        print(f"Raw response: {raw_response}")
        await status_message.edit(content="❌ Couldn't understand that, try rephrasing your description.")
        return

    # Keep track of created items for the confirmation embed
    roles_created = []
    categories_created = []
    channels_created = []

    guild = message.guild

    try:
        # 4. Creates everything on the Discord server

        # Creating roles
        for role_data in data.get("roles", []):
            role_name = role_data.get("name")
            if not role_name:
                continue

            # Before creating a role, check if a role with the same name already exists in the server — if it does, skip it
            existing_role = discord.utils.get(guild.roles, name=role_name)
            if existing_role is not None:
                continue

            color_hex = role_data.get("color", "#FFFFFF")
            # Parse the hex color string into a discord.Colour object using discord.Colour(int(hex.strip('#'), 16))
            try:
                color_val = int(color_hex.strip('#'), 16)
                colour_obj = discord.Colour(color_val)
            except ValueError:
                colour_obj = discord.Colour.default()

            hoist_val = role_data.get("hoist", False)

            new_role = await guild.create_role(
                name=role_name,
                colour=colour_obj,
                hoist=hoist_val,
                reason="Gemini Discord Bot Setup"
            )
            roles_created.append(new_role.name)

        # Creating categories and channels
        for cat_data in data.get("categories", []):
            cat_name = cat_data.get("name")
            if not cat_name:
                continue

            # Before creating a category, check if one with the same name already exists — if it does, use the existing one instead of creating a duplicate
            category = discord.utils.get(guild.categories, name=cat_name)
            if category is None:
                category = await guild.create_category(name=cat_name, reason="Gemini Discord Bot Setup")
            
            # Record category name
            categories_created.append(category.name)

            for chan_data in cat_data.get("channels", []):
                chan_name = chan_data.get("name")
                chan_type = chan_data.get("type", "text")
                if not chan_name:
                    continue

                # Before creating a channel inside a category, check if a channel with the same name already exists in that category — if it does, skip it
                existing_channel = discord.utils.get(category.channels, name=chan_name)
                if existing_channel is not None:
                    continue

                # Always pass the category object when creating channels so they appear inside the right category
                # For "type": "text" use guild.create_text_channel()
                # For "type": "voice" use guild.create_voice_channel()
                if chan_type == "text":
                    new_chan = await guild.create_text_channel(
                        name=chan_name,
                        category=category,
                        reason="Gemini Discord Bot Setup"
                    )
                    channels_created.append(f"#{new_chan.name}")
                elif chan_type == "voice":
                    new_chan = await guild.create_voice_channel(
                        name=chan_name,
                        category=category,
                        reason="Gemini Discord Bot Setup"
                    )
                    channels_created.append(f"🔊 {new_chan.name}")

    except Exception as e:
        print(f"Error during creation of roles/channels: {e}")
        await status_message.edit(content=f"❌ An error occurred during setup: {e}")
        return

    # Delete the temporary status message
    try:
        await status_message.delete()
    except Exception:
        pass

    # 5. Sends a confirmation embed
    embed = discord.Embed(
        title="✅ Server Setup Complete",
        color=discord.Color.green()
    )

    # De-duplicate category names in case there were multiple loops (though dict.fromkeys does it nicely)
    categories_created_uniq = list(dict.fromkeys(categories_created))

    roles_text = ", ".join(roles_created) if roles_created else "None"
    categories_text = ", ".join(categories_created_uniq) if categories_created_uniq else "None"
    channels_text = ", ".join(channels_created) if channels_created else "None"

    embed.add_field(name="Roles Created", value=roles_text, inline=False)
    embed.add_field(name="Categories Created", value=categories_text, inline=False)
    embed.add_field(name="Channels Created", value=channels_text, inline=False)
    embed.set_footer(text="Powered by Gemini")

    await message.channel.send(embed=embed)

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_token_here":
        print("Error: DISCORD_TOKEN is not set in .env file.")
    elif not GEMINI_API_KEY or GEMINI_API_KEY == "your_key_here":
        print("Error: GEMINI_API_KEY is not set in .env file.")
    else:
        print("Starting Discord bot...")
        client.run(DISCORD_TOKEN)
