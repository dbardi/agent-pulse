#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "╔══════════════════════════════════════════╗"
echo "║   Agent Pulse — Heartbeat Framework      ║"
echo "║   Installation Wizard                    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Install Location ──────────────────────────────────────
echo "Where should Agent Pulse be installed?"
echo "  1) ~/.pulse (default)"
echo "  2) ~/.agent-pulse"
echo "  3) Custom path"
read -rp "Choice [1]: " LOC_CHOICE
LOC_CHOICE="${LOC_CHOICE:-1}"

case "$LOC_CHOICE" in
  1) INSTALL_DIR="$HOME/.pulse" ;;
  2) INSTALL_DIR="$HOME/.agent-pulse" ;;
  3) read -rp "Enter path: " INSTALL_DIR ;;
  *) INSTALL_DIR="$HOME/.pulse" ;;
esac

if [[ -d "$INSTALL_DIR" ]]; then
  echo ""
  echo "⚠  Directory $INSTALL_DIR already exists."
  read -rp "Overwrite? [y/N]: " OVERWRITE
  if [[ "${OVERWRITE,,}" != "y" ]]; then
    echo "Aborting."
    exit 1
  fi
fi

echo ""
echo "Installing to: $INSTALL_DIR"

# ── 2. Agent Selection ───────────────────────────────────────
echo ""
echo "Which AI agent will Pulse invoke?"
echo "  1) Hermes (hermes chat -q)"
echo "  2) Claude Code (claude -p)"
echo "  3) OpenClaw (openclaw chat)"
echo "  4) Generic (custom command)"
read -rp "Choice [1]: " AGENT_CHOICE
AGENT_CHOICE="${AGENT_CHOICE:-1}"

case "$AGENT_CHOICE" in
  1)
    AGENT_CMD="hermes chat -q"
    AGENT_NAME="hermes"
    ;;
  2)
    AGENT_CMD="claude -p"
    AGENT_NAME="claude"
    ;;
  3)
    AGENT_CMD="openclaw chat"
    AGENT_NAME="openclaw"
    ;;
  4)
    read -rp "Enter the full command to invoke your agent (use {PROMPT} as placeholder): " AGENT_CMD
    AGENT_NAME="custom"
    ;;
  *) 
    AGENT_CMD="hermes chat -q"
    AGENT_NAME="hermes"
    ;;
esac

echo "Agent command: $AGENT_CMD"

# ── 3. Check Interval ────────────────────────────────────────
echo ""
echo "How often should Pulse run? (cron expression or shorthand)"
echo "  Examples: */5 * * * * (every 5 min), */15 * * * * (every 15 min), 0 * * * * (hourly)"
read -rp "Interval [*/5 * * * *]: " INTERVAL
INTERVAL="${INTERVAL:-*/5 * * * *}"

# ── 4. Daily Cap ─────────────────────────────────────────────
echo ""
read -rp "Maximum agent invocations per day? [20]: " DAILY_CAP
DAILY_CAP="${DAILY_CAP:-20}"

# ── 5. Notification ──────────────────────────────────────────
echo ""
echo "How should Pulse notify you when something triggers?"
echo "  1) Silent (log only)"
echo "  2) Terminal output (for manual runs)"
echo "  3) Telegram (requires bot token and chat ID)"
read -rp "Choice [1]: " NOTIFY_CHOICE
NOTIFY_CHOICE="${NOTIFY_CHOICE:-1}"

TELEGRAM_TOKEN=""
TELEGRAM_CHAT=""
case "$NOTIFY_CHOICE" in
  3)
    read -rp "Telegram Bot Token: " TELEGRAM_TOKEN
    read -rp "Telegram Chat ID: " TELEGRAM_CHAT
    ;;
esac

# ── 6. Confirm ───────────────────────────────────────────────
echo ""
echo "═══ Installation Summary ═══"
echo "  Location:    $INSTALL_DIR"
echo "  Agent:       $AGENT_CMD"
echo "  Interval:    $INTERVAL"
echo "  Daily cap:   $DAILY_CAP"
echo "  Notify:      $NOTIFY_CHOICE"
[[ -n "$TELEGRAM_TOKEN" ]] && echo "  Telegram:    configured"
echo ""
read -rp "Proceed? [Y/n]: " PROCEED
if [[ "${PROCEED,,}" == "n" ]]; then
  echo "Aborting."
  exit 1
