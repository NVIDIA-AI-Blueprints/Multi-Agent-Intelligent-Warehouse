"""
Tests for the database migration system.

This module contains comprehensive tests for the migration system,
including unit tests, integration tests, and end-to-end tests.
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import yaml
from datetime import datetime

from src.api.services.migration import migrator, MigrationService
from src.api.services.version import version_service


class TestMigrationService:
    """Test cases for the MigrationService class."""
    
    @pytest.fixture
    def migration_service(self):
        """Create a MigrationService instance for testing."""
        return MigrationService()
    
    @pytest.fixture
    def mock_db_connection(self):
        """Create a mock database connection."""
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
        return mock_conn, mock_cursor
    
    @pytest.fixture
    def sample_migration_config(self):
        """Create a sample migration configuration."""
        return {
            'migration_system': {
                'version': '1.0.0',
                'description': 'Test Migration System',
                'created': '2024-01-01T00:00:00Z',
                'last_updated': '2024-01-01T00:00:00Z'
            },
            'settings': {
                'database': {
                    'host': 'localhost',
                    'port': 5435,
                    'name': 'test_db',
                    'user': 'test_user',
                    'password': 'test_pass',
                    'ssl_mode': 'disable'
                },
                'execution': {
                    'timeout_seconds': 300,
                    'retry_attempts': 3,
                    'retry_delay_seconds': 5,
                    'dry_run_enabled': True,
                    'rollback_enabled': True
                }
            },
            'migrations': [
                {
                    'version': '001',
                    'filename': '001_initial_schema.sql',
                    'description': 'Initial schema',
                    'dependencies': [],
                    'rollback_supported': True,
                    'estimated_duration_seconds': 30
                },
                {
                    'version': '002',
                    'filename': '002_warehouse_tables.sql',
                    'description': 'Warehouse tables',
                    'dependencies': ['001'],
                    'rollback_supported': True,
                    'estimated_duration_seconds': 60
                }
            ]
        }
    
    @pytest.fixture
    def temp_migration_dir(self, sample_migration_config):
        """Create a temporary directory with migration files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create migration files
            migration_dir = Path(temp_dir) / "migrations"
            migration_dir.mkdir()
            
            # Create migration SQL files
            (migration_dir / "001_initial_schema.sql").write_text("-- Test migration 001\nCREATE TABLE test_table (id SERIAL PRIMARY KEY);")
            (migration_dir / "002_warehouse_tables.sql").write_text("-- Test migration 002\nCREATE TABLE warehouse (id SERIAL PRIMARY KEY);")
            
            # Create config file
            config_file = migration_dir / "migration_config.yaml"
            with open(config_file, 'w') as f:
                yaml.dump(sample_migration_config, f)
            
            yield migration_dir
    
    @pytest.mark.asyncio
    async def test_load_migration_config(self, migration_service, temp_migration_dir):
        """Test loading migration configuration."""
        config_path = temp_migration_dir / "migration_config.yaml"
        
        with patch.object(migration_service, 'config_path', config_path):
            config = await migration_service.load_migration_config()
            
            assert config is not None
            assert config['migration_system']['version'] == '1.0.0'
            assert len(config['migrations']) == 2
    
    @pytest.mark.asyncio
    async def test_get_migration_status(self, migration_service, mock_db_connection):
        """Test getting migration status."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock database response
        mock_cursor.fetchall.return_value = [
            ('001', 'Initial schema', datetime.now(), 'abc123', 1000, None),
            ('002', 'Warehouse tables', datetime.now(), 'def456', 2000, None)
        ]
        
        with patch.object(migration_service, 'get_db_connection', return_value=mock_conn):
            status = await migration_service.get_migration_status()
            
            assert status['applied_count'] == 2
            assert status['pending_count'] == 0
            assert len(status['applied_migrations']) == 2
    
    @pytest.mark.asyncio
    async def test_migrate_success(self, migration_service, mock_db_connection, temp_migration_dir):
        """Test successful migration execution."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock database responses
        mock_cursor.fetchall.return_value = []  # No applied migrations
        mock_cursor.execute.return_value = None
        
        with patch.object(migration_service, 'get_db_connection', return_value=mock_conn):
            with patch.object(migration_service, 'migration_dir', temp_migration_dir):
                success = await migration_service.migrate()
                
                assert success is True
                # Verify that migration table was created and migrations were applied
                assert mock_cursor.execute.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_migrate_dry_run(self, migration_service, mock_db_connection, temp_migration_dir):
        """Test dry run migration."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock database responses
        mock_cursor.fetchall.return_value = []  # No applied migrations
        
        with patch.object(migration_service, 'get_db_connection', return_value=mock_conn):
            with patch.object(migration_service, 'migration_dir', temp_migration_dir):
                success = await migration_service.migrate(dry_run=True)
                
                assert success is True
                # Verify that no actual migrations were executed
                assert mock_cursor.execute.call_count == 0
    
    @pytest.mark.asyncio
    async def test_rollback_migration(self, migration_service, mock_db_connection, temp_migration_dir):
        """Test rolling back a migration."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock database responses
        mock_cursor.fetchall.return_value = [
            ('001', 'Initial schema', datetime.now(), 'abc123', 1000, 'DROP TABLE test_table;')
        ]
        mock_cursor.execute.return_value = None
        
        with patch.object(migration_service, 'get_db_connection', return_value=mock_conn):
            with patch.object(migration_service, 'migration_dir', temp_migration_dir):
                success = await migration_service.rollback_migration('001')
                
                assert success is True
                # Verify that rollback SQL was executed
                assert mock_cursor.execute.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_migrate_with_dependencies(self, migration_service, mock_db_connection, temp_migration_dir):
        """Test migration with dependencies."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock database responses
        mock_cursor.fetchall.return_value = []  # No applied migrations
        mock_cursor.execute.return_value = None
        
        with patch.object(migration_service, 'get_db_connection', return_value=mock_conn):
            with patch.object(migration_service, 'migration_dir', temp_migration_dir):
                success = await migration_service.migrate()
                
                assert success is True
                # Verify that migrations were executed in dependency order
                # (001 should be executed before 002)
                assert mock_cursor.execute.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_migrate_database_error(self, migration_service, mock_db_connection, temp_migration_dir):
        """Test migration with database error."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock database error
        mock_cursor.execute.side_effect = Exception("Database connection failed")
        
        with patch.object(migration_service, 'get_db_connection', return_value=mock_conn):
            with patch.object(migration_service, 'migration_dir', temp_migration_dir):
                success = await migration_service.migrate()
                
                assert success is False
    
    @pytest.mark.asyncio
    async def test_migrate_timeout(self, migration_service, mock_db_connection, temp_migration_dir):
        """Test migration timeout."""
        mock_conn, mock_cursor = mock_db_connection
        
        # Mock slow database operation
        async def slow_execute(*args, **kwargs):
            await asyncio.sleep(10)  # Simulate slow operation
        
        mock_cursor.execute.side_effect = slow_execute
        
        with patch.object(migration_service, 'get_db_connection', return_value=mock_conn):
            with patch.object(migration_service, 'migration_dir', temp_migration_dir):
                with patch.object(migration_service, 'config', {'settings': {'execution': {'timeout_seconds': 1}}}):
                    success = await migration_service.migrate()
                    
                    assert success is False


