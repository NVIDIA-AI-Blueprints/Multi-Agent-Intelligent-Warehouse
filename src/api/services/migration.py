"""
Database Migration Service for Warehouse Operational Assistant

This service handles database schema migrations, version tracking,
and rollback capabilities for the warehouse operational system.
"""

import os
import asyncio
import asyncpg
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
import hashlib
import json

logger = logging.getLogger(__name__)


class MigrationRecord:
    """Represents a database migration record."""

    def __init__(
        self,
        version: str,
        name: str,
        checksum: str,
        applied_at: datetime,
        rollback_sql: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.version = version
        self.name = name
        self.checksum = checksum
        self.applied_at = applied_at
        self.rollback_sql = rollback_sql
        self.metadata = metadata or {}


class DatabaseMigrator:
    """
    Handles database migrations with version tracking and rollback support.

    This migrator provides:
    - Schema version tracking
    - Migration validation with checksums
    - Rollback capabilities
    - Migration history
    - Dry-run support
    """

    def __init__(
        self, database_url: str, migrations_dir: str = "data/postgres/migrations"
    ):
        self.database_url = database_url
        self.migrations_dir = Path(migrations_dir)
        self.migrations_dir.mkdir(parents=True, exist_ok=True)

    async def initialize_migration_table(self, conn: asyncpg.Connection) -> None:
        """Initialize the migrations tracking table."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            checksum VARCHAR(64) NOT NULL,
            applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            rollback_sql TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at 
        ON schema_migrations(applied_at);
        """

        await conn.execute(create_table_sql)
        logger.info("Migration tracking table initialized")

    def calculate_checksum(self, content: str) -> str:
        """Calculate SHA-256 checksum of migration content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def load_migration_files(self) -> List[Dict[str, Any]]:
        """Load migration files from the migrations directory."""
        migrations = []

        for migration_file in sorted(self.migrations_dir.glob("*.sql")):
            try:
                with open(migration_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # Extract version and name from filename (e.g., "001_initial_schema.sql")
                filename = migration_file.stem
                parts = filename.split("_", 1)

                if len(parts) != 2:
                    logger.warning(
                        f"Invalid migration filename format: {migration_file}"
                    )
                    continue

                version = parts[0]
                name = parts[1].replace("_", " ").title()

                # Look for rollback file
                rollback_file = migration_file.with_suffix(".rollback.sql")
                rollback_sql = None
                if rollback_file.exists():
                    with open(rollback_file, "r", encoding="utf-8") as f:
                        rollback_sql = f.read()

                migrations.append(
                    {
                        "version": version,
                        "name": name,
                        "file_path": migration_file,
                        "content": content,
                        "checksum": self.calculate_checksum(content),
                        "rollback_sql": rollback_sql,
                    }
                )

            except Exception as e:
                logger.error(f"Error loading migration file {migration_file}: {e}")
                continue

        return sorted(migrations, key=lambda x: x["version"])

    async def get_applied_migrations(
        self, conn: asyncpg.Connection
    ) -> List[MigrationRecord]:
        """Get list of applied migrations from the database."""
        query = """
        SELECT version, name, checksum, applied_at, rollback_sql, metadata
        FROM schema_migrations
        ORDER BY applied_at
        """

        rows = await conn.fetch(query)
        return [
            MigrationRecord(
                version=row["version"],
                name=row["name"],
                checksum=row["checksum"],
                applied_at=row["applied_at"],
                rollback_sql=row["rollback_sql"],
                metadata=row["metadata"] or {},
            )
            for row in rows
        ]

    async def apply_migration(
        self, conn: asyncpg.Connection, migration: Dict[str, Any], dry_run: bool = False
    ) -> bool:
        """Apply a single migration."""
        try:
            if dry_run:
                logger.info(
                    f"[DRY RUN] Would apply migration {migration['version']}: {migration['name']}"
                )
                return True

            # Start transaction
            async with conn.transaction():
                # Execute migration SQL
                await conn.execute(migration["content"])

                # Record migration
                insert_sql = """
                INSERT INTO schema_migrations (version, name, checksum, rollback_sql, metadata)
                VALUES ($1, $2, $3, $4, $5)
                """

                metadata = {
                    "file_path": str(migration["file_path"]),
                    "applied_by": os.getenv("USER", "unknown"),
                    "applied_from": os.getenv("HOSTNAME", "unknown"),
                }

                await conn.execute(
                    insert_sql,
                    migration["version"],
                    migration["name"],
                    migration["checksum"],
                    migration["rollback_sql"],
                    json.dumps(metadata),
                )

                logger.info(
                    f"Applied migration {migration['version']}: {migration['name']}"
                )
                return True

        except Exception as e:
            logger.error(f"Failed to apply migration {migration['version']}: {e}")
            return False

    async def rollback_migration(
        self, conn: asyncpg.Connection, version: str, dry_run: bool = False
    ) -> bool:
        """Rollback a specific migration."""
        try:
            # Get migration record
            query = "SELECT * FROM schema_migrations WHERE version = $1"
            row = await conn.fetchrow(query, version)

            if not row:
                logger.error(f"Migration {version} not found")
                return False

            if not row["rollback_sql"]:
                logger.error(f"No rollback SQL available for migration {version}")
                return False

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would rollback migration {version}: {row['name']}"
                )
                return True

            # Start transaction
            async with conn.transaction():
                # Execute rollback SQL
                await conn.execute(row["rollback_sql"])

                # Remove migration record
                delete_sql = "DELETE FROM schema_migrations WHERE version = $1"
                await conn.execute(delete_sql, version)

                logger.info(f"Rolled back migration {version}: {row['name']}")
                return True

        except Exception as e:
            logger.error(f"Failed to rollback migration {version}: {e}")
            return False

    async def migrate(
        self, target_version: Optional[str] = None, dry_run: bool = False
    ) -> bool:
        """Run database migrations up to target version."""
        try:
            async with asyncpg.connect(self.database_url) as conn:
                # Initialize migration table
                await self.initialize_migration_table(conn)

                # Load migration files
                available_migrations = self.load_migration_files()
                if not available_migrations:
                    logger.info("No migration files found")
                    return True

                # Get applied migrations
                applied_migrations = await self.get_applied_migrations(conn)
                applied_versions = {m.version for m in applied_migrations}

                # Find migrations to apply
                migrations_to_apply = []
                for migration in available_migrations:
                    if migration["version"] in applied_versions:
                        # Verify checksum
                        applied_migration = next(
                            m
                            for m in applied_migrations
                            if m.version == migration["version"]
                        )
                        if applied_migration.checksum != migration["checksum"]:
                            logger.error(
                                f"Checksum mismatch for migration {migration['version']}"
                            )
                            return False
                        continue

                    if target_version and migration["version"] > target_version:
                        break

                    migrations_to_apply.append(migration)

                if not migrations_to_apply:
                    logger.info("No migrations to apply")
                    return True

                # Apply migrations
                logger.info(f"Applying {len(migrations_to_apply)} migrations...")
                for migration in migrations_to_apply:
                    success = await self.apply_migration(conn, migration, dry_run)
                    if not success:
                        return False

                logger.info("All migrations applied successfully")
                return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False

    async def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status."""
        try:
            async with asyncpg.connect(self.database_url) as conn:
                await self.initialize_migration_table(conn)

                # Get applied migrations
                applied_migrations = await self.get_applied_migrations(conn)

                # Load available migrations
                available_migrations = self.load_migration_files()

                # Find pending migrations
                applied_versions = {m.version for m in applied_migrations}
                pending_migrations = [
                    m
                    for m in available_migrations
                    if m["version"] not in applied_versions
                ]

                return {
                    "applied_count": len(applied_migrations),
                    "pending_count": len(pending_migrations),
                    "total_count": len(available_migrations),
                    "applied_migrations": [
                        {
                            "version": m.version,
                            "name": m.name,
                            "applied_at": m.applied_at.isoformat(),
                            "checksum": m.checksum,
                        }
                        for m in applied_migrations
                    ],
                    "pending_migrations": [
                        {
                            "version": m["version"],
                            "name": m["name"],
                            "file_path": str(m["file_path"]),
                        }
                        for m in pending_migrations
                    ],
                }

        except Exception as e:
            logger.error(f"Failed to get migration status: {e}")
            return {"error": str(e)}

    async def create_migration(
        self, name: str, sql_content: str, rollback_sql: Optional[str] = None
    ) -> str:
        """Create a new migration file."""
        # Get next version number
        available_migrations = self.load_migration_files()
        if available_migrations:
            last_version = int(available_migrations[-1]["version"])
            next_version = f"{last_version + 1:03d}"
        else:
            next_version = "001"

        # Create migration filename
        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        filename = f"{next_version}_{safe_name}.sql"
        file_path = self.migrations_dir / filename

        # Write migration file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(sql_content)

        # Write rollback file if provided
        if rollback_sql:
            rollback_filename = f"{next_version}_{safe_name}.rollback.sql"
            rollback_path = self.migrations_dir / rollback_filename
            with open(rollback_path, "w", encoding="utf-8") as f:
                f.write(rollback_sql)

        logger.info(f"Created migration: {file_path}")
        return str(file_path)


# Global migrator instance
migrator = DatabaseMigrator(
    database_url=os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5435/warehouse_ops"
    ),
    migrations_dir="data/postgres/migrations",
)
