# smc-bot

Trading system consisting of three parts:
- **backend (FastAPI + Python scripts)** — API server and trading bots
- **frontend (React)** — web dashboard
- **bot-tg (Kotlin)** — Telegram bot that forwards script output to chat

---

# Bot commands
- /start — subscribe and launch script
- /status — show bot status
- /restart — restart script

# Quick Start

## macOS / Linux

### Backend
```bash
cd mnt/data/backend

# create and activate venv
python3 -m venv .venv
source .venv/bin/activate

# install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements_web.txt   # optional

# run FastAPI server
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```
### Web-Frontend
```bash
cd mnt/data/web-dashboard
npm install
npm run dev
```
Frontend will be available at http://localhost:5173.

### TgBot-Frontend
```bash
cd mnt/data/bot-tg

# set env variable
export TELEGRAM_BOT_TOKEN=123456:ABC...your_token...

# run bot
./gradlew run
```
## Windows
### Backend
```bash
cd mnt\data\backend

# create and activate venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements_web.txt   # optional

# run FastAPI server
.\.venv\Scripts\uvicorn.exe server:app --host 0.0.0.0 --port 8000 --reload
```
### Web-Frontend
```bash
cd mnt\data\web-dashboard
npm install
npm run dev
```
Frontend will be available at http://localhost:5173.

### TgBot-Frontend
```bash
cd mnt\data\bot-tg

# set env variable
$env:TELEGRAM_BOT_TOKEN="123456:ABC...your_token..."

# run bot
.\gradlew.bat run
```