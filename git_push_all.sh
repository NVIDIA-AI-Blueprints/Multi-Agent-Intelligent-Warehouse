#!/bin/bash
# Git add, commit, and push to all remotes

cd /home/tarik-devh/Projects/warehouseassistant/warehouse-operational-assistant

echo "📋 Checking git status..."
git status --short

echo ""
echo "➕ Adding all changes..."
git add -A

echo ""
echo "💾 Committing changes..."
git commit -m "feat: implement equipment dispatch with automatic forklift selection

- Register equipment adapter for tool discovery
- Add equipment category search for dispatch queries
- Implement automatic asset_id extraction from equipment status
- Add tool dependency handling for equipment dispatch (create_task + get_equipment_status -> assign_equipment)
- Enhance logging for equipment tool discovery and execution
- Fix tool execution plan to include equipment tools for dispatch queries
- Add parameter extraction for equipment dispatch tools (asset_id, equipment_type, zone, task_id)"

echo ""
BRANCH=$(git branch --show-current)
echo "🌿 Current branch: $BRANCH"

echo ""
echo "📤 Pushing to all remotes..."
for remote in $(git remote); do
    echo "  Pushing to $remote..."
    git push $remote $BRANCH
done

echo ""
echo "✅ Done!"

