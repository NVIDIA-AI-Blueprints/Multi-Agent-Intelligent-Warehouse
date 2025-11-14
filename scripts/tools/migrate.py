#!/usr/bin/env python3
"""
Database Migration CLI Tool

This script provides command-line interface for managing database migrations.
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.api.services.migration import migrator
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def status_command():
    """Show migration status."""
    print("🔍 Checking migration status...")
    status = await migrator.get_migration_status()
    
    if 'error' in status:
        print(f"❌ Error: {status['error']}")
        return 1
    
    print(f"\n📊 Migration Status:")
    print(f"   Applied: {status['applied_count']}")
    print(f"   Pending: {status['pending_count']}")
    print(f"   Total: {status['total_count']}")
    
    if status['applied_migrations']:
        print(f"\n✅ Applied Migrations:")
        for migration in status['applied_migrations']:
            print(f"   {migration['version']}: {migration['name']} ({migration['applied_at']})")
    
    if status['pending_migrations']:
        print(f"\n⏳ Pending Migrations:")
        for migration in status['pending_migrations']:
            print(f"   {migration['version']}: {migration['name']}")
    
    return 0

async def migrate_command(target_version=None, dry_run=False):
    """Run migrations."""
    action = "Dry run" if dry_run else "Running"
    print(f"🚀 {action} migrations...")
    
    success = await migrator.migrate(target_version=target_version, dry_run=dry_run)
    
    if success:
        print("✅ Migrations completed successfully")
        return 0
    else:
        print("❌ Migration failed")
        return 1

async def rollback_command(version, dry_run=False):
    """Rollback a migration."""
    action = "Dry run rollback" if dry_run else "Rolling back"
    print(f"🔄 {action} migration {version}...")
    
    success = await migrator.rollback_migration(version, dry_run=dry_run)
    
    if success:
        print(f"✅ Migration {version} rolled back successfully")
        return 0
    else:
        print(f"❌ Failed to rollback migration {version}")
        return 1

async def create_command(name, sql_content, rollback_sql=None):
    """Create a new migration."""
    print(f"📝 Creating migration: {name}")
    
    try:
        file_path = await migrator.create_migration(name, sql_content, rollback_sql)
        print(f"✅ Migration created: {file_path}")
        return 0
    except Exception as e:
        print(f"❌ Failed to create migration: {e}")
        return 1

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Database Migration Tool")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    subparsers.add_parser('status', help='Show migration status')
    
    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Run migrations')
    migrate_parser.add_argument('--target-version', help='Target version to migrate to')
    migrate_parser.add_argument('--dry-run', action='store_true', help='Show what would be done without executing')
    
    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Rollback a migration')
    rollback_parser.add_argument('version', help='Version to rollback')
    rollback_parser.add_argument('--dry-run', action='store_true', help='Show what would be done without executing')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new migration')
    create_parser.add_argument('name', help='Migration name')
    create_parser.add_argument('--sql-file', help='SQL file to use as migration content')
    create_parser.add_argument('--rollback-file', help='SQL file to use as rollback content')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Set up environment
    os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5435/warehouse_ops')
    
    try:
        if args.command == 'status':
            return asyncio.run(status_command())
        elif args.command == 'migrate':
            return asyncio.run(migrate_command(args.target_version, args.dry_run))
        elif args.command == 'rollback':
            return asyncio.run(rollback_command(args.version, args.dry_run))
        elif args.command == 'create':
            sql_content = ""
            rollback_sql = None
            
            if args.sql_file:
                with open(args.sql_file, 'r') as f:
                    sql_content = f.read()
            else:
                print("Enter SQL content (end with Ctrl+D):")
                sql_content = sys.stdin.read()
            
            if args.rollback_file:
                with open(args.rollback_file, 'r') as f:
                    rollback_sql = f.read()
            
            return asyncio.run(create_command(args.name, sql_content, rollback_sql))
        else:
            parser.print_help()
            return 1
            
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
