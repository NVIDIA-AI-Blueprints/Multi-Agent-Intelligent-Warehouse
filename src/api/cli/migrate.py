#!/usr/bin/env python3
"""
Database Migration CLI Tool

This CLI tool provides commands for managing database migrations,
including status checking, migration execution, and rollback operations.
"""

import asyncio
import click
import yaml
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import logging
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.api.services.migration import migrator
from src.api.services.version import version_service

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load migration configuration from YAML file."""
    config_path = (
        Path(__file__).parent.parent.parent
        / "data"
        / "postgres"
        / "migrations"
        / "migration_config.yaml"
    )

    if not config_path.exists():
        logger.error(f"Migration config file not found: {config_path}")
        sys.exit(1)

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"Failed to load migration config: {e}")
        sys.exit(1)


@click.group()
@click.option("--config", "-c", help="Path to migration config file")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, config, verbose):
    """Database Migration CLI Tool for Warehouse Operational Assistant."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config()
    ctx.obj["verbose"] = verbose


@cli.command()
@click.pass_context
def status(ctx):
    """Show current migration status."""

    async def _status():
        try:
            status = await migrator.get_migration_status()

            click.echo(f"Migration Status - {version_service.get_version_display()}")
            click.echo("=" * 50)
            click.echo(f"Applied Migrations: {status.get('applied_count', 0)}")
            click.echo(f"Pending Migrations: {status.get('pending_count', 0)}")
            click.echo(f"Total Migrations: {status.get('total_count', 0)}")
            click.echo()

            if status.get("applied_migrations"):
                click.echo("Applied Migrations:")
                for migration in status["applied_migrations"]:
                    click.echo(
                        f"  ✓ {migration['version']} - {migration['description']} ({migration['applied_at']})"
                    )
                click.echo()

            if status.get("pending_migrations"):
                click.echo("Pending Migrations:")
                for migration in status["pending_migrations"]:
                    click.echo(
                        f"  ○ {migration['version']} - {migration['description']}"
                    )
                click.echo()

            if status.get("pending_count", 0) > 0:
                click.echo(
                    click.style(
                        "⚠️  There are pending migrations. Run 'migrate up' to apply them.",
                        fg="yellow",
                    )
                )
            else:
                click.echo(click.style("✅ Database is up to date.", fg="green"))

        except Exception as e:
            click.echo(click.style(f"Error getting migration status: {e}", fg="red"))
            sys.exit(1)

    asyncio.run(_status())


@cli.command()
@click.option("--target", "-t", help="Target migration version")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without executing"
)
@click.pass_context
def up(ctx, target, dry_run):
    """Run pending migrations."""

    async def _up():
        try:
            click.echo(f"Running migrations{' (dry run)' if dry_run else ''}...")
            if target:
                click.echo(f"Target version: {target}")

            success = await migrator.migrate(target_version=target, dry_run=dry_run)

            if success:
                if dry_run:
                    click.echo(
                        click.style("✅ Dry run completed successfully.", fg="green")
                    )
                else:
                    click.echo(
                        click.style("✅ Migrations completed successfully.", fg="green")
                    )
            else:
                click.echo(click.style("❌ Migration failed.", fg="red"))
                sys.exit(1)

        except Exception as e:
            click.echo(click.style(f"Error running migrations: {e}", fg="red"))
            sys.exit(1)

    asyncio.run(_up())


@cli.command()
@click.argument("version")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without executing"
)
@click.pass_context
def down(ctx, version, dry_run):
    """Rollback a specific migration."""

    async def _down():
        try:
            click.echo(
                f"Rolling back migration {version}{' (dry run)' if dry_run else ''}..."
            )

            success = await migrator.rollback_migration(version, dry_run=dry_run)

            if success:
                if dry_run:
                    click.echo(
                        click.style(
                            f"✅ Dry run rollback for {version} completed.", fg="green"
                        )
                    )
                else:
                    click.echo(
                        click.style(
                            f"✅ Migration {version} rolled back successfully.",
                            fg="green",
                        )
                    )
            else:
                click.echo(
                    click.style(f"❌ Failed to rollback migration {version}.", fg="red")
                )
                sys.exit(1)

        except Exception as e:
            click.echo(click.style(f"Error rolling back migration: {e}", fg="red"))
            sys.exit(1)

    asyncio.run(_down())


@cli.command()
@click.pass_context
def history(ctx):
    """Show migration history."""

    async def _history():
        try:
            status = await migrator.get_migration_status()

            click.echo(f"Migration History - {version_service.get_version_display()}")
            click.echo("=" * 50)

            if status.get("applied_migrations"):
                for migration in status["applied_migrations"]:
                    click.echo(f"Version: {migration['version']}")
                    click.echo(f"Description: {migration['description']}")
                    click.echo(f"Applied: {migration['applied_at']}")
                    if migration.get("execution_time_ms"):
                        click.echo(f"Duration: {migration['execution_time_ms']}ms")
                    click.echo("-" * 30)
            else:
                click.echo("No migrations found.")

        except Exception as e:
            click.echo(click.style(f"Error getting migration history: {e}", fg="red"))
            sys.exit(1)

    asyncio.run(_history())


@cli.command()
@click.pass_context
def health(ctx):
    """Check migration system health."""

    async def _health():
        try:
            status = await migrator.get_migration_status()

            click.echo(
                f"Migration System Health - {version_service.get_version_display()}"
            )
            click.echo("=" * 50)

            # Check if there are any pending migrations
            pending_count = status.get("pending_count", 0)

            if pending_count > 0:
                click.echo(click.style("⚠️  System Status: DEGRADED", fg="yellow"))
                click.echo(f"Pending Migrations: {pending_count}")
            else:
                click.echo(click.style("✅ System Status: HEALTHY", fg="green"))

            click.echo(f"Applied Migrations: {status.get('applied_count', 0)}")
            click.echo(f"Total Migrations: {status.get('total_count', 0)}")
            click.echo(f"Migration System: Operational")

        except Exception as e:
            click.echo(click.style("❌ System Status: UNHEALTHY", fg="red"))
            click.echo(f"Error: {e}")
            sys.exit(1)

    asyncio.run(_health())


@cli.command()
@click.pass_context
def info(ctx):
    """Show migration system information."""
    config = ctx.obj["config"]

    click.echo("Migration System Information")
    click.echo("=" * 50)
    click.echo(f"Version: {config['migration_system']['version']}")
    click.echo(f"Description: {config['migration_system']['description']}")
    click.echo(f"Created: {config['migration_system']['created']}")
    click.echo(f"Last Updated: {config['migration_system']['last_updated']}")
    click.echo()

    click.echo("Database Configuration:")
    db_config = config["settings"]["database"]
    click.echo(f"  Host: {db_config['host']}")
    click.echo(f"  Port: {db_config['port']}")
    click.echo(f"  Database: {db_config['name']}")
    click.echo(f"  User: {db_config['user']}")
    click.echo(f"  SSL Mode: {db_config['ssl_mode']}")
    click.echo()

    click.echo("Available Migrations:")
    for migration in config["migrations"]:
        click.echo(f"  {migration['version']} - {migration['description']}")
        click.echo(
            f"    Dependencies: {', '.join(migration['dependencies']) if migration['dependencies'] else 'None'}"
        )
        click.echo(f"    Rollback Supported: {migration['rollback_supported']}")
        click.echo(
            f"    Estimated Duration: {migration['estimated_duration_seconds']}s"
        )
        click.echo()


if __name__ == "__main__":
    cli()
