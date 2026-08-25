"""
=======================================================
FC MOBILE & ESPORTS NEWS + LIVE SCORES BOT COG
=======================================================

Setup Instructions:
1. Register free keys:
   - Football-Data.org: https://www.football-data.org/client/register (Free tier)
   - PandaScore: https://pandascore.co (Free tier)
2. In Discord:
   !setchannel fc #fc-mobile-news
   !setchannel esports #esports-updates
   !setchannel scores #live-scores
   !setapikey football YOUR_KEY
   !setapikey esports YOUR_KEY
3. Done - Sweety auto-posts FC Mobile leaks, Esports tournaments, and Live Football scores!
"""

import os
import re
import json
import logging
import datetime
import asyncio
import aiohttp
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

import discord
from discord import app_commands
from discord.ext import commands, tasks

# ── Directory & Logger Setup ──────────────────────────────────────────────────
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
CONFIG_PATH = os.path.join(CONFIG_DIR, "sports_config.json")
LOG_PATH = os.path.join(LOGS_DIR, "sports.log")

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

sports_logger = logging.getLogger("Sweety.Sports")
sports_logger.setLevel(logging.INFO)

if not sports_logger.handlers:
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("[SPORTS] %(asctime)s - [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    sports_logger.addHandler(fh)

# IST Timezone (UTC +5:30)
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

LEAGUE_NAMES = {
    "PL": "Premier League (England)",
    "CL": "UEFA Champions League",
    "PD": "La Liga (Spain)",
    "SA": "Serie A (Italy)",
    "BL1": "Bundesliga (Germany)",
    "FL1": "Ligue 1 (France)"
}

LEAGUE_COLORS = {
    "PL": 0x38003C,   # Premier League Purple
    "CL": 0x001489,   # Champions League Navy
    "PD": 0xEE1E46,   # La Liga Red
    "SA": 0x024494,   # Serie A Blue
    "BL1": 0xD20515,  # Bundesliga Red
    "FL1": 0x091C3E   # Ligue 1 Dark Blue
}

DEFAULT_CONFIG = {
    "fc_mobile_channel_id": None,
    "esports_channel_id": None,
    "scores_channel_id": None,
    "football_data_api_key": None,
    "pandascore_api_key": None,
    "check_interval_minutes": 30,
    "leagues": ["PD", "SA", "BL1", "FL1"],
    "posted_news_ids": [],
    "posted_match_ids": []
}


def load_config() -> dict:
    """Loads sports config safely from JSON file."""
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
        sports_logger.error(f"Failed to load sports config: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config_data: dict):
    """Saves sports config safely to JSON file."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
    except Exception as e:
        sports_logger.error(f"Failed to save sports config: {e}")


class SportsNews(commands.Cog):
    """Comprehensive FC Mobile Leaks, Esports Tournaments, and European Football Live Scores Cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = load_config()
        self.posted_news_ids = set(self.config.get("posted_news_ids", []))
        self.posted_match_ids = set(self.config.get("posted_match_ids", []))
        
        # Track live score message IDs to edit in-place: {match_id: message_id}
        self.live_score_messages = {}
        
        # Last run stats for diagnostics
        self.last_fc_fetch = None
        self.last_esports_fetch = None
        self.last_live_scores_fetch = None
        self.last_upcoming_fetch = None

        # Start loops
        self.fc_mobile_news_loop.start()
        self.esports_news_loop.start()
        self.live_scores_loop.start()
        self.upcoming_matches_loop.start()
        sports_logger.info("SportsNews Cog initialized and all 4 background loops started.")

    def cog_unload(self):
        self.fc_mobile_news_loop.cancel()
        self.esports_news_loop.cancel()
        self.live_scores_loop.cancel()
        self.upcoming_matches_loop.cancel()
        sports_logger.info("SportsNews Cog unloaded and loops cancelled.")

    def _persist_tracking_ids(self):
        """Saves current posted ID tracking sets into config."""
        self.config["posted_news_ids"] = list(self.posted_news_ids)[-200:]
        self.config["posted_match_ids"] = list(self.posted_match_ids)[-200:]
        save_config(self.config)

    def _format_ist_time(self, utc_str: str) -> str:
        """Converts UTC ISO timestamp to formatted IST string."""
        try:
            dt = date_parser.parse(utc_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            ist_dt = dt.astimezone(IST)
            return ist_dt.strftime("%d %b %Y, %I:%M %p IST")
        except Exception:
            return utc_str

    # ── Loop 1: FC Mobile Leaks & News (Every 30 min) ───────────────────────────

    @tasks.loop(minutes=30)
    async def fc_mobile_news_loop(self):
        """Fetch EA Sports & Reddit RSS feeds for FC Mobile leaks/updates."""
        await self.bot.wait_until_ready()
        self.last_fc_fetch = datetime.datetime.now(IST)
        
        channel_id = self.config.get("fc_mobile_channel_id")
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                return

        articles = await self._fetch_fc_mobile_articles()
        new_count = 0

        for item in articles:
            item_id = item["id"]
            if item_id in self.posted_news_ids:
                continue

            embed = discord.Embed(
                title=f"🎮 {item['title'][:250]}",
                url=item["link"],
                description=item["summary"][:350] + ("..." if len(item["summary"]) > 350 else ""),
                color=0x00D4AA
            )
            embed.set_author(name=f"FC Mobile News • {item['source']}", icon_url="https://media.contentapi.ea.com/content/dam/ea/ea-sports-fc/fc-mobile/common/fc-mobile-logo.png")
            if item.get("image"):
                embed.set_thumbnail(url=item["image"])
            else:
                embed.set_thumbnail(url="https://media.contentapi.ea.com/content/dam/ea/ea-sports-fc/fc-mobile/common/fc-mobile-logo.png")
                
            embed.add_field(name="🔗 Source", value=f"[Read Full Article]({item['link']})", inline=False)
            embed.set_footer(text=f"FC Mobile Updates • {datetime.datetime.now(IST).strftime('%d %b %Y, %I:%M %p IST')}")

            try:
                await channel.send(embed=embed)
                self.posted_news_ids.add(item_id)
                new_count += 1
                await asyncio.sleep(1)
            except Exception as e:
                sports_logger.error(f"[ERROR] Failed to post FC Mobile article: {e}")

        if new_count > 0:
            sports_logger.info(f"[FC-NEWS] Fetched and posted {new_count} new articles to #{channel.name}")
            self._persist_tracking_ids()

    async def _fetch_fc_mobile_articles(self) -> list:
        """Fetches from EA RSS, Reddit RSS, and scraping fallbacks."""
        articles = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SweetyBot/1.0"}
        
        feeds = [
            ("Reddit (r/FUTMobile)", "https://www.reddit.com/r/FUTMobile/new/.rss"),
            ("EA Sports FC", "https://www.ea.com/games/ea-sports-fc/fc-mobile/news.rss")
        ]

        keywords = ["fc mobile", "fcmobile", "leak", "leaks", "update", "toty", "tots", "event", "new players", "reset", "market", "pack", "division rivals"]

        async with aiohttp.ClientSession(headers=headers) as session:
            for source_name, url in feeds:
                try:
                    async with session.get(url, timeout=12) as resp:
                        if resp.status == 200:
                            raw_xml = await resp.text()
                            feed = feedparser.parse(raw_xml)
                            for entry in feed.entries[:10]:
                                title = entry.get("title", "")
                                link = entry.get("link", "")
                                entry_id = entry.get("id", link or title)
                                summary = ""

                                if "summary" in entry:
                                    soup = BeautifulSoup(entry.summary, "html.parser")
                                    summary = soup.get_text(separator=" ").strip()
                                
                                # Filter keyword match
                                text_to_search = (title + " " + summary).lower()
                                if any(kw in text_to_search for kw in keywords) or "futmobile" in url.lower():
                                    articles.append({
                                        "id": entry_id,
                                        "title": title,
                                        "link": link,
                                        "summary": summary or "Click link to view discussion and details.",
                                        "source": source_name,
                                        "image": None
                                    })
                except Exception as e:
                    sports_logger.warning(f"Feed error ({source_name}): {e}")

        return articles

    # ── Loop 2: Esports Tournaments & Matches (Every 30 min) ───────────────────

    @tasks.loop(minutes=30)
    async def esports_news_loop(self):
        """Fetch upcoming esports tournaments & major matches from PandaScore."""
        await self.bot.wait_until_ready()
        self.last_esports_fetch = datetime.datetime.now(IST)

        api_key = self.config.get("pandascore_api_key")
        channel_id = self.config.get("esports_channel_id")

        if not api_key or not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                return

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "SweetyBot/1.0"
        }

        new_items = 0
        async with aiohttp.ClientSession(headers=headers) as session:
            # 1. Fetch Upcoming Tournaments
            try:
                async with session.get("https://api.pandascore.co/tournaments/upcoming?per_page=5", timeout=12) as resp:
                    if resp.status == 200:
                        tournaments = await resp.json()
                        for tourn in tournaments:
                            t_id = f"tourn_{tourn.get('id')}"
                            if t_id in self.posted_match_ids:
                                continue

                            league = tourn.get("league", {})
                            videogame = tourn.get("videogame", {})
                            
                            embed = discord.Embed(
                                title=f"🏆 {tourn.get('name', 'Major Tournament')}",
                                description=f"**League:** {league.get('name', 'N/A')}\n**Game:** {videogame.get('name', 'Esports')}",
                                color=0xFF4655
                            )
                            embed.set_author(name="ESPORTS TOURNAMENT ANNOUNCEMENT", icon_url=videogame.get("image_url") or "https://i.imgur.com/8Q9Z5bS.png")
                            if league.get("image_url"):
                                embed.set_thumbnail(url=league.get("image_url"))

                            start_at = tourn.get("begin_at")
                            if start_at:
                                embed.add_field(name="📅 Start Date", value=self._format_ist_time(start_at), inline=True)
                            
                            prizepool = tourn.get("prizepool")
                            if prizepool:
                                embed.add_field(name="💰 Prize Pool", value=str(prizepool), inline=True)
                                
                            teams_count = len(tourn.get("teams", []))
                            if teams_count:
                                embed.add_field(name="👥 Teams", value=f"`{teams_count}` participating", inline=True)

                            embed.set_footer(text=f"Esports Updates • {datetime.datetime.now(IST).strftime('%d %b %Y, %I:%M %p IST')}")
                            
                            await channel.send(embed=embed)
                            self.posted_match_ids.add(t_id)
                            new_items += 1
                            await asyncio.sleep(1)
            except Exception as e:
                sports_logger.error(f"[ERROR] PandaScore tournaments fetch failed: {e}")

        if new_items > 0:
            sports_logger.info(f"[ESPORTS] {new_items} new tournaments/matches posted to #{channel.name}")
            self._persist_tracking_ids()

    # ── Loop 3: Live Football Scores (Every 5 min) ──────────────────────────────

    @tasks.loop(minutes=5)
    async def live_scores_loop(self):
        """Fetch real-time live matches for La Liga, Serie A, Bundesliga, and Ligue 1."""
        await self.bot.wait_until_ready()
        self.last_live_scores_fetch = datetime.datetime.now(IST)

        api_key = self.config.get("football_data_api_key")
        channel_id = self.config.get("scores_channel_id")

        if not api_key or not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                return

        headers = {
            "X-Auth-Token": api_key,
            "User-Agent": "SweetyBot/1.0"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            for code in self.config.get("leagues", ["PD", "SA", "BL1", "FL1"]):
                url = f"https://api.football-data.org/v4/competitions/{code}/matches?status=IN_PLAY,LIVE,PAUSED"
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 429:
                            sports_logger.warning("[ERROR] football-data.org rate limited (429), waiting 60s")
                            await asyncio.sleep(60)
                            continue
                        elif resp.status == 200:
                            data = await resp.json()
                            matches = data.get("matches", [])
                            for m in matches:
                                await self._post_or_update_live_match(channel, m, code)
                except Exception as e:
                    sports_logger.error(f"Live scores error ({code}): {e}")
                await asyncio.sleep(2)  # Respect free tier rate limits

    async def _post_or_update_live_match(self, channel: discord.TextChannel, match: dict, league_code: str):
        """Creates or edits an in-place live score card."""
        match_id = match.get("id")
        home = match.get("homeTeam", {}).get("name", "Home")
        away = match.get("awayTeam", {}).get("name", "Away")
        
        score_data = match.get("score", {}).get("fullTime", {})
        home_score = score_data.get("home", 0) or 0
        away_score = score_data.get("away", 0) or 0
        
        minute = match.get("minute", "LIVE")
        league_name = LEAGUE_NAMES.get(league_code, league_code)

        embed = discord.Embed(
            title=f"⚽ LIVE MATCH — {league_name}",
            color=LEAGUE_COLORS.get(league_code, 0x38003C)
        )
        embed.add_field(name="🏠 Home", value=f"**{home}**\n`{home_score}`", inline=True)
        embed.add_field(name="⏱️ Status", value=f"**{minute}'**\nVS", inline=True)
        embed.add_field(name="🚌 Away", value=f"**{away}**\n`{away_score}`", inline=True)
        embed.set_footer(text=f"Live Score • Auto-updates every 5 min • {datetime.datetime.now(IST).strftime('%I:%M %p IST')}")

        if match_id in self.live_score_messages:
            msg_id = self.live_score_messages[match_id]
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed)
                sports_logger.info(f"[LIVE] Updated {league_name}: {home} {home_score}-{away_score} {away} ({minute}')")
                return
            except Exception:
                pass  # Message was deleted or inaccessible, post new

        try:
            sent_msg = await channel.send(embed=embed)
            self.live_score_messages[match_id] = sent_msg.id
            sports_logger.info(f"[LIVE] New match posted {league_name}: {home} {home_score}-{away_score} {away}")
        except Exception as e:
            sports_logger.error(f"Failed to send live score message: {e}")

    # ── Loop 4: Upcoming Matches (Every 6 Hours) ───────────────────────────────

    @tasks.loop(hours=6)
    async def upcoming_matches_loop(self):
        """Fetch upcoming matches for the next 7 days across top 4 leagues."""
        await self.bot.wait_until_ready()
        self.last_upcoming_fetch = datetime.datetime.now(IST)

        api_key = self.config.get("football_data_api_key")
        channel_id = self.config.get("scores_channel_id")

        if not api_key or not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                return

        headers = {"X-Auth-Token": api_key, "User-Agent": "SweetyBot/1.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            for code in self.config.get("leagues", ["PD", "SA", "BL1", "FL1"]):
                url = f"https://api.football-data.org/v4/competitions/{code}/matches?status=SCHEDULED"
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            matches = data.get("matches", [])[:8]
                            if matches:
                                embed = self._build_upcoming_embed(code, matches)
                                await channel.send(embed=embed)
                                sports_logger.info(f"[UPCOMING] Posted upcoming fixtures for {LEAGUE_NAMES.get(code, code)}")
                                await asyncio.sleep(2)
                except Exception as e:
                    sports_logger.error(f"Upcoming matches error ({code}): {e}")

    def _build_upcoming_embed(self, league_code: str, matches: list) -> discord.Embed:
        """Generates a clean upcoming matches overview embed."""
        league_name = LEAGUE_NAMES.get(league_code, league_code)
        embed = discord.Embed(
            title=f"📅 UPCOMING FIXTURES — {league_name}",
            description="Upcoming scheduled matches for the next 7 days:",
            color=0x00FF87
        )
        for m in matches:
            home = m.get("homeTeam", {}).get("name", "Home")
            away = m.get("awayTeam", {}).get("name", "Away")
            utc_date = m.get("utcDate", "")
            ist_str = self._format_ist_time(utc_date)
            embed.add_field(
                name=f"⚽ {home} vs {away}",
                value=f"🕒 **{ist_str}**",
                inline=False
            )
        embed.set_footer(text=f"Football Fixtures (IST) • {league_name}")
        return embed

    # ── Prefix & Hybrid Commands ───────────────────────────────────────────────

    @commands.command(name="setchannel")
    @commands.has_permissions(administrator=True)
    async def setchannel_cmd(self, ctx: commands.Context, feed_type: str, channel: discord.TextChannel = None):
        """Set output channel for fc, esports, or scores: !setchannel <fc|esports|scores> [#channel]"""
        target = channel or ctx.channel
        feed_type = feed_type.lower().strip()

        if feed_type in ("fc", "fcmobile", "fc_mobile"):
            self.config["fc_mobile_channel_id"] = target.id
            name = "🎮 FC Mobile News"
        elif feed_type in ("esports", "gaming"):
            self.config["esports_channel_id"] = target.id
            name = "🏆 Esports Tournaments"
        elif feed_type in ("scores", "football", "soccer"):
            self.config["scores_channel_id"] = target.id
            name = "⚽ Live Football Scores"
        else:
            await ctx.send("❌ Invalid type. Choose: `fc`, `esports`, or `scores`.\nExample: `!setchannel fc #fc-news`")
            return

        save_config(self.config)
        sports_logger.info(f"[CONFIG] {name} channel set to #{target.name} ({target.id}) by {ctx.author}")
        await ctx.send(f"✅ Successfully set **{name}** channel to {target.mention}!")

    @commands.command(name="setapikey")
    @commands.has_permissions(administrator=True)
    async def setapikey_cmd(self, ctx: commands.Context, service: str, api_key: str):
        """Set free API keys: !setapikey <football|esports> <KEY>"""
        service = service.lower().strip()
        if service in ("football", "footballdata", "football-data"):
            self.config["football_data_api_key"] = api_key.strip()
            name = "Football-Data.org"
        elif service in ("esports", "pandascore"):
            self.config["pandascore_api_key"] = api_key.strip()
            name = "PandaScore"
        else:
            await ctx.send("❌ Invalid service. Choose: `football` or `esports`.\nExample: `!setapikey football YOUR_KEY`")
            return

        save_config(self.config)
        sports_logger.info(f"[CONFIG] {name} API key updated by {ctx.author}")
        try:
            await ctx.message.delete()  # Delete message for API key security
        except Exception:
            pass
        await ctx.send(f"🔒 Successfully configured and saved **{name}** API key securely!")

    @commands.command(name="fcnews")
    async def fcnews_cmd(self, ctx: commands.Context):
        """Fetch latest FC Mobile news and leaks immediately."""
        async with ctx.typing():
            articles = await self._fetch_fc_mobile_articles()
            if not articles:
                await ctx.send("ℹ️ No new FC Mobile articles found right now. Check back soon!")
                return

            for item in articles[:3]:
                embed = discord.Embed(
                    title=f"🎮 {item['title'][:250]}",
                    url=item["link"],
                    description=item["summary"][:350] + ("..." if len(item["summary"]) > 350 else ""),
                    color=0x00D4AA
                )
                embed.set_author(name=f"FC Mobile News • {item['source']}", icon_url="https://media.contentapi.ea.com/content/dam/ea/ea-sports-fc/fc-mobile/common/fc-mobile-logo.png")
                embed.add_field(name="🔗 Source", value=f"[Read Full Article]({item['link']})", inline=False)
                embed.set_footer(text=f"FC Mobile Updates • {datetime.datetime.now(IST).strftime('%d %b %Y, %I:%M %p IST')}")
                await ctx.send(embed=embed)

    @commands.command(name="esports")
    async def esports_cmd(self, ctx: commands.Context):
        """Fetch latest esports tournaments now."""
        api_key = self.config.get("pandascore_api_key")
        if not api_key:
            await ctx.send("❌ PandaScore API key is not configured! Admin can set it using `!setapikey esports <KEY>`.")
            return

        async with ctx.typing():
            headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json", "User-Agent": "SweetyBot/1.0"}
            async with aiohttp.ClientSession(headers=headers) as session:
                try:
                    async with session.get("https://api.pandascore.co/tournaments/upcoming?per_page=3", timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if not data:
                                await ctx.send("ℹ️ No upcoming tournaments found.")
                                return
                            for tourn in data:
                                league = tourn.get("league", {})
                                videogame = tourn.get("videogame", {})
                                embed = discord.Embed(
                                    title=f"🏆 {tourn.get('name', 'Tournament')}",
                                    description=f"**League:** {league.get('name', 'N/A')}\n**Game:** {videogame.get('name', 'Esports')}",
                                    color=0xFF4655
                                )
                                embed.set_author(name="ESPORTS TOURNAMENT", icon_url=videogame.get("image_url") or "https://i.imgur.com/8Q9Z5bS.png")
                                start_at = tourn.get("begin_at")
                                if start_at:
                                    embed.add_field(name="📅 Start Date", value=self._format_ist_time(start_at), inline=True)
                                embed.set_footer(text=f"Esports Updates • {datetime.datetime.now(IST).strftime('%I:%M %p IST')}")
                                await ctx.send(embed=embed)
                        else:
                            await ctx.send("❌ Failed to reach PandaScore API. Please verify your API key.")
                except Exception as e:
                    await ctx.send(f"❌ Error fetching esports tournaments: {e}")

    @commands.command(name="live")
    async def live_cmd(self, ctx: commands.Context):
        """Show all currently live matches in top European leagues."""
        api_key = self.config.get("football_data_api_key")
        if not api_key:
            await ctx.send("❌ Football-Data API key is not set! Admin can set it using `!setapikey football <KEY>`.")
            return

        async with ctx.typing():
            headers = {"X-Auth-Token": api_key, "User-Agent": "SweetyBot/1.0"}
            live_found = 0
            async with aiohttp.ClientSession(headers=headers) as session:
                for code in self.config.get("leagues", ["PD", "SA", "BL1", "FL1"]):
                    url = f"https://api.football-data.org/v4/competitions/{code}/matches?status=IN_PLAY,LIVE,PAUSED"
                    try:
                        async with session.get(url, timeout=10) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                for m in data.get("matches", []):
                                    home = m.get("homeTeam", {}).get("name", "Home")
                                    away = m.get("awayTeam", {}).get("name", "Away")
                                    score = m.get("score", {}).get("fullTime", {})
                                    h_s = score.get("home", 0) or 0
                                    a_s = score.get("away", 0) or 0
                                    embed = discord.Embed(
                                        title=f"⚽ LIVE — {LEAGUE_NAMES.get(code, code)}",
                                        color=LEAGUE_COLORS.get(code, 0x38003C)
                                    )
                                    embed.add_field(name="🏠 Home", value=f"**{home}**\n`{h_s}`", inline=True)
                                    embed.add_field(name="⏱️ Minute", value=f"**{m.get('minute', 'LIVE')}'**", inline=True)
                                    embed.add_field(name="🚌 Away", value=f"**{away}**\n`{a_s}`", inline=True)
                                    embed.set_footer(text=f"Live Score (IST) • {datetime.datetime.now(IST).strftime('%I:%M %p IST')}")
                                    await ctx.send(embed=embed)
                                    live_found += 1
                    except Exception as e:
                        sports_logger.error(f"Error in !live: {e}")

            if live_found == 0:
                await ctx.send("ℹ️ No live matches currently in progress for La Liga, Serie A, Bundesliga, or Ligue 1. Use `!upcoming` to see upcoming fixtures!")

    @commands.command(name="upcoming")
    async def upcoming_cmd(self, ctx: commands.Context, league: str = "laliga"):
        """Show upcoming matches: !upcoming <laliga|seriea|bundesliga|ligue1>"""
        api_key = self.config.get("football_data_api_key")
        if not api_key:
            await ctx.send("❌ Football-Data API key is not set! Admin can set it using `!setapikey football <KEY>`.")
            return

        league_map = {
            "laliga": "PD", "la liga": "PD", "pd": "PD", "spain": "PD",
            "seriea": "SA", "serie a": "SA", "sa": "SA", "italy": "SA",
            "bundesliga": "BL1", "bl1": "BL1", "germany": "BL1",
            "ligue1": "FL1", "ligue 1": "FL1", "fl1": "FL1", "france": "FL1"
        }
        code = league_map.get(league.lower().replace(" ", ""), "PD")

        async with ctx.typing():
            headers = {"X-Auth-Token": api_key, "User-Agent": "SweetyBot/1.0"}
            async with aiohttp.ClientSession(headers=headers) as session:
                url = f"https://api.football-data.org/v4/competitions/{code}/matches?status=SCHEDULED"
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            matches = data.get("matches", [])[:8]
                            if matches:
                                embed = self._build_upcoming_embed(code, matches)
                                await ctx.send(embed=embed)
                            else:
                                await ctx.send(f"ℹ️ No upcoming matches scheduled in next 7 days for {LEAGUE_NAMES.get(code, code)}.")
                        else:
                            await ctx.send("❌ Failed to fetch matches. Please check API key.")
                except Exception as e:
                    await ctx.send(f"❌ Error fetching upcoming matches: {e}")

    @commands.command(name="sportshelp")
    async def sportshelp_cmd(self, ctx: commands.Context):
        """Show full sports & esports command list and setup instructions."""
        embed = discord.Embed(
            title="⚽ Sweety Sports, Esports & FC Mobile Hub",
            description="Comprehensive auto-posting and live tracking for FC Mobile, Esports, and Top European Football leagues!",
            color=0x00FF87
        )
        embed.add_field(
            name="🛠️ Admin Setup Commands",
            value=(
                "• `!setchannel fc <#chan>` — Set FC Mobile news channel\n"
                "• `!setchannel esports <#chan>` — Set Esports updates channel\n"
                "• `!setchannel scores <#chan>` — Set Live scores & fixtures channel\n"
                "• `!setapikey football <KEY>` — Set Football-Data.org free API key\n"
                "• `!setapikey esports <KEY>` — Set PandaScore free API key\n"
                "• `!forcefetch` — Force run all 4 background loops immediately\n"
                "• `!sportsstatus` — View diagnostic stats and loop health"
            ),
            inline=False
        )
        embed.add_field(
            name="👥 Member Commands",
            value=(
                "• `!fcnews` — Fetch latest FC Mobile leaks & updates\n"
                "• `!esports` — Fetch upcoming esports tournaments\n"
                "• `!live` — Show all live matches right now\n"
                "• `!upcoming [laliga|seriea|bundesliga|ligue1]` — Show upcoming fixtures (IST)"
            ),
            inline=False
        )
        embed.set_footer(text="Sweety Sports Hub • All times shown in IST")
        await ctx.send(embed=embed)

    @commands.command(name="sportsstatus")
    @commands.has_permissions(administrator=True)
    async def sportsstatus_cmd(self, ctx: commands.Context):
        """View diagnostic status of all 4 loops and channel configs."""
        fc_chan = self.bot.get_channel(int(self.config.get("fc_mobile_channel_id") or 0))
        esp_chan = self.bot.get_channel(int(self.config.get("esports_channel_id") or 0))
        sc_chan = self.bot.get_channel(int(self.config.get("scores_channel_id") or 0))

        embed = discord.Embed(
            title="📊 Sports Hub Diagnostics & Loop Status",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="📍 Channels Configured",
            value=(
                f"• **FC Mobile:** {fc_chan.mention if fc_chan else '`Not set`'}\n"
                f"• **Esports:** {esp_chan.mention if esp_chan else '`Not set`'}\n"
                f"• **Live Scores:** {sc_chan.mention if sc_chan else '`Not set`'}"
            ),
            inline=False
        )
        embed.add_field(
            name="🔑 API Keys",
            value=(
                f"• **Football-Data:** `{'Configured' if self.config.get('football_data_api_key') else 'Missing'}`\n"
                f"• **PandaScore:** `{'Configured' if self.config.get('pandascore_api_key') else 'Missing'}`"
            ),
            inline=False
        )
        embed.add_field(
            name="🔄 Loop Timestamps (IST)",
            value=(
                f"• **FC News (30m):** `{self.last_fc_fetch.strftime('%I:%M %p') if self.last_fc_fetch else 'Pending'}`\n"
                f"• **Esports (30m):** `{self.last_esports_fetch.strftime('%I:%M %p') if self.last_esports_fetch else 'Pending'}`\n"
                f"• **Live Scores (5m):** `{self.last_live_scores_fetch.strftime('%I:%M %p') if self.last_live_scores_fetch else 'Pending'}`\n"
                f"• **Upcoming (6h):** `{self.last_upcoming_fetch.strftime('%I:%M %p') if self.last_upcoming_fetch else 'Pending'}`"
            ),
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.command(name="forcefetch")
    @commands.has_permissions(administrator=True)
    async def forcefetch_cmd(self, ctx: commands.Context):
        """Force execute all 4 tasks immediately."""
        msg = await ctx.send("⏳ Force running all sports loops...")
        await self.fc_mobile_news_loop()
        await self.esports_news_loop()
        await self.live_scores_loop()
        await self.upcoming_matches_loop()
        await msg.edit(content="✅ Force fetch complete across all 4 modules!")

    # ── Slash Command Equivalents ──────────────────────────────────────────────

    @app_commands.command(name="fcnews", description="Fetch the latest FC Mobile news, updates, and community leaks")
    async def slash_fcnews(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        articles = await self._fetch_fc_mobile_articles()
        if not articles:
            await interaction.followup.send("ℹ️ No new FC Mobile articles found right now.")
            return

        for item in articles[:3]:
            embed = discord.Embed(
                title=f"🎮 {item['title'][:250]}",
                url=item["link"],
                description=item["summary"][:350] + ("..." if len(item["summary"]) > 350 else ""),
                color=0x00D4AA
            )
            embed.set_author(name=f"FC Mobile News • {item['source']}", icon_url="https://media.contentapi.ea.com/content/dam/ea/ea-sports-fc/fc-mobile/common/fc-mobile-logo.png")
            embed.add_field(name="🔗 Source", value=f"[Read Full Article]({item['link']})", inline=False)
            embed.set_footer(text=f"FC Mobile Updates • {datetime.datetime.now(IST).strftime('%d %b %Y, %I:%M %p IST')}")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="sportshelp", description="View all available sports, esports, and football commands")
    async def slash_sportshelp(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚽ Sweety Sports, Esports & FC Mobile Hub",
            description="Comprehensive auto-posting and live tracking for FC Mobile, Esports, and Top European Football leagues!",
            color=0x00FF87
        )
        embed.add_field(
            name="🛠️ Setup Commands (Prefix `!`)",
            value=(
                "• `!setchannel fc <#chan>` — Set FC Mobile news channel\n"
                "• `!setchannel esports <#chan>` — Set Esports updates channel\n"
                "• `!setchannel scores <#chan>` — Set Live scores & fixtures channel\n"
                "• `!setapikey football <KEY>` — Set Football-Data.org key\n"
                "• `!setapikey esports <KEY>` — Set PandaScore key\n"
                "• `!sportsstatus` — View diagnostic stats and loop status\n"
                "• `!forcefetch` — Force run all background loops"
            ),
            inline=False
        )
        embed.add_field(
            name="👥 Member Commands (Prefix `!` or Slash `/`)",
            value=(
                "• `/fcnews` — Fetch latest FC Mobile leaks & updates\n"
                "• `!esports` — Fetch upcoming esports tournaments\n"
                "• `!live` — Show all live matches right now\n"
                "• `!upcoming [league]` — Show upcoming fixtures (IST)"
            ),
            inline=False
        )
        embed.set_footer(text="Sweety Sports Hub • All times in IST (UTC+5:30)")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(SportsNews(bot))
