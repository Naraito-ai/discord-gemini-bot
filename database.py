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
            """
            CREATE TABLE IF NOT EXISTS guild_resources (
                guild_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id BIGINT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (guild_id, key)
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
                sqlite_query = query.replace("$", "?")  # Just in case
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

    async def get_config(self, guild_id: int, key: str, default=None):
        """Gets a configuration option."""
        query = "SELECT value FROM guild_config WHERE guild_id = ? AND key = ?"
        row = await self.fetchrow(query, str(guild_id), key)
        if row:
            val = row["value"]
            # Convert booleans or ints if they look like it
            if val == "True": return True
            if val == "False": return False
            try:
                return int(val)
            except ValueError:
                return val
        return default

    async def close(self):
        """Closes all database connections."""
        if self.pg_pool:
            await self.pg_pool.close()
            logger.info("PostgreSQL pool closed.")
        if self.sqlite_conn:
            await self.sqlite_conn.close()
            logger.info("SQLite connection closed.")

db = DatabaseManager()
