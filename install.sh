#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Pulse Agent Heartbeat Framework — Setup ==="

# 1. Create directory structure
echo "[1/4] Creating directories..."
mkdir -p checks logs

# 2. Set up Python virtual environment
if [ ! -d "venv" ]; then
    echo "[2/4] Creating virtual environment..."
    python3 -m venv venv
else
    echo "[2/4] Virtual environment already exists, skipping."
fi

# 3. Install dependencies (add to requirements.txt as needed)
if [ -f "requirements.txt" ]; then
    echo "[3/4] Installing dependencies..."
    venv/bin/pip install -q -r requirements.txt
else
    echo "[3/4] No requirements.txt found, skipping dependency install."
fi

# 4. Initialize state.json if it doesn't exist
if [ ! -f "state.json" ]; then
    echo "[4/4] Initializing state.json..."
    echo '{}' > state.json
else
    echo "[4/4] state.json already exists, preserving."
fi

# 5. Set up cron job
CRON_MARKER="# PULSE_HEARTBEAT"
CRON_CMD="cd $SCRIPT_DIR && venv/bin/python3 pulse.py >> logs/heartbeat.log 2>&1"
EXISTING=$(crontab -l 2>/dev/null | grep -F "$CRON_MARKER" || true)

if [ -n "$EXISTING" ]; then
    echo ""
    echo "Cron job already installed. Current entry:"
    echo "  $EXISTING"
else
    echo ""
    echo "Installing cron job (every 5 minutes)..."
    (crontab -l 2>/dev/null; echo "*/5 * * * * $CRON_CMD $CRON_MARKER") | crontab -
    echo "Done. Verify with: crontab -l"
fi

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Edit checks.json to configure your sensors"
echo "  2. Copy checks/template_check.py to create custom sensors"
echo "  3. Run manually: venv/bin/python3 pulse.py"
