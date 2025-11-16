# Database Migration System

## Overview

The Warehouse Operational Assistant implements a comprehensive database migration system that provides version control, dependency management, and rollback capabilities for database schema changes. This system ensures consistent database state across different environments and enables safe, automated database updates.

## Architecture

### Components

1. **Migration Service** (`src/api/services/migration.py`)
   - Core migration logic and database operations
   - Dependency resolution and execution order
   - Rollback management and validation

2. **Migration CLI** (`src/api/cli/migrate.py`)
   - Command-line interface for migration operations
   - Status checking and health monitoring
   - Dry-run and rollback capabilities

3. **Migration API** (`src/api/routers/migration.py`)
   - REST API endpoints for migration management
   - Integration with monitoring and health checks
   - Programmatic migration control

4. **Migration Files** (`data/postgres/migrations/`)
   - SQL migration scripts with versioning
   - Configuration and metadata files
   - Rollback scripts and documentation

### Database Schema

The migration system uses several tables to track and manage migrations:

```sql
-- Migration tracking table
CREATE TABLE schema_migrations (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    checksum VARCHAR(64) NOT NULL,
    execution_time_ms INTEGER,
    rollback_sql TEXT
);

-- Application metadata table
CREATE TABLE application_metadata (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) NOT NULL UNIQUE,
    value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Audit log table
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    record_id VARCHAR(100) NOT NULL,
    operation VARCHAR(20) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by VARCHAR(100),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address INET,
    user_agent TEXT
);
```

## Migration File Structure

### SQL Migration Files

Migration files follow a specific naming convention and structure:

```
data/postgres/migrations/
├── 001_initial_schema.sql
├── 002_warehouse_tables.sql
├── 003_timescale_hypertables.sql
└── migration_config.yaml
```

**Naming Convention:**
- `{version}_{description}.sql`
- Version: 3-digit zero-padded number (001, 002, 003, ...)
- Description: Snake_case description of the migration

**File Structure:**
```sql
-- Migration: 001_initial_schema.sql
-- Description: Initial database schema setup
-- Version: 0.1.0
-- Created: 2024-01-01T00:00:00Z

-- Migration SQL here
CREATE TABLE example_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
```

### Configuration File

The `migration_config.yaml` file contains migration metadata and settings:

```yaml
migration_system:
  version: "1.0.0"
  description: "Warehouse Operational Assistant Database Migration System"
  created: "2024-01-01T00:00:00Z"
  last_updated: "2024-01-01T00:00:00Z"

migrations:
  - version: "001"
    filename: "001_initial_schema.sql"
    description: "Initial database schema setup"
    dependencies: []
    rollback_supported: true
    estimated_duration_seconds: 30
```

## Usage

### CLI Commands

The migration system provides a comprehensive CLI tool:

```bash
# Show migration status
python src/api/cli/migrate.py status

# Run pending migrations
python src/api/cli/migrate.py up

# Run migrations with dry run
python src/api/cli/migrate.py up --dry-run

# Run migrations to specific version
python src/api/cli/migrate.py up --target 002

# Rollback a migration
python src/api/cli/migrate.py down 002

# Show migration history
python src/api/cli/migrate.py history

# Check system health
python src/api/cli/migrate.py health

# Show system information
python src/api/cli/migrate.py info
```

### API Endpoints

The migration system exposes REST API endpoints:

```http
# Get migration status
GET /api/v1/migrations/status

# Run migrations
POST /api/v1/migrations/migrate
Content-Type: application/json
{
  "target_version": "002",
  "dry_run": false
}

# Rollback migration
POST /api/v1/migrations/rollback/002
Content-Type: application/json
{
  "dry_run": false
}

# Get migration history
GET /api/v1/migrations/history

# Check migration health
GET /api/v1/migrations/health
```

### Programmatic Usage

```python
from src.api.services.migration import migrator

# Get migration status
status = await migrator.get_migration_status()

# Run migrations
success = await migrator.migrate(target_version="002", dry_run=False)

# Rollback migration
success = await migrator.rollback_migration("002", dry_run=False)
```

## Features

### Version Control

- **Sequential Versioning**: Migrations are numbered sequentially (001, 002, 003, ...)
- **Version Tracking**: All applied migrations are tracked in the database
- **Version Validation**: System validates migration versions and prevents duplicates

