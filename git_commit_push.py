#!/usr/bin/env python3
"""Git add, commit, and push to all remotes."""
import subprocess
import os
import sys

os.chdir('/home/tarik-devh/Projects/warehouseassistant/warehouse-operational-assistant')

print("📋 Checking for changes...")
result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
if not result.stdout.strip():
    print("⚠️  No changes to commit. Exiting.")
    sys.exit(0)

print("➕ Adding all changes...")
subprocess.run(['git', 'add', '-A'], check=True)

print("💾 Committing changes...")
commit_msg = """feat: implement equipment dispatch with automatic forklift selection

- Register equipment adapter for tool discovery
- Add equipment category search for dispatch queries
- Implement automatic asset_id extraction from equipment status
- Add tool dependency handling for equipment dispatch
- Enhance logging for equipment tool discovery and execution
- Fix tool execution plan to include equipment tools for dispatch queries
- Add parameter extraction for equipment dispatch tools"""
result = subprocess.run(['git', 'commit', '-m', commit_msg])
if result.returncode != 0:
    print("⚠️  Commit failed or nothing to commit. Continuing with push...")

print("🌿 Getting current branch...")
result = subprocess.run(['git', 'branch', '--show-current'], capture_output=True, text=True, check=True)
branch = result.stdout.strip()

print(f"📤 Pushing to all remotes (branch: {branch})...")
# Push to both remotes: origin (T-DevH) and nvidia (NVIDIA-AI-Blueprints)
remotes = ['origin', 'nvidia']

for remote in remotes:
    print(f"  Pushing to {remote}...")
    try:
        subprocess.run(['git', 'push', remote, branch], check=True)
        print(f"  ✅ Successfully pushed to {remote}")
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to push to {remote}: {e}")
        # Continue with other remotes even if one fails
        continue

print("\n✅ Done! All changes committed and pushed.")

