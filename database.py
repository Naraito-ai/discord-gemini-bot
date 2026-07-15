import os
import logging
import asyncio

logger = logging.getLogger("GeminiBot.Database")

class DatabaseManager:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.is_postgres = False
        self.pg_pool = None
        self.sqlite_conn = None
        self._sqlite_lock = asyncio.Lock()  # Prevent SQLite write locks
        self._config_cache = {}  # Cache for guild configurations


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
                # We disable SSL verification issues by passing ssl='require' if typical for Render/Supabase
                # but let's allow it to auto-detect. Often 'ssl' parameter is needed.
                # Render/Supabase usually require SSL.
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
        """Creates database schema."""
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
                # We dynamically convert ? to $1, $2... for postgres
                pg_query = query
                if "?" in query:
                    parts = query.split("?")
                    pg_query = "".join(f"{part}${i+1}" for i, part in enumerate(parts[:-1])) + parts[-1]
                await conn.execute(pg_query, *args)
        else:
            async with self._sqlite_lock:
                # SQLite uses ? placeholders
                sqlite_query = query.replace("$", "?")
                if "SERIAL PRIMARY KEY" in sqlite_query:
                    sqlite_query = sqlite_query.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                await self.sqlite_conn.execute(sqlite_query, args)
                await self.sqlite_conn.commit()

    async def fetch(self, query: str, *args):
        """Fetches multiple records."""
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
                sqlite_query = query.replace("$", "?")
                if "SERIAL PRIMARY KEY" in sqlite_query:
                    sqlite_query = sqlite_query.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                async with self.sqlite_conn.execute(sqlite_query, args) as cursor:
                    rows = await cursor.fetchall()
                    # Convert to list of dicts to match asyncpg interface
                    columns = [description[0] for description in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]

    async def fetchrow(self, query: str, *args):
        """Fetches a single record."""
        results = await self.fetch(query, *args)
        return results[0] if results else None

    # ── Resource Management Queries ─────────────────────────────────────────

    async def add_resource(self, guild_id: int, resource_type: str, resource_id: int):
        """Saves a created role, channel, or category to the database."""
        query = "INSERT INTO guild_resources (guild_id, resource_type, resource_id) VALUES (?, ?, ?)"
        await self.execute(query, str(guild_id), resource_type, resource_id)

    async def get_resources(self, guild_id: int, resource_type: str = None):
        """Gets all resources of a type for a guild."""
        if resource_type:
            query = "SELECT resource_id FROM guild_resources WHERE guild_id = ? AND resource_type = ?"
            rows = await self.fetch(query, str(guild_id), resource_type)
        else:
            query = "SELECT resource_type, resource_id FROM guild_resources WHERE guild_id = ?"
            rows = await self.fetch(query, str(guild_id))
        return rows

    async def clear_resources(self, guild_id: int):
        """Deletes all tracked resource records for a guild from the database."""
        query = "DELETE FROM guild_resources WHERE guild_id = ?"
        await self.execute(query, str(guild_id))

    # ── Guild Configuration Queries ──────────────────────────────────────────

    async def set_config(self, guild_id: int, key: str, value: str):
        """Sets a configuration option."""
        # Upsert logic (different for SQLite vs Postgres, but we can do a DELETE then INSERT for simplicity and cross-compatibility)
        query_del = "DELETE FROM guild_config WHERE guild_id = ? AND key = ?"
        await self.execute(query_del, str(guild_id), key)
        
        query_ins = "INSERT INTO guild_config (guild_id, key, value) VALUES (?, ?, ?)"
        await self.execute(query_ins, str(guild_id), key, str(value))
        
        # Update cache
        self._config_cache[(str(guild_id), key)] = str(value)

    def _parse_config_value(self, val):
        if val == "True": return True
        if val == "False": return False
        if val == "None" or val is None: return None
        try:
            return int(val)
        except ValueError:
            return val

    async def get_config(self, guild_id: int, key: str, default=None):
        """Gets a configuration option."""
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

    async def increment_analytics(self, guild_id: int, column_name: str, amount: int = 1):
        """Increments a specific statistic counter in the analytics table for today."""
        try:
            from datetime import datetime
            from typing import Optional
            today = datetime.now().date()
            rows = await self.fetch(
                "SELECT id FROM analytics WHERE guild_id = ? AND date = ?",
                str(guild_id),
                today
            )
            if rows:
                query = f"UPDATE analytics SET {column_name} = {column_name} + ? WHERE guild_id = ? AND date = ?"
                await self.execute(query, amount, str(guild_id), today)
            else:
                query = f"INSERT INTO analytics (guild_id, date, {column_name}) VALUES (?, ?, ?)"
                await self.execute(query, str(guild_id), today, amount)
        except Exception as e:
            logger.error(f"Failed to increment analytics: {e}")

    async def log_command(self, guild_id, user_id: int, command_name: str, status: str, latency: float):
        """Logs a slash command execution."""
        query = "INSERT INTO commands (guild_id, user_id, command_name, status, latency) VALUES (?, ?, ?, ?, ?)"
        await self.execute(query, str(guild_id) if guild_id else None, str(user_id), command_name, status, latency)
        if guild_id:
            await self.increment_analytics(guild_id, "commands_count")

    async def log_ai_usage(self, guild_id, user_id: int, prompt: str, response: str, model: str, tokens_used: int, latency: float):
        """Logs an AI query usage entry."""
        query = "INSERT INTO ai_usage (guild_id, user_id, prompt, response, model, tokens_used, latency) VALUES (?, ?, ?, ?, ?, ?, ?)"
        await self.execute(query, str(guild_id) if guild_id else None, str(user_id), prompt, response, model, tokens_used, latency)

    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str):
        """Logs a member warning."""
        query = "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), str(moderator_id), reason)
        await self.increment_analytics(guild_id, "warnings_count")

    async def add_timeout(self, guild_id: int, user_id: int, moderator_id: int, duration_seconds: int, reason: str):
        """Logs a member timeout."""
        query = "INSERT INTO timeouts (guild_id, user_id, moderator_id, duration_seconds, reason) VALUES (?, ?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), str(moderator_id), duration_seconds, reason)
        await self.increment_analytics(guild_id, "mutes_count")

    async def add_ban(self, guild_id: int, user_id: int, moderator_id: int, reason: str):
        """Logs a member ban."""
        query = "INSERT INTO bans (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), str(moderator_id), reason)
        await self.increment_analytics(guild_id, "bans_count")

    async def log_audit(self, guild_id: int, user_id: int, action: str, details: str = None):
        """Logs a dashboard or moderator action."""
        query = "INSERT INTO audit_logs (guild_id, user_id, action, details) VALUES (?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), action, details)

    async def close(self):
        """Closes all database connections."""
        if self.pg_pool:
            await self.pg_pool.close()
            logger.info("PostgreSQL pool closed.")
        if self.sqlite_conn:
            await self.sqlite_conn.close()
            logger.info("SQLite connection closed.")

db = DatabaseManager()