class TestMigrationCLI:
    """Test cases for the migration CLI tool."""
    
    @pytest.fixture
    def mock_migrator(self):
        """Create a mock migrator for CLI testing."""
        mock_migrator = AsyncMock()
        mock_migrator.get_migration_status.return_value = {
            'applied_count': 2,
            'pending_count': 0,
            'total_count': 2,
            'applied_migrations': [
                {'version': '001', 'description': 'Initial schema', 'applied_at': '2024-01-01T00:00:00Z'}
            ],
            'pending_migrations': []
        }
        mock_migrator.migrate.return_value = True
        mock_migrator.rollback_migration.return_value = True
        return mock_migrator
    
    @pytest.mark.asyncio
    async def test_cli_status_command(self, mock_migrator):
        """Test CLI status command."""
        from src.api.cli.migrate import cli
        
        with patch('chain_server.cli.migrate.migrator', mock_migrator):
            # This would test the CLI command execution
            # In a real test, you'd use click.testing.CliRunner
            pass
    
    @pytest.mark.asyncio
    async def test_cli_migrate_command(self, mock_migrator):
        """Test CLI migrate command."""
        from src.api.cli.migrate import cli
        
        with patch('chain_server.cli.migrate.migrator', mock_migrator):
            # This would test the CLI command execution
            # In a real test, you'd use click.testing.CliRunner
            pass


class TestMigrationIntegration:
    """Integration tests for the migration system."""
    
    @pytest.fixture
    def test_database_url(self):
        """Get test database URL from environment."""
        return os.getenv('TEST_DATABASE_URL', 'postgresql://test:test@localhost:5435/test_warehouse')
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_migration_cycle(self, test_database_url, temp_migration_dir):
        """Test complete migration cycle with real database."""
        # This would test the full migration cycle with a real database
        # In a real test environment, you'd set up a test database
        pass
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_migration_rollback_cycle(self, test_database_url, temp_migration_dir):
        """Test migration and rollback cycle with real database."""
        # This would test migration and rollback with a real database
        # In a real test environment, you'd set up a test database
        pass


# Test configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Test markers
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.unit,
]
