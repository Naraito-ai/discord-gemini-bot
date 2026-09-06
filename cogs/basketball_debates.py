"""
=======================================================
SPACEYT BASKETBALL DEBATES & ENGAGEMENT COG
=======================================================
Features:
1. Daily & on-demand spicy NBA/Basketball debates & hot takes
2. Interactive real-time voting buttons with dynamic multi-option support (2, 3, or 4 players)
3. Bulletproof persistent interaction listener (buttons NEVER fail across bot restarts)
4. Live percentage bars for all choices
5. "Start, Bench, Cut" challenges
6. Automated debate threads to drive server chat and retention
7. Slash commands + instant prefix commands
"""

import os
import re
import json
import random
import logging
import asyncio
import datetime
from typing import Optional, Dict, Any, List

import discord
from discord import app_commands
from discord.ext import commands, tasks

# ── Directory & Logger Setup ──────────────────────────────────────────────────
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "debates_config.json")
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_PATH = os.path.join(LOGS_DIR, "debates.log")

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

logger = logging.getLogger("Sweety.Debates")
logger.setLevel(logging.INFO)

if not logger.handlers:
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("[DEBATES] %(asctime)s - [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)

DEFAULT_CONFIG = {
    "channel_id": None,
    "auto_post_enabled": True,
    "post_interval_hours": 12,
    "auto_create_thread": True,
    "mention_everyone": False,
    "history": [],
    "user_votes": {}  # message_id -> {user_id: option_idx}
}

def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
    except Exception as e:
        logger.error(f"Failed to load debates config: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(cfg: Dict[str, Any]) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save debates config: {e}")

# ── Curated Bank of High-Engagement Basketball Debates ────────────────────────

DEBATES_BANK: List[Dict[str, Any]] = [
    # ── 3-Way Clutch Showdown ──
    {
        "id": "clutch_final_shot_3way",
        "category": "🎯 CLUTCH GENE",
        "title": "Down 1 with 5 seconds left: Kobe, Jordan, or Dame?",
        "description": "Final possession of Game 7 of the NBA Finals. Down by 1 point. Ball is inbounded with 5.0 seconds left on the clock.\n\nWho are you giving the final shot to win the championship?",
        "options": ["🐍 Kobe Bryant", "🐐 Michael Jordan", "⌚ Damian Lillard"],
        "hot_take": "Dame has the longest buzzer-beaters in playoff history, but Jordan has 6 rings. Who gets the rock?"
    },
    {
        "id": "goat_lj_mj",
        "category": "🐐 GOAT DEBATE",
        "title": "Michael Jordan vs. LeBron James",
        "description": "The eternal basketball debate.\n\n**Michael Jordan:** 6x NBA Champion, 6x Finals MVP, 5x MVP, 10x Scoring Champ, DPOY, never lost a Finals series.\n**LeBron James:** 4x NBA Champion, 4x Finals MVP, 4x MVP, NBA All-Time Leading Scorer (40k+ pts), 20+ years of elite dominance.\n\nWho holds the basketball crown?",
        "options": ["🐐 Michael Jordan", "👑 LeBron James"],
        "hot_take": "Does LeBron's unmatched longevity beat Jordan's flawless peak?"
    },
    {
        "id": "kobe_vs_curry",
        "category": "🏆 LEGACY SHOWDOWN",
        "title": "Kobe Bryant vs. Stephen Curry",
        "description": "Two players who changed how the entire world plays basketball.\n\n**Kobe Bryant:** 5x Champion, 2x Finals MVP, 18x All-Star, 81-point game, Black Mamba mentality & elite two-way defense.\n**Stephen Curry:** 4x Champion, Finals MVP, 2x MVP (only unanimous MVP in history), greatest shooter ever who transformed modern offense.\n\nWho had the greater all-time career and legacy?",
        "options": ["🐍 Kobe Bryant", "🎯 Stephen Curry"],
        "hot_take": "Curry changed the game, but Kobe inspired the mindset. Who do you rank higher?"
    },
    {
        "id": "pg_goat",
        "category": "⚡ BEST POINT GUARD EVER",
        "title": "Magic Johnson vs. Stephen Curry",
        "description": "The battle for Point Guard supremacy:\n\n**Magic Johnson:** 5x Champion, 3x MVP, 3x Finals MVP, 6'9\" Showtime passing wizard and playmaker.\n**Stephen Curry:** 4x Champion, 2x MVP, revolutionized basketball spacing and shooting range forever.\n\nWho takes the starting PG spot on your All-Time team?",
        "options": ["🪄 Magic Johnson", "👨‍🍳 Stephen Curry"],
        "hot_take": "Can Steph's revolutionary shooting dethrone Magic's 5 rings and unmatched playmaking?"
    },
    {
        "id": "prime_center_beast",
        "category": "🧱 PAINT DOMINANCE",
        "title": "Prime Shaquille O'Neal vs. Prime Hakeem Olajuwon",
        "description": "Game 7, NBA Finals, both players in their absolute physical primes.\n\n**Shaq (2000 MVP):** The most unstoppable, overpowering physical force in NBA history.\n**Hakeem (1994 MVP + DPOY):** The Dream Shake, all-time blocks leader, impossible footwork.\n\nWho dominates the paint and wins you the chip?",
        "options": ["🦍 Prime Shaq", "💫 Prime Hakeem"],
        "hot_take": "Shaq swept Hakeem later, but Hakeem swept Shaq in '95. Who takes the crown?"
    },
    {
        "id": "warriors17_vs_bulls96",
        "category": "⚔️ DYNASTY BATTLE",
        "title": "2017 Golden State Warriors vs. 1996 Chicago Bulls",
        "description": "A 7-game series at neutral site, modern officiating with fair physical whistle.\n\n**2017 Warriors:** 73-9 core + Kevin Durant, Steph Curry, Klay Thompson, Draymond Green (16-1 playoff record).\n**1996 Bulls:** 72-10 record, Michael Jordan, Scottie Pippen, Dennis Rodman, Phil Jackson.\n\nWho wins the series?",
        "options": ["🌉 '17 Warriors (KD + Steph)", "🐂 '96 Bulls (MJ + Pippen)"],
        "hot_take": "Can the Bulls' perimeter defense slow down Steph and KD, or do the Warriors get bullied?"
    },
    {
        "id": "luka_vs_tatum_vs_sga_3way",
        "category": "🌟 NEXT GENERATION KINGS",
        "title": "Build a Franchise Around: Luka Dončić, Shai Gilgeous-Alexander, or Jayson Tatum?",
        "description": "You are awarded an expansion NBA team today. You have the choice of signing one superstar to lead your franchise for the next decade:\n\n**Luka Dončić:** Playoff scoring & triple-double machine.\n**Shai Gilgeous-Alexander:** Two-way superstar guard, lethal mid-range and rim pressure.\n**Jayson Tatum:** NBA Champion, elite two-way wing, complete modern prototype.\n\nWho are you building around?",
        "options": ["🪄 Luka Dončić", "⚡ Shai Gilgeous-Alexander", "☘️ Jayson Tatum"],
        "hot_take": "Tatum has the ring, Luka has the stats, and Shai has the two-way game. Who is #1?"
    },
    {
        "id": "kd_vs_kawhi_prime",
        "category": "🔥 SCORER VS TWO-WAY MONSTER",
        "title": "Prime Kevin Durant vs. Prime Kawhi Leonard",
        "description": "Playoff series on the line:\n\n**Kevin Durant:** 7-foot sniper, unguardable hesi-pullup, 4x Scoring Champ, 2x Finals MVP.\n**Kawhi Leonard (2019 'The Claw'):** Defensive lockdown clamp, robotic mid-range execution, 2x Finals MVP across two franchises.\n\nWho would you rather have for a championship run?",
        "options": ["🎯 Prime Kevin Durant", "🤖 Prime Kawhi Leonard"],
        "hot_take": "KD has the better bag, but Kawhi was an unstoppable two-way terminator in 2019."
    },
    {
        "id": "best_duo_history_3way",
        "category": "👥 GREATEST DUO OF ALL TIME",
        "title": "Shaq & Kobe vs. Jordan & Pippen vs. LeBron & Wade",
        "description": "Three iconic championship duos:\n\n**Shaq & Kobe:** Dominant inside-outside power, 3-peat.\n**Jordan & Pippen:** 6-0 in Finals, greatest perimeter defensive duo.\n**LeBron & Wade:** Unmatched athleticism and transition fastbreak speed.\n\nWhich duo is the greatest in NBA history?",
        "options": ["💜💛 Shaq & Kobe", "❤️🖤 Jordan & Pippen", "🔥 LeBron & Wade"],
        "hot_take": "Could anyone stop prime Shaq and young Kobe when they were locked in?"
    },
    {
        "id": "jokic_vs_giannis",
        "category": "🌍 INTERNATIONAL TITANS",
        "title": "Nikola Jokić vs. Giannis Antetokounmpo",
        "description": "The two modern MVP European powerhouses:\n\n**Nikola Jokić:** 3x MVP, Finals MVP, highest basketball IQ center in history, unguardable passing and touch.\n**Giannis Antetokounmpo:** 2x MVP, DPOY, Finals MVP (50-pt Game 6), unstoppable Greek Freak transition engine.\n\nWho ranks higher all-time when both careers are done?",
        "options": ["🃏 Nikola Jokić", "🦌 Giannis Antetokounmpo"],
        "hot_take": "Jokic's offensive genius vs Giannis's two-way dominance — who do you choose?"
    },
    {
        "id": "pure_shooter_3way",
        "category": "🎯 GREATEST SNIPERS",
        "title": "Best Pure Shooter: Steph Curry, Klay Thompson, or Ray Allen?",
        "description": "Game on the line, catch-and-shoot 3-pointer with a hand in their face.\n\n**Steph Curry:** Off-the-dribble god, limitless range.\n**Klay Thompson:** Fastest release in history, 37 pts in a quarter.\n**Ray Allen:** Picture-perfect mechanics, iconic Game 6 miracle.\n\nWho has the purest jumper?",
        "options": ["👨‍🍳 Steph Curry", "🎯 Klay Thompson", "☄️ Ray Allen"],
        "hot_take": "Steph has the range, but in a stationary catch-and-shoot contest, who wins?"
    },
    {
        "id": "greatest_dunker_3way",
        "category": "✈️ IN-GAME DUNK KINGS",
        "title": "Greatest In-Game Dunker: Vince Carter, Michael Jordan, or LeBron James?",
        "description": "Driving down the lane with a 7-footer waiting at the rim.\n\n**Vince Carter:** Dunk of Death over 7'2\" Weis, unmatched bounce and creativity.\n**Michael Jordan:** Free throw line liftoff, suspended in mid-air.\n**LeBron James:** Unstoppable freight train posterizing everyone for 20 straight years.\n\nWho is the true King of the Dunk?",
        "options": ["✈️ Vince Carter", "🐐 Michael Jordan", "👑 LeBron James"],
        "hot_take": "Can anyone top Vince Carter's 2000 Dunk Contest and Olympic poster?"
    },
    {
        "id": "derrick_rose_vs_kyrie_1v1",
        "category": "⚔️ 1v1 TO 21",
        "title": "1v1 to 21 (Make-it-Take-it): Prime D-Rose vs. Prime Kyrie Irving",
        "description": "No double teams. Pure ISO basketball. Winners ball.\n\n**Prime Derrick Rose (2011 MVP):** Blinding first-step speed, violent change of direction, impossible acrobatics.\n**Prime Kyrie Irving:** The deepest scoring bag in history, both hands, unguardable handles and finishing.\n\nFirst to 21 wins. Who takes it?",
        "options": ["🌹 Prime Derrick Rose", "🪄 Prime Kyrie Irving"],
        "hot_take": "Kyrie has the better handles, but could he stay in front of 2011 MVP Rose?"
    },
    {
        "id": "best_euro_alltime_3way",
        "category": "🌍 BEST EUROPEAN PLAYER EVER",
        "title": "Greatest European Player: Dirk Nowitzki, Giannis, or Nikola Jokić?",
        "description": "Europe has taken over the NBA. Who ranks highest all-time when all is said and done?\n\n**Dirk Nowitzki:** 2011 legendary championship run beating LeBron/Wade/Bosh, one-legged fadeaway pioneer.\n**Giannis Antetokounmpo:** 2x MVP, DPOY, 50-point Finals closeout.\n**Nikola Jokić:** 3x MVP, Finals MVP, most complete offensive center in history.\n\nWho holds European basketball crown?",
        "options": ["🇩🇪 Dirk Nowitzki", "🇬🇷 Giannis Antetokounmpo", "🇷🇸 Nikola Jokić"],
        "hot_take": "Does Dirk's 2011 solo ring still hold more weight than Jokic's 3 MVPs?"
    },
    {
        "id": "three_point_revolution",
        "category": "📢 CONTROVERSIAL HOT TAKE",
        "title": "Has the 3-Point Era Ruined the NBA?",
        "description": "Teams now routinely hoist 45+ three-pointers a game. Mid-range and post play have diminished significantly.\n\n**Side A (Ruined):** Too repetitive, live-or-die by the 3, lack of defensive grit and physical interior battles.\n**Side B (Improved):** Elite spacing, higher skill level than ever, exciting high-scoring games and comebacks.\n\nWhat is your honest take?",
        "options": ["❌ Yes, it ruined the game", "✅ No, it evolved for the better"],
        "hot_take": "Are high scores fun, or do you miss physical 90s/2000s basketball?"
    },
    {
        "id": "rings_vs_stats",
        "category": "📢 CONTROVERSIAL HOT TAKE",
        "title": "Do Rings Matter Too Much in All-Time Rankings?",
        "description": "Often players like Charles Barkley, Allen Iverson, and Steve Nash are dismissed in GOAT conversations because they lack an NBA ring, while role players have multiple.\n\n**Side A:** Rings are the ultimate goal; true superstars carry teams over the finish line.\n**Side B:** Basketball is a 5v5 team sport; front office competence and injuries dictate championships more than individual greatness.\n\nWhere do you stand?",
        "options": ["💍 Rings are #1 metric", "📊 Context & Stats matter more"],
        "hot_take": "Does Robert Horry having 7 rings make him better than Charles Barkley?"
    },
    {
        "id": "unbreakable_record",
        "category": "📜 UNBREAKABLE RECORDS",
        "title": "Which Record Will NEVER Be Broken?",
        "description": "Two legendary NBA milestones that seem physically impossible to surpass:\n\n**Wilt Chamberlain's 100-Point Game (1962):** Scoring 100 points in a single 48-minute game.\n**LeBron James's All-Time Scoring Record (40,000+ points):** Requiring 20+ years of 25+ PPG without severe injury.\n\nWhich record stands forever?",
        "options": ["💯 Wilt's 100-Point Game", "👑 LeBron's 40,000+ Points"],
        "hot_take": "With today's pace, could a superstar get hot and drop 101, or is LeBron's 21-year durability unreachable?"
    },
    {
        "id": "wemby_ceiling",
        "category": "👽 THE ALIEN DEBATE",
        "title": "Will Victor Wembanyama Retire as a Top 10 Player All-Time?",
        "description": "Victor Wembanyama entered the league with the most hype since LeBron in 2003 and posted historic defensive & offensive rookie numbers.\n\n**Yes:** 7'4\" frame with guard skills and DPOY-level rim protection means multiple MVPs and titles are guaranteed if healthy.\n**No:** Injuries, modern physical wear, and team success in the competitive West make entering the Top 10 (beating Kobe, Duncan, Shaq, Bird) an insanely high bar.\n\nDo you believe the hype?",
        "options": ["🚀 Yes, Top 10 lock", "🛑 No, Top 10 is too high"],
        "hot_take": "Does Wemby pass Tim Duncan as the greatest Spur ever?"
    }
]

# ── Start, Bench, Cut Challenges ──────────────────────────────────────────────

SBC_CHALLENGES: List[Dict[str, Any]] = [
    {
        "title": "✂️ Start, Bench, Cut: Prime Explosive Point Guards",
        "players": ["Prime Derrick Rose (2011 MVP)", "Prime Russell Westbrook (2017 MVP)", "Prime Kyrie Irving (2016 Finals)"],
        "context": "All three at their absolute peak speed, athleticism, and skill. Who is in your starting lineup, who sits on the bench, and who gets cut completely?"
    },
    {
        "title": "✂️ Start, Bench, Cut: 2000s Pure Scoring Wings",
        "players": ["Prime Carmelo Anthony (Nuggets)", "Prime Tracy McGrady (Magic)", "Prime Vince Carter (Raptors/Nets)"],
        "context": "Three of the most unstoppable pure scoring wings in basketball history. You need a bucket to save your life. Pick your order!"
    },
    {
        "title": "✂️ Start, Bench, Cut: Modern Alpha Wings",
        "players": ["Jayson Tatum", "Luka Dončić", "Anthony Edwards"],
        "context": "Game 7 of the NBA Finals. You need one to Start, one to come off the Bench as 6th man, and one has to be Cut."
    },
    {
        "title": "✂️ Start, Bench, Cut: Unstoppable Big Men",
        "players": ["Prime Dwight Howard (3x DPOY)", "Prime Anthony Davis (Pelicans/2020)", "Prime Joel Embiid (MVP)"],
        "context": "Anchoring your paint and rim defense. Who are you starting, benching, and cutting?"
    },
    {
        "title": "✂️ Start, Bench, Cut: Lethal 3-Point Snipers",
        "players": ["Ray Allen", "Klay Thompson", "Reggie Miller"],
        "context": "Down 3 points, final possession of the season. Who starts, who benches, and who gets cut?"
    }
]

# ── Helper: Dynamic Multi-Option Vote Tally Formatter ─────────────────────────

def format_vote_tally(options: List[str], counts: Dict[int, int]) -> str:
    """Dynamically calculates and formats live vote bars for 2, 3, or 4 options."""
    total = sum(counts.values())
    lines = []
    for idx, opt_label in enumerate(options):
        cnt = counts.get(idx, 0)
        pct = int((cnt / total) * 100) if total > 0 else 0
        filled = min(10, max(0, pct // 10))
        bar = "█" * filled + "░" * (10 - filled)
        lines.append(f"**{opt_label}**\n`[{bar}]` **{pct}%** ({cnt} votes)")

    lines.append(f"\n👥 *Total Votes Cast: `{total}`*")
    return "\n\n".join(lines)

def parse_existing_tally(embed: discord.Embed, options: List[str]) -> Dict[int, int]:
    """Parses existing vote counts from the embed text so votes are never lost on restart."""
    counts = {i: 0 for i in range(len(options))}
    if not embed or not embed.fields:
        return counts

    field_text = ""
    for f in embed.fields:
        if "Live Server Vote" in f.name:
            field_text = f.value
            break

    if not field_text:
        return counts

    # Regex search for: **Option Name** ... (X votes)
    for idx, opt in enumerate(options):
        # Escape option text for regex matching
        clean_opt = re.escape(opt)
        pattern = rf"\*\*{clean_opt}\*\*.*?\((\d+)\s+votes\)"
        match = re.search(pattern, field_text, re.DOTALL)
        if match:
            try:
                counts[idx] = int(match.group(1))
            except Exception:
                pass
    return counts


# ── Interactive Voting View ───────────────────────────────────────────────────

class DebateVoteView(discord.ui.View):
    def __init__(self, debate_data: Dict[str, Any]):
        super().__init__(timeout=None)  # Persistent view
        self.debate_data = debate_data
        self.options = debate_data.get("options", ["Option A", "Option B"])

        styles = [
            discord.ButtonStyle.primary,    # Blurple
            discord.ButtonStyle.success,    # Green
            discord.ButtonStyle.danger,     # Red
            discord.ButtonStyle.secondary   # Grey
        ]

        # Row 0: Player option buttons (max 4)
        for idx, opt_label in enumerate(self.options):
            style = styles[idx % len(styles)]
            btn = discord.ui.Button(
                label=opt_label[:80],
                style=style,
                custom_id=f"vote_{debate_data['id']}_{idx}",
                row=0
            )
            self.add_item(btn)

        # Row 1: Dedicated discussion thread button
        thread_btn = discord.ui.Button(
            label="💬 Join Debate in Thread",
            style=discord.ButtonStyle.secondary,
            custom_id=f"thread_{debate_data['id']}",
            row=1
        )
        self.add_item(thread_btn)


# ── Main Cog Implementation ───────────────────────────────────────────────────

class BasketballDebates(commands.Cog):
    """Automated Basketball Debates & Community Engagement Engine for SpaceYT."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = load_config()
        self.daily_debate_loop.start()
        logger.info("BasketballDebates Cog initialized and automated loop started.")

    def cog_unload(self):
        self.daily_debate_loop.cancel()
        logger.info("BasketballDebates Cog unloaded and loop cancelled.")

    # ── Bulletproof Persistent Interaction Listener ───────────────────────────
    # Catches all button clicks even if the bot restarted or view is not in memory!
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        if not (custom_id.startswith("vote_") or custom_id.startswith("thread_")):
            return

        # 1. Handle Thread Button Click
        if custom_id.startswith("thread_"):
            msg = interaction.message
            if not msg:
                await interaction.response.send_message("❌ Message not found.", ephemeral=True)
                return

            if msg.thread:
                await interaction.response.send_message(f"👉 Jump into the debate here: {msg.thread.mention}", ephemeral=True)
                return

            try:
                topic_title = msg.embeds[0].title if msg.embeds else "Basketball Debate"
                thread = await msg.create_thread(name=topic_title[:80], auto_archive_duration=1440)
                await thread.send(
                    f"🔥 **SpaceYT Debate Floor is OPEN!**\n"
                    f"Drop your takes, back up your player, and trash talk respectfully! Tag `@Sweety` if you want AI analysis."
                )
                await interaction.response.send_message(f"🚀 Thread created! Join here: {thread.mention}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Could not create thread: {e}", ephemeral=True)
            return

        # 2. Handle Vote Button Click
        if custom_id.startswith("vote_"):
            msg = interaction.message
            if not msg or not msg.embeds:
                await interaction.response.send_message("❌ Cannot record vote on this message.", ephemeral=True)
                return

            parts = custom_id.split("_")
            try:
                selected_idx = int(parts[-1])
            except ValueError:
                await interaction.response.send_message("❌ Invalid vote action.", ephemeral=True)
                return

            embed = msg.embeds[0]

            # Extract option names from message buttons
            options = []
            if msg.components:
                for row in msg.components:
                    for comp in row.children:
                        if comp.custom_id and comp.custom_id.startswith("vote_"):
                            options.append(comp.label)

            if not options or selected_idx >= len(options):
                await interaction.response.send_message("❌ Option index out of range.", ephemeral=True)
                return

            chosen_player = options[selected_idx]
            msg_id_str = str(msg.id)
            user_id_str = str(interaction.user.id)

            # Check persistent memory of user votes
            user_votes = self.config.setdefault("user_votes", {}).setdefault(msg_id_str, {})
            prev_vote_idx = user_votes.get(user_id_str)

            # Parse existing tally from embed
            counts = parse_existing_tally(embed, options)

            # If user already voted for this exact option, no change needed
            if prev_vote_idx == selected_idx:
                await interaction.response.send_message(f"✅ You already voted for **{chosen_player}**!", ephemeral=True)
                return

            # If user changed their vote, decrement previous option
            if prev_vote_idx is not None and prev_vote_idx < len(options):
                counts[prev_vote_idx] = max(0, counts.get(prev_vote_idx, 1) - 1)

            # Increment selected option
            counts[selected_idx] = counts.get(selected_idx, 0) + 1
            user_votes[user_id_str] = selected_idx
            save_config(self.config)

            # Update embed with new tally
            new_tally_text = format_vote_tally(options, counts)

            field_index = None
            for i, f in enumerate(embed.fields):
                if "Live Server Vote" in f.name:
                    field_index = i
                    break

            if field_index is not None:
                embed.set_field_at(field_index, name="📊 Live Server Vote Tally", value=new_tally_text, inline=False)
            else:
                embed.add_field(name="📊 Live Server Vote Tally", value=new_tally_text, inline=False)

            try:
                await msg.edit(embed=embed)
            except Exception as edit_err:
                logger.error(f"Failed to edit vote embed: {edit_err}")

            if prev_vote_idx is not None:
                await interaction.response.send_message(f"🔄 Switched your vote to **{chosen_player}**!", ephemeral=True)
            else:
                await interaction.response.send_message(f"✅ Voted for **{chosen_player}**! Join the thread to defend your take!", ephemeral=True)

    def build_debate_embed(self, debate: Dict[str, Any]) -> discord.Embed:
        embed = discord.Embed(
            title=f"🏀 {debate.get('title', 'SpaceYT Basketball Debate')}",
            description=f"{debate.get('description', '')}\n\n🔥 **Hot Take:** *{debate.get('hot_take', 'Drop your take below!')}*",
            color=discord.Color.from_rgb(255, 102, 0)  # Basketball Orange
        )
        embed.set_author(
            name=f"SpaceYT Basketball Arena • {debate.get('category', 'DEBATE')}",
            icon_url="https://cdn-icons-png.flankfast.com/512/889/889508.png"
        )
        
        # Build initial zero-vote tally dynamically for all options
        initial_lines = []
        for opt in debate.get("options", ["Option A", "Option B"]):
            initial_lines.append(f"**{opt}**\n`[░░░░░░░░░░]` **0%** (0 votes)")
        initial_lines.append("👉 *Click a button below to cast your vote!*")

        embed.add_field(
            name="📊 Live Server Vote Tally",
            value="\n\n".join(initial_lines),
            inline=False
        )

        embed.set_footer(
            text="SpaceYT Official Community • Click below to vote & discuss",
            icon_url=self.bot.user.display_avatar.url if self.bot.user else None
        )
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        return embed

    async def post_debate_message(self, channel: discord.TextChannel, debate: Optional[Dict[str, Any]] = None) -> Optional[discord.Message]:
        if not debate:
            # Pick a debate from bank that hasn't been posted recently
            history = self.config.get("history", [])
            available = [d for d in DEBATES_BANK if d["id"] not in history]
            if not available:
                # Reset history if all have been cycled
                self.config["history"] = []
                available = DEBATES_BANK

            debate = random.choice(available)
            self.config.setdefault("history", []).append(debate["id"])
            save_config(self.config)

        embed = self.build_debate_embed(debate)
        view = DebateVoteView(debate)

        header_text = "📢 **NEW BASKETBALL DEBATE DROPPED! 🏀** Cast your vote and defend your take!"
        if self.config.get("mention_everyone", False):
            header_text = f"@everyone {header_text}"

        try:
            msg = await channel.send(content=header_text, embed=embed, view=view)

            # Auto-create discussion thread if enabled
            if self.config.get("auto_create_thread", True):
                try:
                    thread_name = f"🏀・{debate.get('title', 'Debate')[:85]}"
                    thread = await msg.create_thread(name=thread_name, auto_archive_duration=1440)
                    await thread.send(
                        f"🔥 **SpaceYT Debate Floor is OPEN!**\n"
                        f"> **Topic:** {debate.get('title')}\n"
                        f"> *\"{debate.get('hot_take')}\"*\n\n"
                        f"Who's got the better argument? Drop your takes below! 🎤"
                    )
                except Exception as t_err:
                    logger.warning(f"Could not auto-create thread: {t_err}")

            return msg
        except Exception as e:
            logger.error(f"Failed to post debate message: {e}")
            return None

    # ── Background Task Loop (Every 12 Hours) ─────────────────────────────────

    @tasks.loop(hours=12)
    async def daily_debate_loop(self):
        await self.bot.wait_until_ready()
        if not self.config.get("auto_post_enabled", True):
            return

        channel_id = self.config.get("channel_id")
        if not channel_id:
            logger.info("Basketball debate channel not configured yet. Skipping scheduled post.")
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception as e:
                logger.warning(f"Failed to fetch debate channel {channel_id}: {e}")
                return

        logger.info(f"Auto-posting scheduled basketball debate to #{channel.name}...")
        await self.post_debate_message(channel)

    @daily_debate_loop.before_loop
    async def before_daily_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)

    # ── Slash & Prefix Commands ───────────────────────────────────────────────

    @app_commands.command(name="debate", description="🏀 Trigger an instant spicy NBA/Basketball debate with live voting buttons")
    @app_commands.describe(channel="Channel to post the debate in (defaults to current channel)")
    @app_commands.guild_only()
    async def debate_slash(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        target_channel = channel or interaction.channel
        await interaction.response.defer(thinking=True, ephemeral=True)

        msg = await self.post_debate_message(target_channel)
        if msg:
            await interaction.followup.send(f"✅ Basketball debate successfully posted in {target_channel.mention}!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed to post debate. Please check channel permissions.", ephemeral=True)

    @app_commands.command(name="startbenchcut", description="✂️ Post a Start, Bench, Cut basketball challenge")
    @app_commands.guild_only()
    async def startbenchcut_slash(self, interaction: discord.Interaction):
        challenge = random.choice(SBC_CHALLENGES)
        embed = discord.Embed(
            title=challenge["title"],
            description=f"{challenge['context']}\n\n"
                        f"1️⃣ **{challenge['players'][0]}**\n"
                        f"2️⃣ **{challenge['players'][1]}**\n"
                        f"3️⃣ **{challenge['players'][2]}**\n\n"
                        f"👉 **Who are you STARTING? Who are you BENCHING? Who are you CUTTING?**\n"
                        f"*Drop your 1-2-3 combo in chat!*",
            color=discord.Color.from_rgb(255, 69, 0)
        )
        embed.set_author(name="SpaceYT NBA Challenge", icon_url="https://cdn-icons-png.flankfast.com/512/889/889508.png")
        embed.set_footer(text="SpaceYT Basketball Arena • Drop your choices below!")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setdebatechannel", description="⚙️ Set the channel for automated daily basketball debates")
    @app_commands.describe(channel="The channel where daily basketball debates should be posted")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def setdebatechannel_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.config["channel_id"] = channel.id
        self.config["auto_post_enabled"] = True
        save_config(self.config)
        await interaction.response.send_message(
            f"✅ **Automated Basketball Debates Enabled!**\nDaily debates will now automatically post into {channel.mention} every 12 hours."
        )

    @app_commands.command(name="toggledebates", description="⚙️ Enable or disable automatic daily basketball debates")
    @app_commands.describe(status="Turn daily debates on or off")
    @app_commands.choices(status=[
        app_commands.Choice(name="Enable (On)", value="on"),
        app_commands.Choice(name="Disable (Off)", value="off")
    ])
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def toggledebates_slash(self, interaction: discord.Interaction, status: app_commands.Choice[str]):
        enabled = (status.value == "on")
        self.config["auto_post_enabled"] = enabled
        save_config(self.config)
        msg = "✅ Automated basketball debates are now **ENABLED**." if enabled else "⚙️ Automated basketball debates are now **DISABLED**."
        await interaction.response.send_message(msg)

    # ── Prefix Commands ───────────────────────────────────────────────────────

    @commands.command(name="debate", aliases=["nbadebate", "bballdebate"])
    @commands.guild_only()
    async def debate_prefix(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Trigger an instant basketball debate: !debate [#channel]"""
        target = channel or ctx.channel
        await self.post_debate_message(target)

    @commands.command(name="startbenchcut", aliases=["sbc"])
    @commands.guild_only()
    async def sbc_prefix(self, ctx: commands.Context):
        """Start, Bench, Cut basketball challenge: !sbc"""
        challenge = random.choice(SBC_CHALLENGES)
        embed = discord.Embed(
            title=challenge["title"],
            description=f"{challenge['context']}\n\n"
                        f"1️⃣ **{challenge['players'][0]}**\n"
                        f"2️⃣ **{challenge['players'][1]}**\n"
                        f"3️⃣ **{challenge['players'][2]}**\n\n"
                        f"👉 **Who are you STARTING? Who are you BENCHING? Who are you CUTTING?**\n"
                        f"*Drop your 1-2-3 combo in chat!*",
            color=discord.Color.from_rgb(255, 69, 0)
        )
        embed.set_author(name="SpaceYT NBA Challenge", icon_url="https://cdn-icons-png.flankfast.com/512/889/889508.png")
        embed.set_footer(text="SpaceYT Basketball Arena • Drop your choices below!")
        await ctx.send(embed=embed)

    @commands.command(name="setdebatechannel")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setdebatechannel_prefix(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set automated debate channel: !setdebatechannel #channel"""
        self.config["channel_id"] = channel.id
        self.config["auto_post_enabled"] = True
        save_config(self.config)
        await ctx.send(f"✅ Daily basketball debates will now automatically post into {channel.mention} every 12 hours!")


async def setup(bot: commands.Bot):
    await bot.add_cog(BasketballDebates(bot))
