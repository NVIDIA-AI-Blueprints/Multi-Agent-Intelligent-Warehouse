"""
Task-specific SQL queries for warehouse operations.

Provides parameterized queries for task management including
workforce scheduling, task assignment, and operational KPIs.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from .sql_retriever import SQLRetriever

@dataclass
class Task:
    """Data class for warehouse tasks."""
    id: int
    kind: str
    status: str
    assignee: Optional[str]
    payload: Dict[str, Any]
    created_at: str
    updated_at: str

class TaskQueries:
    """Task-specific query operations."""
    
    def __init__(self, sql_retriever: SQLRetriever):
        self.sql_retriever = sql_retriever
    
    async def get_tasks_by_status(self, status: str, limit: int = 100) -> List[Task]:
        """Get tasks by status."""
        query = """
        SELECT id, kind, status, assignee, payload, created_at, updated_at
        FROM tasks 
        WHERE status = $1
        ORDER BY created_at DESC
        LIMIT $2
        """
        
        try:
            results = await self.sql_retriever.execute_query(query, (status, limit))
            return [
                Task(
                    id=row['id'],
                    kind=row['kind'],
                    status=row['status'],
                    assignee=row['assignee'],
                    payload=row['payload'],
                    created_at=str(row['created_at']),
                    updated_at=str(row['updated_at'])
                )
                for row in results
            ]
        except Exception as e:
            raise Exception(f"Failed to get tasks by status {status}: {e}")
    
    async def get_tasks_by_assignee(self, assignee: str, limit: int = 100) -> List[Task]:
        """Get tasks assigned to a specific person."""
        query = """
        SELECT id, kind, status, assignee, payload, created_at, updated_at
        FROM tasks 
        WHERE assignee = $1
        ORDER BY created_at DESC
        LIMIT $2
        """
        
        try:
            results = await self.sql_retriever.execute_query(query, (assignee, limit))
            return [
                Task(
                    id=row['id'],
                    kind=row['kind'],
                    status=row['status'],
                    assignee=row['assignee'],
                    payload=row['payload'],
                    created_at=str(row['created_at']),
                    updated_at=str(row['updated_at'])
                )
                for row in results
            ]
        except Exception as e:
            raise Exception(f"Failed to get tasks for assignee {assignee}: {e}")
    
    async def get_task_summary(self) -> Dict[str, Any]:
        """Get task summary statistics."""
        queries = {
            'total_tasks': "SELECT COUNT(*) FROM tasks",
            'pending_tasks': "SELECT COUNT(*) FROM tasks WHERE status = 'pending'",
            'in_progress_tasks': "SELECT COUNT(*) FROM tasks WHERE status = 'in_progress'",
            'completed_tasks': "SELECT COUNT(*) FROM tasks WHERE status = 'completed'",
            'tasks_by_kind': "SELECT kind, COUNT(*) as count FROM tasks GROUP BY kind ORDER BY count DESC"
        }
        
        try:
            results = {}
            for key, query in queries.items():
                if key == 'tasks_by_kind':
                    results[key] = await self.sql_retriever.execute_query(query)
                else:
                    results[key] = await self.sql_retriever.execute_scalar(query)
            
            return results
        except Exception as e:
            raise Exception(f"Failed to get task summary: {e}")
