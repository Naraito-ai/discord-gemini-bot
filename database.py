import os
import json
import logging
import asyncio
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger("GeminiBot.Database")

class DatabaseManager:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.is_postgres = False
        self.pg_pool = None
        self.sqlite_conn = None
        self._sqlite_lock = asyncio.Lock()  # Prevent SQLite write locks
        self._config_cache: Dict[tuple, Any] = {}  # Cache for guild configurations

        # Detect database type
        if self.db_url and (self.db_url.startswith("postgres://") or self.db_url.startswith("postgresql://")):
            self.is_postgres = True
            # asyncpg requires postgresql:// protocol
            if self.db_url.startswith("postgres://"):
                self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)

    async def initialize(self):
        """Initializes connection pools and creates tables if they do not exist."""
        if self.is_postgres:
            try:
                import asyncpg
                logger.info("Initializing PostgreSQL database connection...")
                self.pg_pool = await asyncpg.create_pool(self.db_url, min_size=1, max_size=10)
                logger.info("PostgreSQL connection pool created successfully.")
            except ImportError:
                logger.error("asyncpg is not installed, falling back to SQLite!")
                self.is_postgres = False
            except Exception as e:
                logger.error(f"Failed to connect to PostgreSQL: {e}. Falling back to SQLite!")
                self.is_postgres = False

        if not self.is_postgres:
            import aiosqlite
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")
            logger.info(f"Initializing local SQLite database at {db_path}...")
            self.sqlite_conn = await aiosqlite.connect(db_path)
            # Enable WAL mode for better concurrency in SQLite
            await self.sqlite_conn.execute("PRAGMA journal_mode=WAL;")
            await self.sqlite_conn.commit()

        # Create tables
        await self._create_tables()

    async def _create_tables(self):
        """Creates database schema for all bot modules and dashboard tracking."""
        queries = [
            # Guilds Table
            """
            CREATE TABLE IF NOT EXISTS guilds (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                icon TEXT,
                owner_id TEXT,
                member_count INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ai_enabled BOOLEAN DEFAULT TRUE,
                logging_enabled BOOLEAN DEFAULT FALSE
            );
            """,
            # Guild Resources
            """
            CREATE TABLE IF NOT EXISTS guild_resources (
                guild_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id BIGINT NOT NULL
            );
            """,
            # Guild Config
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (guild_id, key)
            );
            """,
            # Users Table
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                discriminator TEXT,
                avatar TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Commands Tracking Table
            """
            CREATE TABLE IF NOT EXISTS commands (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                user_id TEXT,
                command_name TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                latency REAL
            );
            """,
            # Warnings Table
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Timeouts Table
            """
            CREATE TABLE IF NOT EXISTS timeouts (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Bans Table
            """
            CREATE TABLE IF NOT EXISTS bans (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # AI Usage Tracking Table
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                user_id TEXT,
                prompt TEXT,
                response TEXT,
                model TEXT,
                tokens_used INTEGER DEFAULT 0,
                latency REAL DEFAULT 0.0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # API Usage Table
            """
            CREATE TABLE IF NOT EXISTS api_usage (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                endpoint TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Backups Table
            """
            CREATE TABLE IF NOT EXISTS backups (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                backup_data TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Audit Logs Table
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Notifications Table
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                type TEXT NOT NULL,
                read BOOLEAN DEFAULT FALSE,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Errors Table
            """
            CREATE TABLE IF NOT EXISTS errors (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                stack_trace TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Analytics Table
            """
            CREATE TABLE IF NOT EXISTS analytics (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                date DATE DEFAULT CURRENT_DATE,
                messages_count INTEGER DEFAULT 0,
                commands_count INTEGER DEFAULT 0,
                joins_count INTEGER DEFAULT 0,
                leaves_count INTEGER DEFAULT 0,
                warnings_count INTEGER DEFAULT 0,
                mutes_count INTEGER DEFAULT 0,
                bans_count INTEGER DEFAULT 0,
                voice_active_seconds INTEGER DEFAULT 0
            );
            """,
            # Reminders Table
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                guild_id TEXT,
                channel_id TEXT NOT NULL,
                reminder_text TEXT NOT NULL,
                remind_at REAL NOT NULL,
                created_at REAL NOT NULL,
                delivery_method TEXT DEFAULT 'dm'
            );
            """,
            # AFK Users Table
            """
            CREATE TABLE IF NOT EXISTS afk_users (
                user_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                afk_since REAL NOT NULL,
                PRIMARY KEY (user_id, guild_id)
            );
            """,
            # Dream Teams Table ($15 All-Time Lineup Builder)
            """
            CREATE TABLE IF NOT EXISTS dream_teams (
                user_id TEXT PRIMARY KEY,
                guild_id TEXT,
                pg TEXT NOT NULL,
                sg TEXT NOT NULL,
                sf TEXT NOT NULL,
                pf TEXT NOT NULL,
                c TEXT NOT NULL,
                total_cost INTEGER NOT NULL,
                ovr_rating REAL NOT NULL,
                team_data TEXT,
                updated_at REAL NOT NULL
            );
            """,
            # Team Battle Stats & Career Records Table
            """
            CREATE TABLE IF NOT EXISTS team_battle_stats (
                user_id TEXT PRIMARY KEY,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                ties INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                total_duels_won INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                daily_wins INTEGER DEFAULT 0,
                last_daily_win_date TEXT DEFAULT '',
                achievements TEXT DEFAULT '[]',
                coaching_dna TEXT DEFAULT '{}',
                updated_at REAL NOT NULL
            );
            """,
            # Head-to-Head NBA Member Rivalries Table
            """
            CREATE TABLE IF NOT EXISTS nba_rivalries (
                player_a TEXT NOT NULL,
                player_b TEXT NOT NULL,
                wins_a INTEGER DEFAULT 0,
                wins_b INTEGER DEFAULT 0,
                ties INTEGER DEFAULT 0,
                last_5 TEXT DEFAULT '[]',
                updated_at REAL NOT NULL,
                PRIMARY KEY (player_a, player_b)
            );
            """,
            # User Snipe 30-Day History Table
            """
            CREATE TABLE IF NOT EXISTS user_snipe_history (
                id SERIAL PRIMARY KEY,
                message_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                channel_name TEXT DEFAULT '',
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                user_display_name TEXT DEFAULT '',
                user_avatar TEXT,
                content TEXT,
                attachments_json TEXT DEFAULT '[]',
                stickers_json TEXT DEFAULT '[]',
                message_type TEXT DEFAULT 'deleted',
                before_content TEXT,
                after_content TEXT,
                created_at REAL NOT NULL,
                recorded_at REAL NOT NULL
            );
            """,
            # Fast index for 30-day user snipe lookup
            """
            CREATE INDEX IF NOT EXISTS idx_user_snipe_lookup ON user_snipe_history(guild_id, user_id, recorded_at);
            """,
            # Active Scheduled Mutes Table (7-Day Role Mute Tracking)
            """
            CREATE TABLE IF NOT EXISTS active_mutes (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role_id TEXT,
                unmute_at REAL NOT NULL,
                reason TEXT,
                created_at REAL NOT NULL,
                UNIQUE(guild_id, user_id)
            );
            """,
            # Appeal Tickets Table
            """
            CREATE TABLE IF NOT EXISTS appeal_tickets (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                reason TEXT,
                additional_info TEXT,
                created_at REAL NOT NULL,
                resolved_at REAL,
                resolved_by TEXT
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_active_mutes ON active_mutes(guild_id, user_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_appeal_tickets ON appeal_tickets(channel_id, status);
            """,
            # User Memories Table (Persistent AI Memory & Personalization)
            """
            CREATE TABLE IF NOT EXISTS user_memories (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                guild_id TEXT,
                fact_key TEXT NOT NULL,
                fact_value TEXT NOT NULL,
                source TEXT DEFAULT 'manual',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(user_id, fact_key)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_user_memories_lookup ON user_memories(user_id, updated_at);
            """
        ]
        
        for query in queries:
            await self.execute(query)

        # Non-destructive column migrations
        try:
            if not self.is_postgres:
                cols = await self.fetch("PRAGMA table_info(team_battle_stats);")
                col_names = [c["name"] for c in cols] if cols else []
                if "daily_wins" not in col_names:
                    await self.execute("ALTER TABLE team_battle_stats ADD COLUMN daily_wins INTEGER DEFAULT 0;")
                if "last_daily_win_date" not in col_names:
                    await self.execute("ALTER TABLE team_battle_stats ADD COLUMN last_daily_win_date TEXT DEFAULT '';")
                if "coaching_dna" not in col_names:
                    await self.execute("ALTER TABLE team_battle_stats ADD COLUMN coaching_dna TEXT DEFAULT '{}';")
            else:
                await self.execute("ALTER TABLE team_battle_stats ADD COLUMN IF NOT EXISTS daily_wins INTEGER DEFAULT 0;")
                await self.execute("ALTER TABLE team_battle_stats ADD COLUMN IF NOT EXISTS last_daily_win_date TEXT DEFAULT '';")
                await self.execute("ALTER TABLE team_battle_stats ADD COLUMN IF NOT EXISTS coaching_dna TEXT DEFAULT '{}';")
        except Exception as alter_err:
            logger.debug(f"Column check for team_battle_stats: {alter_err}")
            
        logger.info("Database tables verified/created successfully.")

    async def execute(self, query: str, *args):
        """Executes a write query (INSERT, UPDATE, DELETE)."""
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                # asyncpg uses $1, $2 for placeholders instead of ? (SQLite)
                pg_query = query
                if "?" in query:
                    parts = query.split("?")
                    pg_query = "".join(f"{part}${i+1}" for i, part in enumerate(parts[:-1])) + parts[-1]
                await conn.execute(pg_query, *args)
        else:
            async with self._sqlite_lock:
                sqlite_query = query
                if "SERIAL PRIMARY KEY" in sqlite_query:
                    sqlite_query = sqlite_query.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                await self.sqlite_conn.execute(sqlite_query, args)
                await self.sqlite_conn.commit()

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """Fetches multiple records as a list of dicts."""
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                pg_query = query
                if "?" in query:
                    parts = query.split("?")
                    pg_query = "".join(f"{part}${i+1}" for i, part in enumerate(parts[:-1])) + parts[-1]
                records = await conn.fetch(pg_query, *args)
                return [dict(r) for r in records]
        else:
            async with self._sqlite_lock:
                sqlite_query = query
                if "SERIAL PRIMARY KEY" in sqlite_query:
                    sqlite_query = sqlite_query.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                async with self.sqlite_conn.execute(sqlite_query, args) as cursor:
                    rows = await cursor.fetchall()
                    if cursor.description is None:
                        return []
                    columns = [description[0] for description in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]

    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Fetches a single record as a dict."""
        results = await self.fetch(query, *args)
        return results[0] if results else None

    # ── Resource Management Queries ─────────────────────────────────────────

    async def add_resource(self, guild_id: Any, resource_type: str, resource_id: Any):
        """Saves a created role, channel, or category to the database."""
        query = "INSERT INTO guild_resources (guild_id, resource_type, resource_id) VALUES (?, ?, ?)"
        await self.execute(query, str(guild_id), resource_type, int(resource_id))

    async def get_resources(self, guild_id: Any, resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gets all resources of a type for a guild."""
        if resource_type:
            query = "SELECT resource_id FROM guild_resources WHERE guild_id = ? AND resource_type = ?"
            rows = await self.fetch(query, str(guild_id), resource_type)
        else:
            query = "SELECT resource_type, resource_id FROM guild_resources WHERE guild_id = ?"
            rows = await self.fetch(query, str(guild_id))
        return rows

    async def clear_resources(self, guild_id: Any):
        """Deletes all tracked resource records for a guild from the database."""
        query = "DELETE FROM guild_resources WHERE guild_id = ?"
        await self.execute(query, str(guild_id))

    # ── Guild Configuration Queries ──────────────────────────────────────────

    async def set_config(self, guild_id: Any, key: str, value: Any):
        """Sets a configuration option with atomic upsert."""
        query = """
            INSERT INTO guild_config (guild_id, key, value) 
            VALUES (?, ?, ?) 
            ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value
        """
        await self.execute(query, str(guild_id), key, str(value))
        
        # Update cache
        self._config_cache[(str(guild_id), key)] = str(value)

    def _parse_config_value(self, val: Any) -> Any:
        if val == "True" or val is True: return True
        if val == "False" or val is False: return False
        if val == "None" or val is None: return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return val

    async def get_config(self, guild_id: Any, key: str, default: Any = None) -> Any:
        """Gets a configuration option with caching."""
        cache_key = (str(guild_id), key)
        if cache_key in self._config_cache:
            val = self._config_cache[cache_key]
            return self._parse_config_value(val)

        query = "SELECT value FROM guild_config WHERE guild_id = ? AND key = ?"
        row = await self.fetchrow(query, str(guild_id), key)
        if row:
            val = row["value"]
            self._config_cache[cache_key] = val
            return self._parse_config_value(val)
        
        # Cache negative/default values too to prevent repeat misses
        self._config_cache[cache_key] = "None" if default is None else str(default)
        return default

    # ── Dashboard Helper Queries ──────────────────────────────────────────

    async def increment_analytics(self, guild_id: Any, column_name: str, amount: int = 1):
        """Increments a specific statistic counter in the analytics table for today."""
        # Whitelist columns to prevent any arbitrary injection
        valid_columns = {
            "messages_count", "commands_count", "joins_count", "leaves_count",
            "warnings_count", "mutes_count", "bans_count", "voice_active_seconds"
        }
        if column_name not in valid_columns:
            logger.warning(f"Invalid analytics column name: {column_name}")
            return

        try:
            today_str = datetime.now().date().isoformat()
            rows = await self.fetch(
                "SELECT id FROM analytics WHERE guild_id = ? AND date = ?",
                str(guild_id),
                today_str
            )
            if rows:
                query = f"UPDATE analytics SET {column_name} = {column_name} + ? WHERE guild_id = ? AND date = ?"
                await self.execute(query, amount, str(guild_id), today_str)
            else:
                query = f"INSERT INTO analytics (guild_id, date, {column_name}) VALUES (?, ?, ?)"
                await self.execute(query, str(guild_id), today_str, amount)
        except Exception as e:
            logger.error(f"Failed to increment analytics: {e}")

    async def log_command(self, guild_id: Any, user_id: Any, command_name: str, status: str, latency: float):
        """Logs a slash command execution."""
        query = "INSERT INTO commands (guild_id, user_id, command_name, status, latency) VALUES (?, ?, ?, ?, ?)"
        await self.execute(query, str(guild_id) if guild_id else None, str(user_id), command_name, status, latency)
        if guild_id:
            await self.increment_analytics(guild_id, "commands_count")

    async def log_ai_usage(self, guild_id: Any, user_id: Any, prompt: str, response: str, model: str, tokens_used: int, latency: float):
        """Logs an AI query usage entry."""
        query = "INSERT INTO ai_usage (guild_id, user_id, prompt, response, model, tokens_used, latency) VALUES (?, ?, ?, ?, ?, ?, ?)"
        await self.execute(query, str(guild_id) if guild_id else None, str(user_id), prompt, response, model, tokens_used, latency)

    async def add_warning(self, guild_id: Any, user_id: Any, moderator_id: Any, reason: str):
        """Logs a member warning."""
        query = "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), str(moderator_id), reason)
        await self.increment_analytics(guild_id, "warnings_count")

    async def get_warnings(self, guild_id: Any, user_id: Any) -> list:
        """Retrieves all warnings for a user in a guild."""
        query = "SELECT id, moderator_id, reason, timestamp FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC"
        return await self.fetch(query, str(guild_id), str(user_id))

    async def clear_warnings(self, guild_id: Any, user_id: Any, amount: Optional[int] = None) -> int:
        """Deletes warnings for a user in a guild (all or limited amount) and returns count deleted."""
        if amount is not None and amount > 0:
            rows = await self.fetch(
                "SELECT id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC, id DESC LIMIT ?",
                str(guild_id), str(user_id), int(amount)
            )
            if not rows:
                return 0
            ids = [r["id"] if isinstance(r, dict) and "id" in r else r[0] for r in rows]
            placeholders = ", ".join(["?"] * len(ids))
            query = f"DELETE FROM warnings WHERE id IN ({placeholders})"
            await self.execute(query, *ids)
            return len(ids)
        else:
            rows = await self.fetch("SELECT COUNT(*) as count FROM warnings WHERE guild_id = ? AND user_id = ?", str(guild_id), str(user_id))
            count = rows[0]["count"] if rows and isinstance(rows[0], dict) and "count" in rows[0] else (rows[0][0] if rows else 0)
            query = "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?"
            await self.execute(query, str(guild_id), str(user_id))
            return int(count)

    async def delete_warning_by_id(self, guild_id: Any, warn_id: int) -> bool:
        """Deletes a specific warning by its ID. Returns True if deleted, False if not found."""
        rows = await self.fetch("SELECT id FROM warnings WHERE guild_id = ? AND id = ?", str(guild_id), int(warn_id))
        if not rows:
            return False
        await self.execute("DELETE FROM warnings WHERE guild_id = ? AND id = ?", str(guild_id), int(warn_id))
        return True

    async def get_warnings_leaderboard(self, guild_id: Any, limit: int = 10) -> list:
        """Retrieves top warned members in a guild."""
        query = """
            SELECT user_id, COUNT(*) as warn_count, MAX(timestamp) as latest_warn
            FROM warnings
            WHERE guild_id = ?
            GROUP BY user_id
            ORDER BY warn_count DESC, latest_warn DESC
            LIMIT ?
        """
        return await self.fetch(query, str(guild_id), int(limit))

    async def add_timeout(self, guild_id: Any, user_id: Any, moderator_id: Any, duration_seconds: int, reason: str):
        """Logs a member timeout."""
        query = "INSERT INTO timeouts (guild_id, user_id, moderator_id, duration_seconds, reason) VALUES (?, ?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), str(moderator_id), duration_seconds, reason)
        await self.increment_analytics(guild_id, "mutes_count")

    async def add_ban(self, guild_id: Any, user_id: Any, moderator_id: Any, reason: str):
        """Logs a member ban."""
        query = "INSERT INTO bans (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), str(moderator_id), reason)
        await self.increment_analytics(guild_id, "bans_count")

    async def log_audit(self, guild_id: Any, user_id: Any, action: str, details: str = None):
        """Logs a dashboard or moderator action."""
        query = "INSERT INTO audit_logs (guild_id, user_id, action, details) VALUES (?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), action, details)

    # ── Reminders Methods ───────────────────────────────────────────────────
    async def add_reminder(self, reminder_id: str, user_id: Any, guild_id: Any, channel_id: Any, reminder_text: str, remind_at: float, created_at: float, delivery_method: str = "dm") -> bool:
        """Stores a scheduled reminder."""
        await self.execute(
            "INSERT INTO reminders (id, user_id, guild_id, channel_id, reminder_text, remind_at, created_at, delivery_method) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            str(reminder_id), str(user_id), str(guild_id) if guild_id else None, str(channel_id), reminder_text, float(remind_at), float(created_at), delivery_method
        )
        return True

    async def get_due_reminders(self, current_time: float) -> List[Dict[str, Any]]:
        """Fetches all reminders that are due to be delivered."""
        return await self.fetch(
            "SELECT id, user_id, guild_id, channel_id, reminder_text, remind_at, created_at, delivery_method FROM reminders WHERE remind_at <= ?",
            float(current_time)
        )

    async def delete_reminder(self, reminder_id: str) -> bool:
        """Deletes a reminder after delivery or upon user cancellation."""
        await self.execute(
            "DELETE FROM reminders WHERE id = ?",
            str(reminder_id)
        )
        return True

    async def get_user_reminders(self, user_id: Any) -> List[Dict[str, Any]]:
        """Fetches all active pending reminders for a user."""
        return await self.fetch(
            "SELECT id, guild_id, channel_id, reminder_text, remind_at, created_at, delivery_method FROM reminders WHERE user_id = ? ORDER BY remind_at ASC",
            str(user_id)
        )

    # ── AFK System Methods ──────────────────────────────────────────────────
    async def set_afk(self, user_id: Any, guild_id: Any, reason: str, afk_since: float) -> bool:
        """Sets AFK status for a user in a specific guild."""
        if self.is_postgres:
            query = "INSERT INTO afk_users (user_id, guild_id, reason, afk_since) VALUES (?, ?, ?, ?) ON CONFLICT (user_id, guild_id) DO UPDATE SET reason = EXCLUDED.reason, afk_since = EXCLUDED.afk_since"
        else:
            query = "INSERT OR REPLACE INTO afk_users (user_id, guild_id, reason, afk_since) VALUES (?, ?, ?, ?)"
        return await self.execute(query, str(user_id), str(guild_id), reason, float(afk_since))

    async def remove_afk(self, user_id: Any, guild_id: Any) -> bool:
        """Removes AFK status for a user in a guild."""
        return await self.execute(
            "DELETE FROM afk_users WHERE user_id = ? AND guild_id = ?",
            str(user_id), str(guild_id)
        )

    async def get_all_afk_users(self) -> List[Dict[str, Any]]:
        """Loads all AFK records from database on startup."""
        return await self.fetch("SELECT user_id, guild_id, reason, afk_since FROM afk_users")

    # ── Dream Teams ($15 All-Time Builder) ──────────────────────────────────
    async def save_dream_team(self, user_id: Any, guild_id: Any, pg: str, sg: str, sf: str, pf: str, c: str, total_cost: int, ovr_rating: float, team_data: str, updated_at: float) -> bool:
        """Saves or updates a user's $15 Dream Team lineup."""
        if self.is_postgres:
            query = "INSERT INTO dream_teams (user_id, guild_id, pg, sg, sf, pf, c, total_cost, ovr_rating, team_data, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (user_id) DO UPDATE SET guild_id = EXCLUDED.guild_id, pg = EXCLUDED.pg, sg = EXCLUDED.sg, sf = EXCLUDED.sf, pf = EXCLUDED.pf, c = EXCLUDED.c, total_cost = EXCLUDED.total_cost, ovr_rating = EXCLUDED.ovr_rating, team_data = EXCLUDED.team_data, updated_at = EXCLUDED.updated_at"
        else:
            query = "INSERT OR REPLACE INTO dream_teams (user_id, guild_id, pg, sg, sf, pf, c, total_cost, ovr_rating, team_data, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        await self.execute(query, str(user_id), str(guild_id) if guild_id else None, pg, sg, sf, pf, c, int(total_cost), float(ovr_rating), team_data, float(updated_at))
        return True

    async def get_dream_team(self, user_id: Any) -> Optional[Dict[str, Any]]:
        """Fetches a user's active $15 Dream Team lineup."""
        return await self.fetchrow("SELECT user_id, guild_id, pg, sg, sf, pf, c, total_cost, ovr_rating, team_data, updated_at FROM dream_teams WHERE user_id = ?", str(user_id))

    async def get_top_dream_teams(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetches the top dream teams ranked by OVR rating."""
        return await self.fetch("SELECT user_id, guild_id, pg, sg, sf, pf, c, total_cost, ovr_rating, updated_at FROM dream_teams ORDER BY ovr_rating DESC, updated_at ASC LIMIT ?", int(limit))

    # ── Team Battle Career Stats & Leaderboard ──────────────────────────────
    async def get_team_battle_stats(self, user_id: Any) -> Dict[str, Any]:
        """Fetches a member's career NBA team battle record, streak, achievements, and coaching DNA."""
        row = await self.fetchrow("SELECT user_id, wins, losses, ties, streak, best_streak, total_duels_won, total_points, daily_wins, last_daily_win_date, achievements, coaching_dna, updated_at FROM team_battle_stats WHERE user_id = ?", str(user_id))
        if row:
            try:
                achievements = json.loads(row.get("achievements") or "[]")
            except Exception:
                achievements = []
            try:
                coaching_dna = json.loads(row.get("coaching_dna") or "{}")
            except Exception:
                coaching_dna = {}
            coaching_dna.setdefault("three", 0)
            coaching_dna.setdefault("drive", 0)
            coaching_dna.setdefault("pnr", 0)
            coaching_dna.setdefault("defense", 0)
            coaching_dna.setdefault("iso", 0)
            coaching_dna.setdefault("timeouts", 0)
            coaching_dna.setdefault("total", 0)
            return {
                "wins": row.get("wins", 0),
                "losses": row.get("losses", 0),
                "ties": row.get("ties", 0),
                "streak": row.get("streak", 0),
                "best_streak": row.get("best_streak", 0),
                "total_duels_won": row.get("total_duels_won", 0),
                "total_points": row.get("total_points", 0),
                "daily_wins": row.get("daily_wins", 0),
                "last_daily_win_date": row.get("last_daily_win_date", ""),
                "achievements": achievements,
                "coaching_dna": coaching_dna
            }
        return {
            "wins": 0, "losses": 0, "ties": 0, "streak": 0, "best_streak": 0,
            "total_duels_won": 0, "total_points": 0, "daily_wins": 0, "last_daily_win_date": "", "achievements": [],
            "coaching_dna": {"three": 0, "drive": 0, "pnr": 0, "defense": 0, "iso": 0, "timeouts": 0, "total": 0}
        }

    async def update_team_battle_record(
        self,
        user_id: Any,
        won: bool,
        is_tie: bool,
        duels_won: int,
        points_scored: int,
        new_achievements: Optional[List[str]] = None,
        is_daily_win: bool = False,
        tactics_used: Optional[Dict[str, int]] = None,
        timeouts_used: int = 0
    ):
        """Updates career record, streaks, points, daily challenge wins, coaching DNA, and unlocks achievements."""
        stats = await self.get_team_battle_stats(user_id)
        wins = stats["wins"]
        losses = stats["losses"]
        ties = stats["ties"]
        streak = stats["streak"]
        best_streak = stats["best_streak"]
        total_duels = stats["total_duels_won"] + duels_won
        total_pts = stats["total_points"] + points_scored
        daily_wins = stats.get("daily_wins", 0)
        last_daily_win_date = stats.get("last_daily_win_date", "")
        achievements_set = set(stats["achievements"])
        dna = dict(stats.get("coaching_dna", {}))

        if is_daily_win:
            daily_wins += 1
            last_daily_win_date = datetime.now().strftime("%Y-%m-%d")

        if new_achievements:
            for ach in new_achievements:
                achievements_set.add(ach)

        if is_tie:
            ties += 1
            streak = 0
        elif won:
            wins += 1
            streak = streak + 1 if streak > 0 else 1
            if streak > best_streak:
                best_streak = streak
        else:
            losses += 1
            streak = streak - 1 if streak < 0 else -1

        if tactics_used:
            for k, count in tactics_used.items():
                dna[k] = dna.get(k, 0) + count
                dna["total"] = dna.get("total", 0) + count
        if timeouts_used:
            dna["timeouts"] = dna.get("timeouts", 0) + timeouts_used

        now = datetime.now().timestamp()
        ach_json = json.dumps(list(achievements_set))
        dna_json = json.dumps(dna)

        if self.is_postgres:
            query = """
                INSERT INTO team_battle_stats (user_id, wins, losses, ties, streak, best_streak, total_duels_won, total_points, daily_wins, last_daily_win_date, achievements, coaching_dna, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    wins = EXCLUDED.wins, losses = EXCLUDED.losses, ties = EXCLUDED.ties,
                    streak = EXCLUDED.streak, best_streak = EXCLUDED.best_streak,
                    total_duels_won = EXCLUDED.total_duels_won, total_points = EXCLUDED.total_points,
                    daily_wins = EXCLUDED.daily_wins, last_daily_win_date = EXCLUDED.last_daily_win_date,
                    achievements = EXCLUDED.achievements, coaching_dna = EXCLUDED.coaching_dna, updated_at = EXCLUDED.updated_at
            """
        else:
            query = "INSERT OR REPLACE INTO team_battle_stats (user_id, wins, losses, ties, streak, best_streak, total_duels_won, total_points, daily_wins, last_daily_win_date, achievements, coaching_dna, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"

        await self.execute(query, str(user_id), wins, losses, ties, streak, best_streak, total_duels, total_pts, daily_wins, last_daily_win_date, ach_json, dna_json, now)

    async def get_nba_rivalry(self, user_a_id: Any, user_b_id: Any) -> Dict[str, Any]:
        """Fetches head-to-head rivalry history and match count between two users."""
        u1, u2 = str(user_a_id), str(user_b_id)
        p_a, p_b = (u1, u2) if u1 < u2 else (u2, u1)
        row = await self.fetchrow("SELECT player_a, player_b, wins_a, wins_b, ties, last_5 FROM nba_rivalries WHERE player_a = ? AND player_b = ?", p_a, p_b)
        if not row:
            return {
                "player_a": p_a, "player_b": p_b,
                "wins_a": 0, "wins_b": 0, "ties": 0,
                "user_a_wins": 0, "user_b_wins": 0,
                "total_matches": 0, "is_rivalry": False,
                "last_5": [], "streak": 0, "leader_id": None
            }
        w_a = row.get("wins_a", 0)
        w_b = row.get("wins_b", 0)
        ties = row.get("ties", 0)
        total = w_a + w_b + ties
        try:
            last_5 = json.loads(row.get("last_5") or "[]")
        except Exception:
            last_5 = []

        user_a_wins = w_a if u1 == p_a else w_b
        user_b_wins = w_b if u1 == p_a else w_a

        streak_winner = last_5[-1] if last_5 else None
        streak_count = 0
        if streak_winner and streak_winner != "tie":
            for winner in reversed(last_5):
                if winner == streak_winner:
                    streak_count += 1
                else:
                    break

        leader_id = None
        if user_a_wins > user_b_wins:
            leader_id = u1
        elif user_b_wins > user_a_wins:
            leader_id = u2

        return {
            "player_a": p_a, "player_b": p_b,
            "wins_a": w_a, "wins_b": w_b, "ties": ties,
            "user_a_wins": user_a_wins, "user_b_wins": user_b_wins,
            "total_matches": total,
            "is_rivalry": total >= 3,
            "last_5": last_5,
            "streak": streak_count,
            "streak_winner": streak_winner,
            "leader_id": leader_id
        }

    async def update_nba_rivalry(self, winner_id: Any, loser_id: Any, is_tie: bool = False) -> Dict[str, Any]:
        """Updates head-to-head match count and last-5 results for a rivalry matchup."""
        u1, u2 = str(winner_id), str(loser_id)
        p_a, p_b = (u1, u2) if u1 < u2 else (u2, u1)
        row = await self.fetchrow("SELECT player_a, player_b, wins_a, wins_b, ties, last_5 FROM nba_rivalries WHERE player_a = ? AND player_b = ?", p_a, p_b)
        w_a = row.get("wins_a", 0) if row else 0
        w_b = row.get("wins_b", 0) if row else 0
        ties = row.get("ties", 0) if row else 0
        try:
            last_5 = json.loads(row.get("last_5") or "[]") if row else []
        except Exception:
            last_5 = []

        if is_tie:
            ties += 1
            last_5.append("tie")
        elif u1 == p_a:
            w_a += 1
            last_5.append(u1)
        else:
            w_b += 1
            last_5.append(u1)

        last_5 = last_5[-5:]
        now = datetime.now().timestamp()
        last_5_json = json.dumps(last_5)

        if self.is_postgres:
            query = """
                INSERT INTO nba_rivalries (player_a, player_b, wins_a, wins_b, ties, last_5, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (player_a, player_b) DO UPDATE SET
                    wins_a = EXCLUDED.wins_a, wins_b = EXCLUDED.wins_b, ties = EXCLUDED.ties,
                    last_5 = EXCLUDED.last_5, updated_at = EXCLUDED.updated_at
            """
        else:
            query = "INSERT OR REPLACE INTO nba_rivalries (player_a, player_b, wins_a, wins_b, ties, last_5, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"

        await self.execute(query, p_a, p_b, w_a, w_b, ties, last_5_json, now)
        return await self.get_nba_rivalry(winner_id, loser_id)

    async def get_top_battle_records(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetches top coaches ranked by wins and win streak."""
        query = """
            SELECT user_id, wins, losses, ties, streak, best_streak, total_duels_won, total_points, daily_wins, last_daily_win_date, achievements, coaching_dna
            FROM team_battle_stats
            ORDER BY wins DESC, streak DESC, total_points DESC
            LIMIT ?
        """
        return await self.fetch(query, int(limit))

    async def record_user_snipe_event(
        self,
        message_id: Any,
        guild_id: Any,
        channel_id: Any,
        channel_name: str,
        user_id: Any,
        user_name: str,
        user_display_name: str,
        user_avatar: Optional[str],
        content: str,
        attachments_json: str = "[]",
        stickers_json: str = "[]",
        message_type: str = "deleted",
        before_content: Optional[str] = None,
        after_content: Optional[str] = None,
        created_at: Optional[float] = None,
        recorded_at: Optional[float] = None
    ) -> bool:
        """Stores a deleted or edited message in persistent database for up to 30-day user snipe history."""
        now = recorded_at or datetime.now().timestamp()
        c_at = created_at or now
        query = """
            INSERT INTO user_snipe_history (
                message_id, guild_id, channel_id, channel_name, user_id,
                user_name, user_display_name, user_avatar, content,
                attachments_json, stickers_json, message_type,
                before_content, after_content, created_at, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            await self.execute(
                query,
                str(message_id),
                str(guild_id),
                str(channel_id),
                str(channel_name),
                str(user_id),
                str(user_name),
                str(user_display_name),
                str(user_avatar or ""),
                str(content or ""),
                str(attachments_json or "[]"),
                str(stickers_json or "[]"),
                str(message_type),
                str(before_content or "") if before_content is not None else None,
                str(after_content or "") if after_content is not None else None,
                float(c_at),
                float(now)
            )
            return True
        except Exception as e:
            logger.error(f"Error recording user snipe event: {e}")
            return False

    async def get_user_snipe_history(
        self,
        guild_id: Any,
        user_id: Any,
        days: int = 30,
        message_type: Optional[str] = None,
        limit: int = 150
    ) -> List[Dict[str, Any]]:
        """Fetches deleted/edited message history for a specific user in a guild within the past X days (default 30)."""
        cutoff = datetime.now().timestamp() - (max(1, min(days, 30)) * 86400)
        if message_type:
            query = """
                SELECT * FROM user_snipe_history
                WHERE guild_id = ? AND user_id = ? AND message_type = ? AND recorded_at >= ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """
            return await self.fetch(query, str(guild_id), str(user_id), str(message_type), cutoff, int(limit))
        else:
            query = """
                SELECT * FROM user_snipe_history
                WHERE guild_id = ? AND user_id = ? AND recorded_at >= ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """
            return await self.fetch(query, str(guild_id), str(user_id), cutoff, int(limit))

    async def get_user_snipe_stats(
        self,
        guild_id: Any,
        user_id: Any,
        days: int = 30
    ) -> Dict[str, Any]:
        """Calculates 30-day deleted and edited message stats for a user."""
        cutoff = datetime.now().timestamp() - (max(1, min(days, 30)) * 86400)
        query = """
            SELECT 
                COUNT(*) as total_count,
                SUM(CASE WHEN message_type = 'deleted' THEN 1 ELSE 0 END) as deleted_count,
                SUM(CASE WHEN message_type = 'edited' THEN 1 ELSE 0 END) as edited_count
            FROM user_snipe_history
            WHERE guild_id = ? AND user_id = ? AND recorded_at >= ?
        """
        row = await self.fetchrow(query, str(guild_id), str(user_id), cutoff)
        if not row:
            return {"total_count": 0, "deleted_count": 0, "edited_count": 0}
        return {
            "total_count": row.get("total_count", 0) or 0,
            "deleted_count": row.get("deleted_count", 0) or 0,
            "edited_count": row.get("edited_count", 0) or 0
        }

    async def prune_old_snipe_history(self, days: int = 30) -> int:
        """Prunes snipe history older than specified days (default 30)."""
        cutoff = datetime.now().timestamp() - (max(1, days) * 86400)
        query = "DELETE FROM user_snipe_history WHERE recorded_at < ?"
        try:
            res = await self.execute(query, cutoff)
            return res if isinstance(res, int) else 0
        except Exception as e:
            logger.error(f"Error pruning old snipe history: {e}")
            return 0

    async def clear_user_snipe_history(self, guild_id: Any, user_id: Optional[Any] = None) -> int:
        """Clears persistent snipe history for a specific user or entire guild."""
        try:
            if user_id:
                query = "DELETE FROM user_snipe_history WHERE guild_id = ? AND user_id = ?"
                res = await self.execute(query, str(guild_id), str(user_id))
            else:
                query = "DELETE FROM user_snipe_history WHERE guild_id = ?"
                res = await self.execute(query, str(guild_id))
            return res if isinstance(res, int) else 0
        except Exception as e:
            logger.error(f"Error clearing user snipe history: {e}")
            return 0

    # ── Active Scheduled Mutes & Fallback System ──────────────────────────────
    async def add_active_mute(self, guild_id: Any, user_id: Any, unmute_at: float, role_id: Optional[Any] = None, reason: str = "") -> bool:
        """Saves an active 7-day role-based mute with auto-expiration timestamp."""
        now = time.time()
        if not self.is_postgres:
            query = """
            INSERT INTO active_mutes (guild_id, user_id, role_id, unmute_at, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                role_id = excluded.role_id,
                unmute_at = excluded.unmute_at,
                reason = excluded.reason,
                created_at = excluded.created_at
            """
        else:
            query = """
            INSERT INTO active_mutes (guild_id, user_id, role_id, unmute_at, reason, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                role_id = EXCLUDED.role_id,
                unmute_at = EXCLUDED.unmute_at,
                reason = EXCLUDED.reason,
                created_at = EXCLUDED.created_at
            """
        try:
            await self.execute(query, str(guild_id), str(user_id), str(role_id) if role_id else None, unmute_at, reason, now)
            return True
        except Exception as e:
            logger.error(f"Error adding active mute: {e}")
            return False

    async def get_active_mute(self, guild_id: Any, user_id: Any) -> Optional[Dict[str, Any]]:
        """Fetches active mute entry for a member (only if not expired)."""
        now = time.time()
        if not self.is_postgres:
            query = "SELECT * FROM active_mutes WHERE guild_id = ? AND user_id = ? AND unmute_at > ?"
            return await self.fetchrow(query, str(guild_id), str(user_id), now)
        else:
            query = "SELECT * FROM active_mutes WHERE guild_id = $1 AND user_id = $2 AND unmute_at > $3"
            return await self.fetchrow(query, str(guild_id), str(user_id), now)

    async def get_due_unmutes(self, current_time: float) -> List[Dict[str, Any]]:
        """Retrieves all active mutes whose expiration timestamp has passed."""
        if not self.is_postgres:
            query = "SELECT * FROM active_mutes WHERE unmute_at <= ?"
        else:
            query = "SELECT * FROM active_mutes WHERE unmute_at <= $1"
        return await self.fetch(query, current_time)

    async def remove_active_mute(self, guild_id: Any, user_id: Any) -> bool:
        """Deletes active mute record upon unmuting or appeal acceptance."""
        if not self.is_postgres:
            query = "DELETE FROM active_mutes WHERE guild_id = ? AND user_id = ?"
        else:
            query = "DELETE FROM active_mutes WHERE guild_id = $1 AND user_id = $2"
        try:
            await self.execute(query, str(guild_id), str(user_id))
            return True
        except Exception as e:
            logger.error(f"Error removing active mute: {e}")
            return False

    # ── Appeal Tickets System ─────────────────────────────────────────────────
    async def create_appeal_ticket(self, guild_id: Any, user_id: Any, channel_id: Any, reason: str, additional_info: str = "") -> bool:
        """Records a new open appeal ticket."""
        now = time.time()
        if not self.is_postgres:
            query = """
            INSERT INTO appeal_tickets (guild_id, user_id, channel_id, status, reason, additional_info, created_at)
            VALUES (?, ?, ?, 'open', ?, ?, ?)
            """
        else:
            query = """
            INSERT INTO appeal_tickets (guild_id, user_id, channel_id, status, reason, additional_info, created_at)
            VALUES ($1, $2, $3, 'open', $4, $5, $6)
            """
        try:
            await self.execute(query, str(guild_id), str(user_id), str(channel_id), reason, additional_info, now)
            return True
        except Exception as e:
            logger.error(f"Error creating appeal ticket in DB: {e}")
            return False

    async def get_appeal_ticket_by_channel(self, channel_id: Any) -> Optional[Dict[str, Any]]:
        """Fetches appeal ticket data for a specific channel."""
        if not self.is_postgres:
            query = "SELECT * FROM appeal_tickets WHERE channel_id = ?"
        else:
            query = "SELECT * FROM appeal_tickets WHERE channel_id = $1"
        return await self.fetchrow(query, str(channel_id))

    async def get_active_appeal_by_user(self, guild_id: Any, user_id: Any) -> Optional[Dict[str, Any]]:
        """Checks if a user already has an open appeal ticket in this guild."""
        if not self.is_postgres:
            query = "SELECT * FROM appeal_tickets WHERE guild_id = ? AND user_id = ? AND status = 'open' ORDER BY created_at DESC LIMIT 1"
        else:
            query = "SELECT * FROM appeal_tickets WHERE guild_id = $1 AND user_id = $2 AND status = 'open' ORDER BY created_at DESC LIMIT 1"
        return await self.fetchrow(query, str(guild_id), str(user_id))

    async def resolve_appeal_ticket(self, channel_id: Any, status: str, resolved_by: Any) -> bool:
        """Marks an appeal ticket as accepted or denied."""
        now = time.time()
        if not self.is_postgres:
            query = "UPDATE appeal_tickets SET status = ?, resolved_at = ?, resolved_by = ? WHERE channel_id = ?"
        else:
            query = "UPDATE appeal_tickets SET status = $1, resolved_at = $2, resolved_by = $3 WHERE channel_id = $4"
        try:
            await self.execute(query, status, now, str(resolved_by), str(channel_id))
            return True
        except Exception as e:
            logger.error(f"Error resolving appeal ticket in DB: {e}")
            return False

    # ── User Memory System (Persistent AI Memory) ─────────────────────────

    async def set_user_memory(self, user_id: Any, fact_key: str, fact_value: str, guild_id: Optional[Any] = None, source: str = "manual") -> bool:
        """Stores or updates a remembered fact about a user."""
        now = time.time()
        clean_key = str(fact_key).strip().lower().replace(" ", "_")[:50]
        clean_val = str(fact_value).strip()[:500]
        if not clean_key or not clean_val:
            return False

        gid_str = str(guild_id) if guild_id else None
        if not self.is_postgres:
            query = """
            INSERT INTO user_memories (user_id, guild_id, fact_key, fact_value, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, fact_key)
            DO UPDATE SET
                fact_value = excluded.fact_value,
                guild_id = COALESCE(excluded.guild_id, user_memories.guild_id),
                source = excluded.source,
                updated_at = excluded.updated_at;
            """
        else:
            query = """
            INSERT INTO user_memories (user_id, guild_id, fact_key, fact_value, source, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT(user_id, fact_key)
            DO UPDATE SET
                fact_value = EXCLUDED.fact_value,
                guild_id = COALESCE(EXCLUDED.guild_id, user_memories.guild_id),
                source = EXCLUDED.source,
                updated_at = EXCLUDED.updated_at;
            """
        try:
            await self.execute(query, str(user_id), gid_str, clean_key, clean_val, source, now, now)
            return True
        except Exception as e:
            logger.error(f"Error setting user memory in DB: {e}")
            return False

    async def get_user_memories(self, user_id: Any, limit: int = 25) -> List[Dict[str, Any]]:
        """Retrieves all stored facts/memories for a user."""
        if not self.is_postgres:
            query = "SELECT fact_key, fact_value, source, updated_at FROM user_memories WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?"
        else:
            query = "SELECT fact_key, fact_value, source, updated_at FROM user_memories WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2"
        return await self.fetch(query, str(user_id), limit)

    async def delete_user_memory(self, user_id: Any, fact_key: str) -> bool:
        """Deletes a specific remembered fact for a user."""
        clean_key = str(fact_key).strip().lower().replace(" ", "_")
        if not self.is_postgres:
            query = "DELETE FROM user_memories WHERE user_id = ? AND fact_key = ?"
        else:
            query = "DELETE FROM user_memories WHERE user_id = $1 AND fact_key = $2"
        try:
            await self.execute(query, str(user_id), clean_key)
            return True
        except Exception as e:
            logger.error(f"Error deleting user memory in DB: {e}")
            return False

    async def clear_user_memories(self, user_id: Any) -> bool:
        """Clears all stored memories for a user."""
        if not self.is_postgres:
            query = "DELETE FROM user_memories WHERE user_id = ?"
        else:
            query = "DELETE FROM user_memories WHERE user_id = $1"
        try:
            await self.execute(query, str(user_id))
            return True
        except Exception as e:
            logger.error(f"Error clearing user memories in DB: {e}")
            return False

    async def close(self):
        """Closes all database connections."""
        if self.pg_pool:
            await self.pg_pool.close()
            logger.info("PostgreSQL pool closed.")
        if self.sqlite_conn:
            await self.sqlite_conn.close()
            logger.info("SQLite connection closed.")

db = DatabaseManager()
