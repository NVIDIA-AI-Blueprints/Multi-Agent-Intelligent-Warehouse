#!/bin/bash
# Simple backend restart script

echo "Stopping existing backend processes..."
pkill -9 -f "uvicorn.*8001" 2>/dev/null
sleep 2

echo "Starting backend..."
cd /home/tarik-devh/Projects/warehouseassistant/warehouse-operational-assistant
./scripts/start_server.sh > /tmp/backend.log 2>&1 &

echo "Waiting for backend to start..."
sleep 10

echo "Checking backend health..."
if curl -s http://localhost:8001/api/v1/health/simple > /dev/null 2>&1; then
    echo "✅ Backend restarted successfully!"
    echo "   API: http://localhost:8001"
    echo "   Docs: http://localhost:8001/docs"
else
    echo "⏳ Backend still starting... Check logs: tail -f /tmp/backend.log"
fi

