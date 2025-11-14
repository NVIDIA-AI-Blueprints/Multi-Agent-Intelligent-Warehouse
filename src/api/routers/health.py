from fastapi import APIRouter, HTTPException
from datetime import datetime
import os
import logging
from src.api.services.version import version_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Health"])

# Track application start time
_start_time = datetime.utcnow()


def get_uptime() -> str:
    """Get application uptime in human-readable format."""
    uptime = datetime.utcnow() - _start_time
    total_seconds = int(uptime.total_seconds())

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m {seconds}s"
    elif hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


async def check_database_health() -> dict:
    """Check database connectivity."""
    try:
        import asyncpg
        import os
        from dotenv import load_dotenv

        load_dotenv()
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://warehouse:warehousepw@localhost:5435/warehouse",
        )

        conn = await asyncpg.connect(database_url)
        await conn.execute("SELECT 1")
        await conn.close()
        return {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "message": str(e)}


async def check_redis_health() -> dict:
    """Check Redis connectivity."""
    try:
        import redis

        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        )
        redis_client.ping()
        return {"status": "healthy", "message": "Redis connection successful"}
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return {"status": "unhealthy", "message": str(e)}


async def check_milvus_health() -> dict:
    """Check Milvus vector database connectivity."""
    try:
        from pymilvus import connections, utility

        connections.connect(
            alias="default",
            host=os.getenv("MILVUS_HOST", "localhost"),
            port=os.getenv("MILVUS_PORT", "19530"),
        )
        utility.get_server_version()
        return {"status": "healthy", "message": "Milvus connection successful"}
    except Exception as e:
        logger.warning(f"Milvus health check failed: {e}")
        return {"status": "unhealthy", "message": str(e)}


@router.get("/health/simple")
async def health_simple():
    """
    Simple health check endpoint for frontend compatibility.

    Returns:
        dict: Simple health status with ok field
    """
    try:
        # Quick database check
        import asyncpg
        import os
        from dotenv import load_dotenv

        load_dotenv()
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://warehouse:warehousepw@localhost:5435/warehouse",
        )

        conn = await asyncpg.connect(database_url)
        await conn.execute("SELECT 1")
        await conn.close()

        return {"ok": True, "status": "healthy"}
    except Exception as e:
        logger.error(f"Simple health check failed: {e}")
        return {"ok": False, "status": "unhealthy", "error": str(e)}


@router.get("/health")
async def health_check():
    """
    Comprehensive health check endpoint.

    Returns:
        dict: Health status with version and service information
    """
    try:
        # Get basic health info
        health_data = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime": get_uptime(),
            "version": version_service.get_version_display(),
            "environment": os.getenv("ENVIRONMENT", "development"),
        }

        # Check services
        services = {}
        try:
            services["database"] = await check_database_health()
        except Exception as e:
            services["database"] = {"status": "error", "message": str(e)}

        try:
            services["redis"] = await check_redis_health()
        except Exception as e:
            services["redis"] = {"status": "error", "message": str(e)}

        try:
            services["milvus"] = await check_milvus_health()
        except Exception as e:
            services["milvus"] = {"status": "error", "message": str(e)}

        health_data["services"] = services

        # Determine overall health status
        unhealthy_services = [
            name
            for name, info in services.items()
            if info.get("status") in ["unhealthy", "error"]
        ]

        if unhealthy_services:
            health_data["status"] = "degraded"
            health_data["unhealthy_services"] = unhealthy_services

        return health_data

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/version")
async def get_version():
    """
    Get application version and build information.

    Returns:
        dict: Version information
    """
    import asyncio
    try:
        # Wrap version service call with timeout to prevent hanging
        try:
            version_info = await asyncio.wait_for(
                asyncio.to_thread(version_service.get_version_info),
                timeout=2.0  # 2 second timeout for version info
            )
            return {"status": "ok", **version_info}
        except asyncio.TimeoutError:
            logger.warning("Version service call timed out, returning fallback version")
            # Return fallback version info
            return {
                "status": "ok",
                "version": "0.0.0-dev",
                "git_sha": "unknown",
                "build_time": datetime.utcnow().isoformat(),
                "environment": os.getenv("ENVIRONMENT", "development"),
            }
    except Exception as e:
        logger.error(f"Version endpoint failed: {e}")
        # Return fallback version info instead of raising error
        return {
            "status": "ok",
            "version": "0.0.0-dev",
            "git_sha": "unknown",
            "build_time": datetime.utcnow().isoformat(),
            "environment": os.getenv("ENVIRONMENT", "development"),
        }


@router.get("/version/detailed")
async def get_detailed_version():
    """
    Get detailed build information for debugging.

    Returns:
        dict: Detailed build information
    """
    import asyncio
    try:
        # Wrap version service call with timeout to prevent hanging
        try:
            detailed_info = await asyncio.wait_for(
                asyncio.to_thread(version_service.get_detailed_info),
                timeout=3.0  # 3 second timeout for detailed version info
            )
            return {"status": "ok", **detailed_info}
        except asyncio.TimeoutError:
            logger.warning("Detailed version service call timed out, returning fallback version")
            # Return fallback detailed version info
            return {
                "status": "ok",
                "version": "0.0.0-dev",
                "git_sha": "unknown",
                "git_branch": "unknown",
                "build_time": datetime.utcnow().isoformat(),
                "commit_count": 0,
                "python_version": "unknown",
                "environment": os.getenv("ENVIRONMENT", "development"),
                "docker_image": "unknown",
                "build_host": os.getenv("HOSTNAME", "unknown"),
                "build_user": os.getenv("USER", "unknown"),
            }
    except Exception as e:
        logger.error(f"Detailed version endpoint failed: {e}")
        # Return fallback instead of raising error
        return {
            "status": "ok",
            "version": "0.0.0-dev",
            "git_sha": "unknown",
            "git_branch": "unknown",
            "build_time": datetime.utcnow().isoformat(),
            "commit_count": 0,
            "python_version": "unknown",
            "environment": os.getenv("ENVIRONMENT", "development"),
            "docker_image": "unknown",
            "build_host": os.getenv("HOSTNAME", "unknown"),
            "build_user": os.getenv("USER", "unknown"),
        }


@router.get("/ready")
async def readiness_check():
    """
    Kubernetes readiness probe endpoint.

    Returns:
        dict: Readiness status
    """
    try:
        # Check critical services for readiness
        database_health = await check_database_health()

        if database_health["status"] != "healthy":
            raise HTTPException(
                status_code=503, detail="Service not ready: Database unavailable"
            )

        return {
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat(),
            "version": version_service.get_version_display(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service not ready: {str(e)}")


@router.get("/live")
async def liveness_check():
    """
    Kubernetes liveness probe endpoint.

    Returns:
        dict: Liveness status
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": get_uptime(),
        "version": version_service.get_version_display(),
    }