fi

# ── 7. Install ───────────────────────────────────────────────
echo ""
echo "Installing..."

# Create directory structure
mkdir -p "$INSTALL_DIR"/{checks,logs}

# Copy framework files
cp "$SCRIPT_DIR/pulse.py" "$INSTALL_DIR/pulse.py"
cp "$SCRIPT_DIR/checks/check_mail.py" "$INSTALL_DIR/checks/" 2>/dev/null || true
cp "$SCRIPT_DIR/checks/check_sys.py" "$INSTALL_DIR/checks/" 2>/dev/null || true
cp "$SCRIPT_DIR/checks/template_check.py" "$INSTALL_DIR/checks/" 2>/dev/null || true

# Create venv
python3 -m venv "$INSTALL_DIR/venv" 2>/dev/null || python -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip 2>/dev/null || true

# Generate checks.json
cat > "$INSTALL_DIR/checks.json" << CHECKS_EOF
{
  "checks": [
    {
      "id": "inbox_monitor",
      "script": "check_mail.py",
      "params": {
        "path": "$HOME/mail/inbox"
      }
    },
    {
      "id": "system_health",
      "script": "check_sys.py",
      "params": {
        "disk_limit": 90,
        "processes": []
      }
    }
  ]
}
CHECKS_EOF

# Generate state.json
cat > "$INSTALL_DIR/state.json" << STATE_EOF
{
  "last_run": null,
  "daily_invocations": 0,
  "daily_reset": null,
  "last_invocation_time": null
}
STATE_EOF

# Generate config.json (runner settings)
cat > "$INSTALL_DIR/config.json" << CONFIG_EOF
{
  "agent_command": "$AGENT_CMD",
  "agent_name": "$AGENT_NAME",
  "daily_cap": $DAILY_CAP,
  "cooldown_minutes": 15,
  "script_timeout": 10,
  "notification": {
    "method": $([ "$NOTIFY_CHOICE" == "3" ] && echo '"telegram"' || echo "\"silent\""),
    "telegram_token": "$TELEGRAM_TOKEN",
    "telegram_chat": "$TELEGRAM_CHAT"
  }
}
CONFIG_EOF

# Set up cron
echo ""
read -rp "Set up cron job now? [Y/n]: " CRON_CHOICE
if [[ "${CRON_CHOICE,,}" != "n" ]]; then
  CRON_CMD="cd $INSTALL_DIR && $INSTALL_DIR/venv/bin/python3 pulse.py --config checks.json --state state.json >> $INSTALL_DIR/logs/cron.log 2>&1"
  # Remove old pulse cron if exists
  (crontab -l 2>/dev/null | grep -v "pulse.py" || true) | { cat; echo "$INTERVAL $CRON_CMD"; } | crontab -
  echo "Cron job installed: $INTERVAL"
fi

# ── 8. Done ──────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ✓  Agent Pulse installed!              ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Config:  $INSTALL_DIR/config.json"
echo "  Checks:  $INSTALL_DIR/checks.json"
echo "  State:   $INSTALL_DIR/state.json"
echo "  Logs:    $INSTALL_DIR/logs/"
echo ""
echo "Quick start:"
echo "  cd $INSTALL_DIR"
echo "  ./venv/bin/python3 pulse.py --config checks.json --state state.json --dry-run"
echo ""
echo "To create a new check with your agent:"
if [[ "$AGENT_NAME" == "hermes" ]]; then
  echo "  hermes chat -q \"Create a new Agent Pulse check script at $INSTALL_DIR/checks/check_<name>.py that monitors <thing>. Use template_check.py as the base. Follow the Three-Field Contract.\""
elif [[ "$AGENT_NAME" == "openclaw" ]]; then
  echo "  openclaw chat \"Create a new Agent Pulse check script at $INSTALL_DIR/checks/check_<name>.py that monitors <thing>. Use template_check.py as the base. Follow the Three-Field Contract.\""
else
  echo "  Ask your agent to create a new check script using template_check.py as the base."
fi
echo ""
echo "Then add the check to checks.json and you're done."
