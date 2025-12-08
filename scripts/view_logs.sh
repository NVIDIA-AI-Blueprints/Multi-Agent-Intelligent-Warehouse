#!/bin/bash
# View backend logs in real-time with filtering options
# Usage: ./scripts/view_logs.sh [filter]
#   filter options: llm, error, chat, all (default: all)

set -euo pipefail

LOG_FILE="/tmp/backend.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if log file exists
if [ ! -f "$LOG_FILE" ]; then
    echo -e "${RED}Error: Log file not found: $LOG_FILE${NC}"
    echo -e "${YELLOW}The backend may not be running. Start it with: ./restart_backend.sh${NC}"
    exit 1
fi

# Parse filter argument
FILTER="${1:-all}"

case "$FILTER" in
    llm|LLM)
        echo -e "${GREEN}Viewing LLM/NIM related logs...${NC}"
        echo -e "${BLUE}Press Ctrl+C to stop${NC}"
        echo ""
        tail -f "$LOG_FILE" | grep --color=always -E "LLM|NIM|nim_client|generate_response|generate_embeddings|NVIDIA_API_KEY|api.brev.dev|integrate.api.nvidia.com"
        ;;
    error|ERROR|err)
        echo -e "${RED}Viewing errors and warnings...${NC}"
        echo -e "${BLUE}Press Ctrl+C to stop${NC}"
        echo ""
        tail -f "$LOG_FILE" | grep --color=always -E "ERROR|WARNING|Exception|Traceback|Failed|failed|Error|error"
        ;;
    chat|CHAT)
        echo -e "${GREEN}Viewing chat/API request logs...${NC}"
        echo -e "${BLUE}Press Ctrl+C to stop${NC}"
        echo ""
        tail -f "$LOG_FILE" | grep --color=always -E "chat|/api/v1/chat|POST|GET|message|session_id|route|intent"
        ;;
    all|ALL|"")
        echo -e "${GREEN}Viewing all logs...${NC}"
        echo -e "${BLUE}Press Ctrl+C to stop${NC}"
        echo ""
        tail -f "$LOG_FILE"
        ;;
    help|--help|-h)
        echo "Usage: $0 [filter]"
        echo ""
        echo "Filters:"
        echo "  llm     - Show LLM/NIM related logs"
        echo "  error   - Show errors and warnings only"
        echo "  chat    - Show chat/API request logs"
        echo "  all     - Show all logs (default)"
        echo "  help    - Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0           # View all logs"
        echo "  $0 llm       # View LLM logs only"
        echo "  $0 error     # View errors only"
        echo "  $0 chat      # View chat logs only"
        exit 0
        ;;
    *)
        echo -e "${RED}Unknown filter: $FILTER${NC}"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac

