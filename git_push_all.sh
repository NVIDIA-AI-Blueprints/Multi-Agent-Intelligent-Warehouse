#!/bin/bash
# Git add, commit, and push to both remotes (origin and nvidia)
# Usage: ./git_push_all.sh [commit_message]
#        ./git_push_all.sh  (will prompt for commit message)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the commit message
if [ $# -eq 0 ]; then
    echo -e "${YELLOW}Enter commit message:${NC}"
    read -r COMMIT_MESSAGE
    if [ -z "$COMMIT_MESSAGE" ]; then
        echo -e "${RED}Error: Commit message cannot be empty${NC}"
        exit 1
    fi
else
    COMMIT_MESSAGE="$*"
fi

# Check if there are any changes to commit
if [ -z "$(git status --porcelain)" ]; then
    echo -e "${YELLOW}No changes to commit${NC}"
    exit 0
fi

echo -e "${GREEN}Staging all changes...${NC}"
git add -A

echo -e "${GREEN}Committing changes...${NC}"
echo -e "${YELLOW}Commit message: ${COMMIT_MESSAGE}${NC}"
git commit -m "$COMMIT_MESSAGE"

# Get current branch
CURRENT_BRANCH=$(git branch --show-current)
echo -e "${GREEN}Current branch: ${CURRENT_BRANCH}${NC}"

# Push to origin
echo -e "${GREEN}Pushing to origin...${NC}"
if git push origin "$CURRENT_BRANCH"; then
    echo -e "${GREEN}✓ Successfully pushed to origin${NC}"
else
    echo -e "${RED}✗ Failed to push to origin${NC}"
    exit 1
fi

# Push to nvidia
echo -e "${GREEN}Pushing to nvidia...${NC}"
if git push nvidia "$CURRENT_BRANCH"; then
    echo -e "${GREEN}✓ Successfully pushed to nvidia${NC}"
else
    echo -e "${RED}✗ Failed to push to nvidia${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Successfully pushed to both remotes!${NC}"

