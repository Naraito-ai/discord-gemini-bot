import os
import json
import logging
import datetime
import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks

# ── Directory & Logger Setup ──────────────────────────────────────────────────
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
CONFIG_PATH = os.path.join(CONFIG_DIR, "auto_bump_config.json")
LOG_PATH = os.path.join(LOGS_DIR, "auto_bump.log")

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Auto-bump dedicated file logger
bump_logger = logging.getLogger("Sweety.AutoBump")
bump_logger.setLevel(logging.INFO)

if not bump_logger.handlers:
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("[AUTO-BUMP] %(asctime)s - [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    bump_logger.addHandler(fh)

DEFAULT_CONFIG = {
    "enabled": True,
    "channel_id": None,
    "fallback_channel_id": None,
    "mode": "text",  # "text" sends "/bump" directly
    "ping_role_id": None,  # Optional role ID to mention
    "interval_hours": 2,
    "retry_on_fail": True,
    "retry_delay_minutes": 5,
    "max_retries": 3,
    "last_bump_timestamp": None,
    "next_bump_timestamp": None,
    "total_bumps_sent": 0,
    "bump_text": "/bump"
}


def load_config() -> dict:
    """Loads auto-bump config from JSON file, creating it if missing."""
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge missing keys
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            # If still on old !d bump default, update to /bump
            if data.get("bump_text") == "!d bump":
                data["bump_text"] = "/bump"
                data["mode"] = "text"
            return data
    except Exception as e:
        bump_logger.error(f"Failed to load config: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config_data: dict):
    """Saves auto-bump config safely to JSON file."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
    except Exception as e:
        bump_logger.error(f"Failed to save config: {e}")


class AutoBump(commands.Cog):
    """Automated 2-hour server bump integration for Sweety."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = load_config()
        self.auto_bump_task.start()
        bump_logger.info("AutoBump Cog initialized and task loop started.")

    def cog_unload(self):
        self.auto_bump_task.cancel()
        bump_logger.info("AutoBump Cog unloaded and task loop cancelled.")

    async def execute_bump(self, guild: discord.Guild = None) -> tuple[bool, str]:
        """Core bump execution logic with channel discovery, fallback, and retries."""
        self.config = load_config()
        if not self.config.get("enabled", True):
            return False, "Auto-bump is currently disabled."

        channel_id = self.config.get("channel_id")
        fallback_id = self.config.get("fallback_channel_id")

        if not channel_id and not fallback_id:
            msg = "No valid bump channel configured. Use `/setbumpchannel` to set one."
            bump_logger.warning(msg)
            return False, msg

        # Resolve primary or fallback channel
        target_channel = None
        if channel_id:
            target_channel = self.bot.get_channel(int(channel_id))
            if not target_channel:
                try:
                    target_channel = await self.bot.fetch_channel(int(channel_id))
                except Exception:
                    target_channel = None

        if not target_channel and fallback_id:
            bump_logger.warning(f"Primary channel {channel_id} unavailable. Attempting fallback channel {fallback_id}...")
            target_channel = self.bot.get_channel(int(fallback_id))
            if not target_channel:
                try:
                    target_channel = await self.bot.fetch_channel(int(fallback_id))
                except Exception:
                    target_channel = None

        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            msg = f"Cannot access configured channel (ID: {channel_id}). Please check bot permissions."
            bump_logger.error(msg)
            return False, msg

        # Verify permissions
        perms = target_channel.permissions_for(target_channel.guild.me)
        if not perms.send_messages:
            msg = f"Missing Send Messages permission in #{target_channel.name} ({target_channel.id})"
            bump_logger.error(f"[ERROR] {msg}")
            return False, msg

        # Prepare Content based on configured Mode
        mode = self.config.get("mode", "embed")
        ping_role_id = self.config.get("ping_role_id")
        mention_str = f"<@&{ping_role_id}> " if ping_role_id else ""
        now = datetime.datetime.now(datetime.timezone.utc)
        
        try:
            if mode == "text":
                bump_text = self.config.get("bump_text", "!d bump")
                content = f"{mention_str}{bump_text}".strip()
                await target_channel.send(content)
            else:
                embed = discord.Embed(
                    title="🚀 Time to Bump the Server!",
                    description=(
                        "The 2-hour Disboard cooldown has refreshed!\n\n"
                        "👉 **Please type `/bump` in this channel to boost our server to the top of discovery lists!**"
                    ),
                    color=discord.Color.from_rgb(88, 101, 242)
                )
                embed.add_field(name="⏱️ Cooldown", value="2 Hours", inline=True)
                embed.add_field(name="📈 Growth", value="Boosts server visibility", inline=True)
                embed.set_footer(text="Sweety Auto-Bump Reminder • Bump regularly for maximum members!")
                
                content = mention_str.strip() if mention_str else None
                await target_channel.send(content=content, embed=embed)
            
            # Update stats
            self.config["last_bump_timestamp"] = int(now.timestamp())
            next_time = now + datetime.timedelta(hours=self.config.get("interval_hours", 2))
            self.config["next_bump_timestamp"] = int(next_time.timestamp())
            self.config["total_bumps_sent"] = self.config.get("total_bumps_sent", 0) + 1
            save_config(self.config)

            success_msg = f"[SUCCESS] Bump dispatched to #{target_channel.name} in {target_channel.guild.name} (Mode: {mode})"
            bump_logger.info(success_msg)
            return True, f"✅ Successfully dispatched bump to {target_channel.mention}!"
            
        except Exception as e:
            err_msg = f"Failed to send bump: {e}"
            bump_logger.error(f"[ERROR] {err_msg}")
            return False, err_msg

    @tasks.loop(hours=2)
    async def auto_bump_task(self):
        """Automated loop triggering server bump every 2 hours."""
        await self.bot.wait_until_ready()
        bump_logger.info("Executing scheduled 2-hour auto-bump task...")
        
        success, result_msg = await self.execute_bump()
        
        # Retry loop on failure if enabled
        if not success and self.config.get("retry_on_fail", True):
            max_retries = self.config.get("max_retries", 3)
            delay_mins = self.config.get("retry_delay_minutes", 5)
            
            for attempt in range(1, max_retries + 1):
                bump_logger.info(f"[INFO] Retrying bump in {delay_mins} minutes (attempt {attempt}/{max_retries})...")
                await asyncio.sleep(delay_mins * 60)
                retry_success, _ = await self.execute_bump()
                if retry_success:
                    bump_logger.info(f"[SUCCESS] Bump succeeded on retry attempt {attempt}/{max_retries}.")
                    break

    @auto_bump_task.before_loop
    async def before_auto_bump_task(self):
        """Wait for bot gateway readiness before starting loop."""
        await self.bot.wait_until_ready()

    # ── Slash Commands ──────────────────────────────────────────────────────────

    @app_commands.command(name="setbumpchannel", description="Configure the channel where Sweety will auto-bump every 2 hours")
    @app_commands.describe(channel="The text channel to send auto-bumps to (defaults to current channel)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setbumpchannel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        """Sets the active auto-bump channel."""
        target = channel or interaction.channel
        
        # Verify permissions
        perms = target.permissions_for(interaction.guild.me)
        if not perms.send_messages:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {target.mention}. Please grant **Send Messages** permission and try again.",
                ephemeral=True
            )
            return

        self.config["channel_id"] = target.id
        self.config["enabled"] = True
        
        now = datetime.datetime.now(datetime.timezone.utc)
        next_time = now + datetime.timedelta(hours=self.config.get("interval_hours", 2))
        self.config["next_bump_timestamp"] = int(next_time.timestamp())
        save_config(self.config)

        bump_logger.info(f"Bump channel set to #{target.name} ({target.id}) by {interaction.user}")

        embed = discord.Embed(
            title="🚀 Auto-Bump Channel Configured",
            description=f"Auto-bump has been set to **{target.mention}**!\nSweety will automatically bump your server every **{self.config.get('interval_hours', 2)} hours**.",
            color=discord.Color.green()
        )
        embed.add_field(name="📍 Channel", value=target.mention, inline=True)
        embed.add_field(name="🎨 Mode", value=f"`{self.config.get('mode', 'embed').capitalize()}`", inline=True)
        embed.add_field(name="⏰ Next Scheduled Bump", value=f"<t:{int(next_time.timestamp())}:R>", inline=True)
        embed.set_footer(text="Use /setbumpmode to change format or /manualbump to test")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setbumpmode", description="Choose between a rich reminder embed or raw text command for auto-bump")
    @app_commands.describe(
        mode="The bump dispatch mode",
        raw_text="Custom text to send if mode is 'raw text' (defaults to '!d bump')"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Rich Reminder Embed (Recommended for /bump)", value="embed"),
            app_commands.Choice(name="Raw Text Command (!d bump)", value="text")
        ]
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setbumpmode(self, interaction: discord.Interaction, mode: app_commands.Choice[str], raw_text: str = None):
        """Switches bump mode between rich embed reminder and raw text."""
        self.config = load_config()
        self.config["mode"] = mode.value
        if raw_text:
            self.config["bump_text"] = raw_text.strip()
            
        save_config(self.config)
        
        embed = discord.Embed(
            title="⚙️ Bump Mode Updated",
            description=f"Auto-bump format set to: **{mode.name}**",
            color=discord.Color.blue()
        )
        if mode.value == "text":
            embed.add_field(name="📝 Text Command", value=f"`{self.config.get('bump_text', '!d bump')}`", inline=False)
        else:
            embed.add_field(name="💡 Why Embed?", value="Discord prevents bots from running other bots' slash commands directly, so the rich embed reminds your community to type `/bump`.", inline=False)
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setbumpping", description="Configure a role to ping when it's time to bump")
    @app_commands.describe(role="The role to mention (leave empty to disable pings)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setbumpping(self, interaction: discord.Interaction, role: discord.Role = None):
        """Sets or clears the auto-bump mention role."""
        self.config = load_config()
        if role:
            self.config["ping_role_id"] = role.id
            desc = f"Sweety will now mention {role.mention} on each 2-hour bump reminder."
        else:
            self.config["ping_role_id"] = None
            desc = "Role mentions for auto-bump have been **disabled**."
            
        save_config(self.config)
        
        embed = discord.Embed(
            title="🔔 Bump Ping Configuration",
            description=desc,
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bumpstatus", description="View current auto-bump status, next scheduled bump, and statistics")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def bumpstatus(self, interaction: discord.Interaction):
        """Shows current auto-bump configuration and next scheduled bump."""
        self.config = load_config()
        
        channel_id = self.config.get("channel_id")
        channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        
        enabled = self.config.get("enabled", True)
        mode = self.config.get("mode", "embed")
        interval = self.config.get("interval_hours", 2)
        total_bumps = self.config.get("total_bumps_sent", 0)
        last_bump = self.config.get("last_bump_timestamp")
        next_bump = self.config.get("next_bump_timestamp")
        ping_role_id = self.config.get("ping_role_id")

        embed = discord.Embed(
            title="📊 Sweety Auto-Bump Status",
            color=discord.Color.blue() if enabled else discord.Color.greyple()
        )
        
        embed.add_field(name="⚙️ Status", value="🟢 **Active & Running**" if enabled else "🔴 **Disabled**", inline=True)
        embed.add_field(name="📍 Channel", value=channel.mention if channel else "`Not configured`", inline=True)
        embed.add_field(name="🎨 Format", value=f"`{mode.capitalize()}`", inline=True)
        
        last_str = f"<t:{last_bump}:R>" if last_bump else "`Never`"
        next_str = f"<t:{next_bump}:R> (<t:{next_bump}:T>)" if next_bump else "`Pending next loop`"
        
        embed.add_field(name="🕒 Last Bump", value=last_str, inline=True)
        embed.add_field(name="⏳ Next Bump", value=next_str, inline=True)
        embed.add_field(name="📈 Total Bumps", value=f"`{total_bumps}` sent", inline=True)
        
        if ping_role_id:
            embed.add_field(name="🔔 Ping Role", value=f"<@&{ping_role_id}>", inline=True)
            
        embed.set_footer(text="Sweety Auto-Bump Module • Use /manualbump to test")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="manualbump", description="Manually trigger an immediate server bump test")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def manualbump(self, interaction: discord.Interaction):
        """Forces an immediate manual bump."""
        await interaction.response.defer(thinking=True)
        
        success, message = await self.execute_bump(interaction.guild)
        if success:
            embed = discord.Embed(
                title="✅ Manual Bump Dispatched",
                description=message,
                color=discord.Color.green()
            )
            embed.set_footer(text="Next automatic bump scheduled in 2 hours")
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Manual Bump Failed",
                description=f"{message}\n\nPlease check `/setbumpchannel` or ensure Sweety has permissions.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="bumphelp", description="Learn how to configure and use Sweety's 2-hour Auto-Bump feature")
    async def bumphelp(self, interaction: discord.Interaction):
        """Displays help and usage guide for Auto-Bump."""
        embed = discord.Embed(
            title="🚀 Sweety Auto-Bump Integration Guide",
            description="Sweety keeps your server active on Discord discovery lists every **2 hours** automatically!",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="🛠️ Quick Setup",
            value="1. **`/setbumpchannel #channel`** — Select your bump channel.\n2. **`/setbumpmode`** — Choose between **Rich Reminder Embed** or **Raw Text** (`!d bump`).\n3. **`/setbumpping [role]`** — Optionally ping a `@Bumper` or `@here` role.\n4. **`/manualbump`** — Test an instant bump dispatch.",
            inline=False
        )
        embed.add_field(
            name="💡 Why Embed vs Text?",
            value="Discord's security API forbids bots from triggering other bots' slash commands directly. The **Rich Embed** reminds your members to run `/bump`, while **Raw Text** sends text commands like `!d bump` for classic bots.",
            inline=False
        )
        embed.set_footer(text="Sweety 24/7 Cloud Engine")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoBump(bot))
