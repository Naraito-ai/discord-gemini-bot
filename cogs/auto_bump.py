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

bump_logger = logging.getLogger("Sweety.BumpReminder")
bump_logger.setLevel(logging.INFO)

if not bump_logger.handlers:
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("[BUMP-REMINDER] %(asctime)s - [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    bump_logger.addHandler(fh)

DISBOARD_BOT_ID = 302050872383242240

DEFAULT_CONFIG = {
    "enabled": True,
    "channel_id": None,
    "ping_role_id": None,
    "last_bump_timestamp": None,
    "next_bump_timestamp": None,
    "last_bumper_id": None,
    "total_reminders_sent": 0,
    "total_bumps_detected": 0
}


def load_config() -> dict:
    """Loads auto-bump config from JSON file, creating it if missing."""
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
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


class BumpReminder(commands.Cog):
    """Smart 2-Hour Disboard Bump Reminder and Cooldown Tracker for Sweety."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = load_config()
        self.reminder_check_task.start()
        bump_logger.info("BumpReminder Cog initialized and checker task started.")

    def cog_unload(self):
        self.reminder_check_task.cancel()
        bump_logger.info("BumpReminder Cog unloaded.")

    async def send_reminder(self) -> tuple[bool, str]:
        """Dispatches the 2-hour bump reminder card with optional role mention."""
        self.config = load_config()
        if not self.config.get("enabled", True):
            return False, "Bump reminders are currently disabled."

        channel_id = self.config.get("channel_id")
        if not channel_id:
            msg = "No bump channel configured. Use `/setbumpchannel` to set one."
            bump_logger.warning(msg)
            return False, msg

        target_channel = self.bot.get_channel(int(channel_id))
        if not target_channel:
            try:
                target_channel = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                target_channel = None

        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            msg = f"Cannot access configured channel (ID: {channel_id}). Please check bot permissions."
            bump_logger.error(msg)
            return False, msg

        perms = target_channel.permissions_for(target_channel.guild.me)
        if not perms.send_messages:
            msg = f"Missing Send Messages permission in #{target_channel.name} ({target_channel.id})"
            bump_logger.error(f"[ERROR] {msg}")
            return False, msg

        ping_role_id = self.config.get("ping_role_id")
        mention_str = f"<@&{ping_role_id}> " if ping_role_id else ""

        now = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            title="🚀 Time to Bump the Server!",
            description=(
                "The **2-hour Disboard cooldown** has refreshed!\n\n"
                "👉 Please type **`/bump`** in this channel to boost our server to the top of discovery lists!"
            ),
            color=discord.Color.from_rgb(88, 101, 242)
        )
        embed.add_field(name="⏱️ Cooldown", value="Every 2 Hours", inline=True)
        embed.add_field(name="📈 Benefits", value="Brings new active members", inline=True)
        embed.set_footer(text="Sweety Bump Manager • Type /bump to boost!")

        try:
            content = mention_str.strip() if mention_str else None
            await target_channel.send(content=content, embed=embed)

            # Mark reminder sent
            self.config["total_reminders_sent"] = self.config.get("total_reminders_sent", 0) + 1
            # Push next check 2 hours ahead so it doesn't repeatedly ping if unbumped
            next_time = now + datetime.timedelta(hours=2)
            self.config["next_bump_timestamp"] = int(next_time.timestamp())
            save_config(self.config)

            success_msg = f"[SUCCESS] Reminder sent to #{target_channel.name} in {target_channel.guild.name}"
            bump_logger.info(success_msg)
            return True, f"✅ Successfully sent bump reminder to {target_channel.mention}!"

        except Exception as e:
            err_msg = f"Failed to send reminder: {e}"
            bump_logger.error(f"[ERROR] {err_msg}")
            return False, err_msg

    @tasks.loop(minutes=1)
    async def reminder_check_task(self):
        """Checks every minute if the 2-hour cooldown has elapsed and sends the reminder."""
        await self.bot.wait_until_ready()
        self.config = load_config()

        if not self.config.get("enabled", True) or not self.config.get("channel_id"):
            return

        next_bump = self.config.get("next_bump_timestamp")
        if not next_bump:
            return

        now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        if now_ts >= next_bump:
            bump_logger.info("2-hour cooldown elapsed. Triggering bump reminder...")
            await self.send_reminder()

    @reminder_check_task.before_loop
    async def before_reminder_check_task(self):
        await self.bot.wait_until_ready()

    # ── Smart Disboard Detection Listener ───────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Automatically detects when a user runs /bump and Disboard responds successfully."""
        # Check if message is from Disboard (by ID or Bot Name)
        is_disboard = (
            (message.author.id == DISBOARD_BOT_ID) or 
            (message.author.bot and "disboard" in message.author.name.lower())
        )
        if not is_disboard:
            return

        # Check for Disboard bump confirmation text / embed
        is_successful_bump = False
        content_lower = message.content.lower()

        if "bump done" in content_lower or "check it on disboard" in content_lower:
            is_successful_bump = True
        elif message.embeds:
            for emb in message.embeds:
                desc = (emb.description or "").lower()
                title = (emb.title or "").lower()
                if "bump done" in desc or "bump done" in title or "check it on disboard" in desc or "please wait another" in desc:
                    is_successful_bump = True
                    break

        if is_successful_bump:
            now = datetime.datetime.now(datetime.timezone.utc)
            next_time = now + datetime.timedelta(hours=2)
            
            self.config = load_config()
            self.config["last_bump_timestamp"] = int(now.timestamp())
            self.config["next_bump_timestamp"] = int(next_time.timestamp())
            self.config["total_bumps_detected"] = self.config.get("total_bumps_detected", 0) + 1
            if message.interaction and message.interaction.user:
                self.config["last_bumper_id"] = message.interaction.user.id
            save_config(self.config)

            bump_logger.info(f"✅ Disboard bump detected in #{message.channel.name}! Next reminder scheduled at {next_time} (in 2 hours).")
            
            # Optional friendly reaction
            try:
                await message.add_reaction("⭐")
            except Exception:
                pass

    # ── Clean Slash Commands ───────────────────────────────────────────────────

    @app_commands.command(name="setbumpchannel", description="Set the channel and optional notification role for 2-hour bump reminders")
    @app_commands.describe(
        channel="The text channel where bump reminders will be sent (defaults to current channel)",
        role="Optional role to ping when the 2-hour cooldown ends (e.g. @Bumper or @here)"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setbumpchannel(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel = None,
        role: discord.Role = None
    ):
        """Configures the bump reminder channel and ping role."""
        target = channel or interaction.channel
        
        perms = target.permissions_for(interaction.guild.me)
        if not perms.send_messages:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {target.mention}. Please grant **Send Messages** permission and try again.",
                ephemeral=True
            )
            return

        self.config = load_config()
        self.config["channel_id"] = target.id
        self.config["enabled"] = True
        if role is not None:
            self.config["ping_role_id"] = role.id

        now = datetime.datetime.now(datetime.timezone.utc)
        next_time = now + datetime.timedelta(hours=2)
        self.config["next_bump_timestamp"] = int(next_time.timestamp())
        save_config(self.config)

        bump_logger.info(f"Bump reminder channel set to #{target.name} ({target.id}) by {interaction.user}")

        embed = discord.Embed(
            title="🚀 Bump Reminder Configured",
            description=f"Sweety is now tracking Disboard bumps for **{interaction.guild.name}**!\nWhenever 2 hours pass without a bump, Sweety will post a reminder card.",
            color=discord.Color.green()
        )
        embed.add_field(name="📍 Channel", value=target.mention, inline=True)
        embed.add_field(name="🔔 Ping Role", value=role.mention if role else "`None (Embed only)`", inline=True)
        embed.add_field(name="⏰ Next Reminder", value=f"<t:{int(next_time.timestamp())}:R>", inline=True)
        embed.set_footer(text="Use /testbump to send an instant preview or /bumpstatus to check live timer")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bumpstatus", description="View live 2-hour Disboard cooldown countdown and bump statistics")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def bumpstatus(self, interaction: discord.Interaction):
        """Shows current bump status, countdown timer, and statistics."""
        self.config = load_config()

        channel_id = self.config.get("channel_id")
        channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        
        enabled = self.config.get("enabled", True)
        last_bump = self.config.get("last_bump_timestamp")
        next_bump = self.config.get("next_bump_timestamp")
        ping_role_id = self.config.get("ping_role_id")
        total_reminders = self.config.get("total_reminders_sent", 0)
        total_bumps = self.config.get("total_bumps_detected", 0)
        last_bumper_id = self.config.get("last_bumper_id")

        embed = discord.Embed(
            title="📊 Disboard Bump Reminder Status",
            color=discord.Color.blue() if enabled else discord.Color.greyple()
        )

        embed.add_field(name="⚙️ System Status", value="🟢 **Active & Tracking**" if enabled else "🔴 **Disabled**", inline=True)
        embed.add_field(name="📍 Reminder Channel", value=channel.mention if channel else "`Not configured`", inline=True)
        embed.add_field(name="🔔 Ping Role", value=f"<@&{ping_role_id}>" if ping_role_id else "`None`", inline=True)

        last_str = f"<t:{last_bump}:R>" if last_bump else "`No bumps recorded yet`"
        next_str = f"<t:{next_bump}:R> (<t:{next_bump}:T>)" if next_bump else "`Pending bump`"

        embed.add_field(name="🕒 Last Bump", value=last_str, inline=True)
        embed.add_field(name="⏳ Next Reminder", value=next_str, inline=True)
        if last_bumper_id:
            embed.add_field(name="⭐ Last Bumper", value=f"<@{last_bumper_id}>", inline=True)
        else:
            embed.add_field(name="⭐ Last Bumper", value="`None`", inline=True)

        embed.add_field(name="📈 Reminders Sent", value=f"`{total_reminders}`", inline=True)
        embed.add_field(name="🎉 Bumps Detected", value=f"`{total_bumps}`", inline=True)

        embed.set_footer(text="Sweety 24/7 Bump Manager • Type /bump to boost!")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="testbump", description="Send an immediate test bump reminder to preview the channel & role ping")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def testbump(self, interaction: discord.Interaction):
        """Sends an immediate test reminder card."""
        await interaction.response.defer(thinking=True)
        
        success, message = await self.send_reminder()
        if success:
            embed = discord.Embed(
                title="✅ Test Reminder Sent",
                description=f"{message}\nYour community will receive this card every 2 hours whenever Disboard is ready.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Test Reminder Failed",
                description=f"{message}\n\nPlease run `/setbumpchannel #channel` to configure the channel.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="bumptoggle", description="Enable or disable the 2-hour Disboard bump reminder system")
    @app_commands.describe(enabled="Turn the reminder system ON (True) or OFF (False)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def bumptoggle(self, interaction: discord.Interaction, enabled: bool):
        """Toggles the auto-reminder system on or off."""
        self.config = load_config()
        self.config["enabled"] = enabled
        save_config(self.config)

        status_text = "🟢 **Enabled**" if enabled else "🔴 **Disabled**"
        embed = discord.Embed(
            title="⚙️ Bump Reminder Setting Updated",
            description=f"Disboard bump reminders are now {status_text}.",
            color=discord.Color.green() if enabled else discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BumpReminder(bot))
