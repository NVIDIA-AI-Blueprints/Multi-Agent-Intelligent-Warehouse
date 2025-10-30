"""
SQL Retriever for Warehouse Operations

Provides structured data retrieval from PostgreSQL/TimescaleDB with
parameterized queries for security and performance.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import asyncpg
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """Database configuration for warehouse operations."""
    host: str = os.getenv("PGHOST", "localhost")
    port: int = int(os.getenv("PGPORT", "5435"))
    database: str = os.getenv("POSTGRES_DB", "warehouse")
    user: str = os.getenv("POSTGRES_USER", "warehouse")
    password: str = os.getenv("POSTGRES_PASSWORD", "warehousepw")
    min_size: int = 1
    max_size: int = 10

class SQLRetriever:
    """
    SQL-based retriever for warehouse operational data.
    
    Provides secure, parameterized access to structured data in
    PostgreSQL/TimescaleDB with connection pooling and error handling.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, config: Optional[DatabaseConfig] = None):
        if cls._instance is None:
            cls._instance = super(SQLRetriever, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        if not self._initialized:
            self.config = config or DatabaseConfig()
            self._pool: Optional[asyncpg.Pool] = None
            self._initialized = True
        
    async def initialize(self) -> None:
        """Initialize the database connection pool."""
        import asyncio
        try:
            if self._pool is None:
                # Create pool with timeout to prevent hanging
                try:
                    self._pool = await asyncio.wait_for(
                        asyncpg.create_pool(
                            host=self.config.host,
                            port=self.config.port,
                            database=self.config.database,
                            user=self.config.user,
                            password=self.config.password,
                            min_size=self.config.min_size,
                            max_size=self.config.max_size,
                            command_timeout=30,
                            server_settings={
                                'application_name': 'warehouse_assistant',
                                'jit': 'off',  # Disable JIT for better connection stability
                                'connect_timeout': '5'  # Connection timeout: 5 seconds (PostgreSQL setting)
                            }
                        ),
                        timeout=10.0  # Overall timeout: 10 seconds for pool creation
                    )
                    logger.info(f"Database connection pool initialized for {self.config.database}")
                except asyncio.TimeoutError:
                    logger.error(f"Database pool creation timed out after 10 seconds")
                    raise ConnectionError(f"Database connection timeout: Unable to connect to {self.config.host}:{self.config.port}/{self.config.database} within 10 seconds")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    async def close(self) -> None:
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("Database connection pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool with retry logic."""
        if not self._pool:
            await self.initialize()
        
        connection = None
        try:
            connection = await self._pool.acquire()
            yield connection
        finally:
            if connection:
                await self._pool.release(connection)
    
    async def execute_query(
        self, 
        query: str, 
        params: Optional[Union[tuple, dict]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a parameterized SQL query and return results.
        
        Args:
            query: SQL query string with parameter placeholders
            params: Query parameters (tuple or dict)
            
        Returns:
            List of dictionaries representing query results
            
        Raises:
            Exception: If query execution fails
        """
        try:
            async with self.get_connection() as conn:
                if params:
                    if isinstance(params, tuple):
                        rows = await conn.fetch(query, *params)
                    else:
                        rows = await conn.fetch(query, **params)
                else:
                    rows = await conn.fetch(query)
                
                # Convert asyncpg.Record objects to dictionaries
                results = [dict(row) for row in rows]
                logger.debug(f"Query executed successfully, returned {len(results)} rows")
                return results
                
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise
    
    async def fetch_all(
        self, 
        query: str, 
        *params
    ) -> List[Dict[str, Any]]:
        """
        Execute a query and return all results.
        
        Args:
            query: SQL query string
            *params: Query parameters
            
        Returns:
            List of dictionaries representing query results
        """
        try:
            async with self.get_connection() as conn:
                if params:
                    rows = await conn.fetch(query, *params)
                else:
                    rows = await conn.fetch(query)
                
                results = [dict(row) for row in rows]
                logger.debug(f"Fetch all executed successfully, returned {len(results)} rows")
                return results
                
        except Exception as e:
            logger.error(f"Fetch all failed: {e}")
            raise

    async def fetch_one(
        self, 
        query: str, 
        *params
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a query and return a single row.
        
        Args:
            query: SQL query string
            *params: Query parameters
            
        Returns:
            Single row as dictionary or None if no results
        """
        try:
            async with self.get_connection() as conn:
                if params:
                    row = await conn.fetchrow(query, *params)
                else:
                    row = await conn.fetchrow(query)
                
                result = dict(row) if row else None
                logger.debug(f"Fetch one executed successfully, returned: {result is not None}")
                return result
                
        except Exception as e:
            logger.error(f"Fetch one failed: {e}")
            raise

    async def fetch_scalar(
        self, 
        query: str, 
        *params
    ) -> Any:
        """
        Execute a query and return a single scalar value.
        
        Args:
            query: SQL query string
            *params: Query parameters
            
        Returns:
            Single scalar value from the query
        """
        try:
            async with self.get_connection() as conn:
                if params:
                    result = await conn.fetchval(query, *params)
                else:
                    result = await conn.fetchval(query)
                
                logger.debug(f"Fetch scalar executed successfully, returned: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Fetch scalar failed: {e}")
            raise

    async def execute_scalar(
        self, 
        query: str, 
        params: Optional[Union[tuple, dict]] = None
    ) -> Any:
        """
        Execute a query that returns a single scalar value.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            Single scalar value from the query
        """
        try:
            async with self.get_connection() as conn:
                if params:
                    if isinstance(params, tuple):
                        result = await conn.fetchval(query, *params)
                    else:
                        result = await conn.fetchval(query, **params)
                else:
                    result = await conn.fetchval(query)
                
                logger.debug(f"Scalar query executed successfully, returned: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Scalar query execution failed: {e}")
            raise
    
    async def execute_command(
        self, 
        command: str, 
        *params
    ) -> str:
        """
        Execute a command (INSERT, UPDATE, DELETE) and return status.
        
        Args:
            command: SQL command string
            *params: Command parameters
            
        Returns:
            Command status message
        """
        try:
            async with self.get_connection() as conn:
                if params:
                    result = await conn.execute(command, *params)
                else:
                    result = await conn.execute(command)
                
                logger.info(f"Command executed successfully: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            raise
    
    async def health_check(self) -> bool:
        """
        Check database connectivity and health.
        
        Returns:
            True if database is healthy, False otherwise
        """
        try:
            if not self._pool:
                return False
            
            # Check pool status - try to reinitialize if pool is None
            if self._pool is None:
                logger.warning("Database pool is None, reinitializing...")
                await self.initialize()
            
            result = await self.execute_scalar("SELECT 1")
            return result == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            # Try to reinitialize on health check failure
            try:
                await self.initialize()
                return True
            except Exception as reinit_error:
                logger.error(f"Failed to reinitialize database pool: {reinit_error}")
                return False

# Global retriever instance with thread safety
_sql_retriever: Optional[SQLRetriever] = None
_retriever_lock = asyncio.Lock()

async def get_sql_retriever() -> SQLRetriever:
    """Get or create the global SQL retriever instance with thread safety."""
    global _sql_retriever
    async with _retriever_lock:
        if _sql_retriever is None:
            _sql_retriever = SQLRetriever()
            await _sql_retriever.initialize()
        return _sql_retriever

async def close_sql_retriever() -> None:
    """Close the global SQL retriever instance."""
    global _sql_retriever
    if _sql_retriever:
        await _sql_retriever.close()
        _sql_retriever = None