### Dependency Management

- **Dependency Resolution**: Migrations can depend on other migrations
- **Execution Order**: System automatically resolves and executes migrations in correct order
- **Dependency Validation**: System validates that all dependencies are met before execution

### Rollback Support

- **Rollback Scripts**: Each migration can include rollback SQL
- **Rollback Validation**: System validates rollback scripts before execution
- **Selective Rollback**: Can rollback specific migrations while preserving others

### Safety Features

- **Dry Run Mode**: Test migrations without executing them
- **Transaction Safety**: All migrations run within database transactions
- **Error Handling**: Comprehensive error handling and rollback on failure
- **Timeout Protection**: Configurable timeouts prevent hanging migrations

### Monitoring and Logging

- **Execution Timing**: Track migration execution time
- **Audit Logging**: All migration operations are logged
- **Health Checks**: System health monitoring and status reporting
- **Metrics Collection**: Performance metrics and success rates

## Configuration

### Environment Variables

```bash
# Database connection
DB_HOST=localhost
DB_PORT=5435
DB_NAME=warehouse_assistant
DB_USER=warehouse_user
DB_PASSWORD=warehouse_pass
DB_SSL_MODE=prefer

# Migration settings
MIGRATION_LOG_LEVEL=INFO
BACKUP_LOCATION=./backups
```

### Migration Settings

```yaml
settings:
  execution:
    timeout_seconds: 300
    retry_attempts: 3
    retry_delay_seconds: 5
    dry_run_enabled: true
    rollback_enabled: true
  
  backup:
    enabled: true
    backup_before_migration: true
    backup_retention_days: 30
```

## Best Practices

### Writing Migrations

1. **Idempotent Operations**: Ensure migrations can be run multiple times safely
2. **Backward Compatibility**: Maintain backward compatibility when possible
3. **Rollback Scripts**: Always include rollback scripts for DDL operations
4. **Testing**: Test migrations in development before production
5. **Documentation**: Document complex migrations and their purpose

### Migration Management

1. **Sequential Development**: Develop migrations sequentially to avoid conflicts
2. **Dependency Management**: Keep dependencies simple and well-documented
3. **Version Control**: Keep migration files in version control
4. **Backup Strategy**: Always backup before major migrations
5. **Monitoring**: Monitor migration execution and performance

### Production Deployment

1. **Staging Testing**: Test all migrations in staging environment
2. **Rollback Plan**: Have a rollback plan for critical migrations
3. **Maintenance Windows**: Schedule major migrations during maintenance windows
4. **Monitoring**: Monitor system health during and after migrations
5. **Documentation**: Document all production migration activities

## Troubleshooting

### Common Issues

1. **Migration Failures**: Check logs for specific error messages
2. **Dependency Issues**: Ensure all dependencies are met
3. **Timeout Issues**: Increase timeout settings for large migrations
4. **Rollback Failures**: Check rollback scripts for syntax errors
5. **Database Connection**: Verify database connectivity and permissions

### Debugging

1. **Enable Debug Logging**: Set `MIGRATION_LOG_LEVEL=DEBUG`
2. **Dry Run Mode**: Use dry run mode to test migrations
3. **Check Status**: Use status command to verify current state
4. **Review Logs**: Check application and database logs
5. **Health Checks**: Use health check endpoints to verify system status

## Security Considerations

1. **Access Control**: Restrict migration API access to authorized users
2. **Audit Logging**: Log all migration operations for security auditing
3. **Backup Security**: Secure backup files and access
4. **SQL Injection**: Use parameterized queries and validate inputs
5. **Environment Isolation**: Use separate migration systems for different environments

## Performance Considerations

1. **Migration Size**: Keep individual migrations small and focused
2. **Index Management**: Create indexes after data migration for better performance
3. **Batch Operations**: Use batch operations for large data migrations
4. **Monitoring**: Monitor migration performance and optimize as needed
5. **Resource Usage**: Consider database resource usage during migrations

## Future Enhancements

1. **Parallel Migrations**: Support for parallel migration execution
2. **Migration Templates**: Pre-built templates for common migration patterns
3. **Visual Interface**: Web-based migration management interface
4. **Advanced Rollback**: More sophisticated rollback strategies
5. **Performance Analytics**: Advanced performance monitoring and analytics
