"""Database migration manager for CodeMemory.

Tracks applied database schema versions using a `schema_migrations` table
and applies incremental migration scripts sequentially.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    import aiosqlite

logger = logging.getLogger(__name__)

# List of migrations as (version_id, description, sql_script)
# Version 1 is the base schema defined in schema.sql.
MIGRATIONS: list[tuple[int, str, str | None]] = [
    (1, "Initial base schema", None),
    (2, "Create schema migrations tracking table", """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at REAL NOT NULL
        );
    """),
    (3, "Add index on symbols parent_id", """
        CREATE INDEX IF NOT EXISTS idx_symbols_parent_id ON symbols(parent_id);
    """),
]


async def apply_migrations(conn: aiosqlite.Connection, schema_path: Path) -> None:
    """Check database version and apply pending migrations.

    Args:
        conn: The active aiosqlite.Connection.
        schema_path: Path to the schema.sql file.
    """
    # Check if schema_migrations table exists
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    )
    has_migrations_table = await cursor.fetchone() is not None

    current_version = 0
    if has_migrations_table:
        cursor = await conn.execute("SELECT MAX(version) FROM schema_migrations")
        row = await cursor.fetchone()
        if row and row[0] is not None:
            current_version = row[0]
    else:
        # Check if database has files table, indicating an unversioned v1 schema
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
        )
        has_files = await cursor.fetchone() is not None
        if has_files:
            # Seed version 1 in unversioned database
            logger.info("Detected existing unversioned database. Initialising schema tracking at version 1.")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL
                );
            """)
            await conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (1, time.time())
            )
            await conn.commit()
            current_version = 1

    for version, description, sql in MIGRATIONS:
        if version > current_version:
            logger.info("Applying database migration %d: %s", version, description)
            if version == 1:
                # Apply base schema.sql
                if schema_path.exists():
                    schema_sql = schema_path.read_text(encoding="utf-8")
                    await conn.executescript(schema_sql)
                else:
                    logger.error("Base schema.sql not found at %s", schema_path)
            elif sql:
                await conn.executescript(sql)

            # Ensure tracking table exists (in case it wasn't created yet)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL
                );
            """)
            await conn.execute(
                "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, time.time())
            )
            await conn.commit()
            current_version = version

    logger.debug("Database schema is up to date (version %d).", current_version)
