from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
from src.api.routers.health import router as health_router
from src.api.routers.chat import router as chat_router
from src.api.routers.equipment import router as equipment_router
from src.api.routers.operations import router as operations_router
from src.api.routers.safety import router as safety_router
from src.api.routers.auth import router as auth_router
from src.api.routers.wms import router as wms_router
from src.api.routers.iot import router as iot_router
from src.api.routers.erp import router as erp_router
from src.api.routers.scanning import router as scanning_router
from src.api.routers.attendance import router as attendance_router
from src.api.routers.reasoning import router as reasoning_router
from src.api.routers.migration import router as migration_router
from src.api.routers.mcp import router as mcp_router
from src.api.routers.document import router as document_router
from src.api.routers.equipment_old import router as inventory_router
from src.api.routers.advanced_forecasting import router as forecasting_router
from src.api.routers.training import router as training_router
from src.api.services.monitoring.metrics import (
    record_request_metrics,
    get_metrics_response,
)

app = FastAPI(title="Warehouse Operational Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)


# Add metrics middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    record_request_metrics(request, response, duration)
    return response


app.include_router(health_router)
app.include_router(chat_router)
app.include_router(equipment_router)
app.include_router(operations_router)
app.include_router(safety_router)
app.include_router(auth_router)
app.include_router(wms_router)
app.include_router(iot_router)
app.include_router(erp_router)
app.include_router(scanning_router)
app.include_router(attendance_router)
app.include_router(reasoning_router)
app.include_router(migration_router)
app.include_router(mcp_router)
app.include_router(document_router)
app.include_router(inventory_router)
app.include_router(forecasting_router)
app.include_router(training_router)


# Add metrics endpoint
@app.get("/api/v1/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return get_metrics_response()
