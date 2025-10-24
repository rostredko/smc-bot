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

# Kill existing processes
print("🛑 Killing existing processes...")
if sys.platform == "win32":
    subprocess.run("taskkill /F /IM python.exe 2>nul", shell=True)
    subprocess.run("taskkill /F /IM node.exe 2>nul", shell=True)
else:
    subprocess.run("pkill -f 'python.*server.py' || true", shell=True)
    subprocess.run("pkill -f 'node' || true", shell=True)

time.sleep(2)

# Build frontend
print("🔨 Building frontend...")
os.chdir(WEB)
subprocess.run(["npm", "run", "build"])

# Start backend
print("🚀 Starting backend...")
if sys.platform == "win32":
    subprocess.Popen("python server.py", shell=True, cwd=str(WEB))
else:
    subprocess.Popen(["python", "server.py"], cwd=str(WEB))

time.sleep(3)
print("✅ Done! Open http://localhost:8000")
