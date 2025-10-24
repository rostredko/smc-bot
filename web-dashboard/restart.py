#!/usr/bin/env python3
"""Restart SMC Trading Engine backend and frontend"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Get directories
PROJECT = Path(__file__).parent.parent.absolute()
WEB = Path(__file__).parent.absolute()

print("=" * 60)
print("🔄 SMC Trading Engine - Restart Script")
print("=" * 60)

# Kill existing processes
print("\n🛑 Step 1: Killing existing processes...")
if sys.platform == "win32":
    print("  → Running: taskkill /F /IM python.exe")
    subprocess.run("taskkill /F /IM python.exe 2>nul", shell=True)
    print("  → Running: taskkill /F /IM node.exe")
    subprocess.run("taskkill /F /IM node.exe 2>nul", shell=True)
    print("  → Waiting 3 seconds...")
    time.sleep(3)
else:
    print("  → Running: pkill -f 'python.*server.py'")
    subprocess.run("pkill -f 'python.*server.py' || true", shell=True)
    print("  → Running: pkill -f 'node'")
    subprocess.run("pkill -f 'node' || true", shell=True)
    print("  → Waiting 2 seconds...")
    time.sleep(2)

# Build frontend
print("\n🔨 Step 2: Building frontend...")
os.chdir(WEB)
result = subprocess.run(["npm", "run", "build"], capture_output=True, text=True)
if result.returncode == 0:
    print("  ✅ Frontend built successfully")
else:
    print("  ❌ Frontend build failed!")
    print(result.stderr)
    sys.exit(1)

# Start backend
print("\n🚀 Step 3: Starting backend server...")
if sys.platform == "win32":
    # Use START command to run in separate window and detach
    print("  → Running in new window: python server.py")
    subprocess.Popen(
        'start cmd /k python server.py',
        shell=True,
        cwd=str(WEB),
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
else:
    print("  → Running: python server.py")
    subprocess.Popen(
        ["python", "server.py"],
        cwd=str(WEB),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

print("  ⏳ Waiting 4 seconds for server startup...")
time.sleep(4)

print("\n" + "=" * 60)
print("✅ Done! Open http://localhost:8000 in your browser")
print("=" * 60)
