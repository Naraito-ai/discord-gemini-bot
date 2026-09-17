import os
import logging
import asyncio
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
            # Debate Votes Table (Persistent Community Engagement)
            """
            CREATE TABLE IF NOT EXISTS debate_votes (
                message_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                option_index INTEGER NOT NULL,
                option_name TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (message_id, user_id)
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
            """
        ]
        
        for query in queries:
            await self.execute(query)
            
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

    # ── Basketball & Community Debate Voting Persistence ──────────────────────
    async def record_debate_vote(self, message_id: Any, user_id: Any, option_index: int, option_name: str) -> tuple:
        """
        Records or updates a user's debate vote.
        Returns: (is_new_vote: bool, previous_option_index: Optional[int])
        """
        existing = await self.fetchrow(
            "SELECT option_index FROM debate_votes WHERE message_id = ? AND user_id = ?",
            str(message_id), str(user_id)
        )
        if existing:
            prev_idx = existing["option_index"] if isinstance(existing, dict) and "option_index" in existing else (existing[0] if existing else None)
            if prev_idx == option_index:
                return False, prev_idx
            # Update existing vote
            await self.execute(
                "UPDATE debate_votes SET option_index = ?, option_name = ?, timestamp = CURRENT_TIMESTAMP WHERE message_id = ? AND user_id = ?",
                option_index, option_name, str(message_id), str(user_id)
            )
            return True, prev_idx
        else:
            # Insert new vote
            await self.execute(
                "INSERT INTO debate_votes (message_id, user_id, option_index, option_name) VALUES (?, ?, ?, ?)",
                str(message_id), str(user_id), option_index, option_name
            )
            return True, None

    async def get_user_debate_vote(self, message_id: Any, user_id: Any) -> Optional[int]:
        """Gets user's previously voted option index for a debate message."""
        existing = await self.fetchrow(
            "SELECT option_index FROM debate_votes WHERE message_id = ? AND user_id = ?",
            str(message_id), str(user_id)
        )
        if existing:
            return existing["option_index"] if isinstance(existing, dict) and "option_index" in existing else existing[0]
        return None

    async def get_debate_tallies(self, message_id: Any) -> Dict[int, int]:
        """Returns a dict of {option_index: total_votes} from database."""
        rows = await self.fetch(
            "SELECT option_index, COUNT(*) as count FROM debate_votes WHERE message_id = ? GROUP BY option_index",
            str(message_id)
        )
        tallies = {}
        for r in rows:
            opt = r["option_index"] if isinstance(r, dict) and "option_index" in r else r[0]
            cnt = r["count"] if isinstance(r, dict) and "count" in r else r[1]
            tallies[int(opt)] = int(cnt)
        return tallies

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

    async def close(self):
        """Closes all database connections."""
        if self.pg_pool:
            await self.pg_pool.close()
            logger.info("PostgreSQL pool closed.")
        if self.sqlite_conn:
            await self.sqlite_conn.close()
            logger.info("SQLite connection closed.")

db = DatabaseManager()
