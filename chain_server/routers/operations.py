from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from inventory_retriever.structured import SQLRetriever, TaskQueries
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Operations"])

# Initialize SQL retriever
sql_retriever = SQLRetriever()


class Task(BaseModel):
    id: int
    kind: str
    status: str
    assignee: Optional[str] = None
    payload: dict
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    kind: str
    status: str = "pending"
    assignee: Optional[str] = None
    payload: dict = {}


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    assignee: Optional[str] = None
    payload: Optional[dict] = None


class WorkforceStatus(BaseModel):
    total_workers: int
    active_workers: int
    available_workers: int
    tasks_in_progress: int
    tasks_pending: int


@router.get("/operations/tasks", response_model=List[Task])
async def get_tasks():
    """Get all tasks."""
    try:
        await sql_retriever.initialize()
        query = """
            SELECT id, kind, status, assignee, payload, created_at, updated_at 
            FROM tasks 
            ORDER BY created_at DESC
        """
        results = await sql_retriever.fetch_all(query)

        tasks = []
        for row in results:
            # Parse JSON payload if it's a string
            payload = row["payload"]
            if isinstance(payload, str):
                try:
                    import json

                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            elif payload is None:
                payload = {}

            tasks.append(
                Task(
                    id=row["id"],
                    kind=row["kind"],
                    status=row["status"],
                    assignee=row["assignee"],
                    payload=payload,
                    created_at=(
                        row["created_at"].isoformat() if row["created_at"] else ""
                    ),
                    updated_at=(
                        row["updated_at"].isoformat() if row["updated_at"] else ""
                    ),
                )
            )

        return tasks
    except Exception as e:
        logger.error(f"Failed to get tasks: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tasks")


@router.get("/operations/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    """Get a specific task by ID."""
    try:
        await sql_retriever.initialize()
        task = await TaskQueries().get_task_by_id(sql_retriever, task_id)

        if not task:
            raise HTTPException(
                status_code=404, detail=f"Task with ID {task_id} not found"
            )

        return Task(
            id=task["id"],
            kind=task["kind"],
            status=task["status"],
            assignee=task["assignee"],
            payload=task["payload"] if task["payload"] else {},
            created_at=task["created_at"].isoformat() if task["created_at"] else "",
            updated_at=task["updated_at"].isoformat() if task["updated_at"] else "",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve task")


@router.post("/operations/tasks", response_model=Task)
async def create_task(task: TaskCreate):
    """Create a new task."""
    try:
        await sql_retriever.initialize()
        import json

        query = """
            INSERT INTO tasks (kind, status, assignee, payload, created_at, updated_at)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            RETURNING id, kind, status, assignee, payload, created_at, updated_at
        """
        result = await sql_retriever.fetch_one(
            query, task.kind, task.status, task.assignee, json.dumps(task.payload)
        )

        return Task(
            id=result["id"],
            kind=result["kind"],
            status=result["status"],
            assignee=result["assignee"],
            payload=result["payload"] if result["payload"] else {},
            created_at=result["created_at"].isoformat() if result["created_at"] else "",
            updated_at=result["updated_at"].isoformat() if result["updated_at"] else "",
        )
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        raise HTTPException(status_code=500, detail="Failed to create task")


@router.put("/operations/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, update: TaskUpdate):
    """Update an existing task."""
    try:
        await sql_retriever.initialize()

        # Get current task
        current_task = await task_queries.get_task_by_id(sql_retriever, task_id)
        if not current_task:
            raise HTTPException(
                status_code=404, detail=f"Task with ID {task_id} not found"
            )

        # Update fields
        status = update.status if update.status is not None else current_task["status"]
        assignee = (
            update.assignee if update.assignee is not None else current_task["assignee"]
        )
        payload = (
            update.payload if update.payload is not None else current_task["payload"]
        )

        # Ensure payload is JSON-encoded
        import json

        if isinstance(payload, dict):
            payload = json.dumps(payload)
        elif payload is None:
            payload = json.dumps({})

        query = """
            UPDATE tasks 
            SET status = $1, assignee = $2, payload = $3, updated_at = NOW()
            WHERE id = $4
            RETURNING id, kind, status, assignee, payload, created_at, updated_at
        """
        result = await sql_retriever.fetch_one(
            query, status, assignee, payload, task_id
        )

        return Task(
            id=result["id"],
            kind=result["kind"],
            status=result["status"],
            assignee=result["assignee"],
            payload=result["payload"] if result["payload"] else {},
            created_at=result["created_at"].isoformat() if result["created_at"] else "",
            updated_at=result["updated_at"].isoformat() if result["updated_at"] else "",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update task")


@router.post("/operations/tasks/{task_id}/assign")
async def assign_task(task_id: int, assignee: str):
    """Assign a task to a worker."""
    try:
        await sql_retriever.initialize()
        await TaskQueries().assign_task(sql_retriever, task_id, assignee)

        # Get updated task
        task = await TaskQueries().get_task_by_id(sql_retriever, task_id)

        # Parse JSON payload if it's a string
        payload = task["payload"]
        if isinstance(payload, str):
            try:
                import json

                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        elif payload is None:
            payload = {}

        return Task(
            id=task["id"],
            kind=task["kind"],
            status=task["status"],
            assignee=task["assignee"],
            payload=payload,
            created_at=task["created_at"].isoformat() if task["created_at"] else "",
            updated_at=task["updated_at"].isoformat() if task["updated_at"] else "",
        )
    except Exception as e:
        logger.error(f"Failed to assign task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to assign task")


@router.get("/operations/workforce", response_model=WorkforceStatus)
async def get_workforce_status():
    """Get workforce status and statistics."""
    try:
        await sql_retriever.initialize()

        # Get task statistics
        tasks_query = """
            SELECT 
                COUNT(*) as total_tasks,
                COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending
            FROM tasks
        """
        task_stats = await sql_retriever.fetch_one(tasks_query)

        # Mock workforce data (in a real system, this would come from a workforce management system)
        return WorkforceStatus(
            total_workers=25,
            active_workers=20,
            available_workers=5,
            tasks_in_progress=task_stats["in_progress"] or 0,
            tasks_pending=task_stats["pending"] or 0,
        )
    except Exception as e:
        logger.error(f"Failed to get workforce status: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve workforce status"
        )
