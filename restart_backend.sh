#!/bin/bash
pkill -9 -f "uvicorn.*8001" 2>/dev/null
sleep 2
cd /home/tarik-devh/Projects/warehouseassistant/warehouse-operational-assistant
./scripts/start_server.sh > /tmp/backend.log 2>&1 &
echo "Backend restart initiated"

