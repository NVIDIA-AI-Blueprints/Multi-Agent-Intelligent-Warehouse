from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
from chain_server.routers.health import router as health_router
from chain_server.routers.chat import router as chat_router
from chain_server.routers.equipment import router as equipment_router
from chain_server.routers.operations import router as operations_router
from chain_server.routers.safety import router as safety_router
from chain_server.routers.auth import router as auth_router
from chain_server.routers.wms import router as wms_router
from chain_server.routers.iot import router as iot_router
from chain_server.routers.erp import router as erp_router
from chain_server.routers.scanning import router as scanning_router
from chain_server.routers.attendance import router as attendance_router
from chain_server.routers.reasoning import router as reasoning_router
from chain_server.routers.migration import router as migration_router
from chain_server.routers.mcp import router as mcp_router
from chain_server.routers.document import router as document_router
from chain_server.services.monitoring.metrics import (
    record_request_metrics,
    get_metrics_response,
)

app = FastAPI(title="Warehouse Operational Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# Add metrics endpoint
@app.get("/api/v1/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return get_metrics_response()
