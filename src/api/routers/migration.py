"""
Migration Management API Endpoints

This module provides REST API endpoints for managing database migrations,
including status checking, migration execution, and rollback operations.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List, Optional
import logging
from src.api.services.migration import migrator
from src.api.services.version import version_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/migrations", tags=["Migrations"])


@router.get("/status")
async def get_migration_status():
    """
    Get current migration status.

    Returns:
        dict: Migration status including applied and pending migrations
    """
    try:
        status = await migrator.get_migration_status()
        return {
            "status": "ok",
            "version": version_service.get_version_display(),
            **status,
        }
    except Exception as e:
        logger.error(f"Failed to get migration status: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get migration status: {str(e)}"
        )


@router.post("/migrate")
async def run_migrations(target_version: Optional[str] = None, dry_run: bool = False):
    """
    Run database migrations.

    Args:
        target_version: Optional target version to migrate to
        dry_run: If True, show what would be done without executing

    Returns:
        dict: Migration result
    """
    try:
        success = await migrator.migrate(target_version=target_version, dry_run=dry_run)

        if success:
            return {
                "status": "ok",
                "message": (
                    "Migrations completed successfully"
                    if not dry_run
                    else "Dry run completed"
                ),
                "dry_run": dry_run,
                "target_version": target_version,
            }
        else:
            raise HTTPException(status_code=500, detail="Migration failed")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")


@router.post("/rollback/{version}")
async def rollback_migration(version: str, dry_run: bool = False):
    """
    Rollback a specific migration.

    Args:
        version: Version to rollback
        dry_run: If True, show what would be done without executing

    Returns:
        dict: Rollback result
    """
    try:
        success = await migrator.rollback_migration(version, dry_run=dry_run)

        if success:
            return {
                "status": "ok",
                "message": (
                    f"Migration {version} rolled back successfully"
                    if not dry_run
                    else f"Dry run rollback for {version}"
                ),
                "version": version,
                "dry_run": dry_run,
            }
        else:
            raise HTTPException(
                status_code=500, detail=f"Failed to rollback migration {version}"
            )

    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")


@router.get("/history")
async def get_migration_history():
    """
    Get migration history.

    Returns:
        dict: Complete migration history
    """
    try:
        status = await migrator.get_migration_status()

        return {
            "status": "ok",
            "version": version_service.get_version_display(),
            "migration_history": status.get("applied_migrations", []),
            "total_applied": status.get("applied_count", 0),
            "total_pending": status.get("pending_count", 0),
        }

    except Exception as e:
        logger.error(f"Failed to get migration history: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get migration history: {str(e)}"
        )


@router.get("/health")
async def migration_health():
    """
    Check migration system health.

    Returns:
        dict: Health status of migration system
    """
    try:
        status = await migrator.get_migration_status()

        # Check if there are any pending migrations
        pending_count = status.get("pending_count", 0)

        health_status = "healthy"
        if pending_count > 0:
            health_status = "degraded"

        return {
            "status": health_status,
            "version": version_service.get_version_display(),
            "migration_system": "operational",
            "pending_migrations": pending_count,
            "applied_migrations": status.get("applied_count", 0),
            "total_migrations": status.get("total_count", 0),
        }

    except Exception as e:
        logger.error(f"Migration health check failed: {e}")
        return {
            "status": "unhealthy",
            "version": version_service.get_version_display(),
            "migration_system": "error",
            "error": str(e),
        }
