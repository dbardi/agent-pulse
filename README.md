# Pulse — Agent Heartbeat Framework

A lightweight, event-driven monitoring framework for AI agents. Runs cheap local checks on a schedule and only invokes an LLM when something actually needs attention.

## Philosophy

**Zero-LLM Sensing.** Most of the time, nothing is on fire. Pulse runs dumb sensors — file checks, disk usage, process status — using plain Python. No tokens burned. No API calls. If everything is fine, the runner updates state and exits silently.

**Targeted Invocation.** When a sensor detects something, Pulse wakes the agent with exact context — not a generic "check everything." The agent gets told precisely what changed and can act immediately.

**Modular by Default.** Each sensor is an independent script with a standardized interface. Add a new monitor by dropping a `.py` file and adding an entry to `checks.json`. No changes to the runner.

## Architecture

```
Pulse (Runner)
  │
  ├── checks.json        ← What to check
  ├── state.json         ← What changed (auto-managed)
  │
  └── checks/
        ├── check_mail.py      ← Inbox sensor
        ├── check_sys.py       ← System health sensor
        └── template_check.py  ← Copy this to build new sensors
```

**Runner + Scripts pattern:**

1. `pulse.py` reads `checks.json` and runs each sensor script
2. Each script performs local, zero-cost checks against its params and previous state
3. Scripts return a Three-Field Contract (see below)
4. If nothing triggers — silent exit, zero LLM cost
5. If something triggers — runner batches all triggered contexts into a single agent invocation

## The Three-Field Contract

Every check script returns exactly three fields on stdout:

```json
{
  "triggered": true,
  "context": "2 new emails from alice@example.com and bob@example.com",
  "state_update": {
    "inbox": {
      "20260421_095537_alice": "seen",
      "20260421_100012_bob": "seen"
    }
  }
}
```

| Field | Type | Purpose |
|-------|------|---------|
| `triggered` | `bool` | Does the agent need to wake up? |
| `context` | `string` | What to tell the agent |
| `state_update` | `object` | Data to merge into `state.json` for next run |

**Why this contract:**
- Scripts are stateless — the runner passes state in, the script returns state out
- Scripts are testable in isolation — pipe in `--state '{}'` and check stdout
- Scripts can't clobber each other — the runner namespaces each update under the check ID
- A failure in one script can't crash the runner — malformed output is caught and logged

## Usage

### Install

```bash
cd ~/.hermes/heartbeat
bash install.sh
```

This creates the virtual environment, installs dependencies, and sets up a cron job (every 5 minutes by default).

### Configure

Edit `checks.json` to enable or disable sensors:

```json
{
  "checks": [
    {
      "id": "inbox_monitor",
      "script": "check_mail.py",
      "params": {
        "path": "~/mail/inbox"
      }
    },
    {
      "id": "system_health",
      "script": "check_sys.py",
      "params": {
        "disk_limit": 90,
        "processes": ["nginx", "postgresql"]
      }
    }
  ]
}
```

### Run manually

```bash
# With the venv active
python3 pulse.py

# Or directly
~/.hermes/heartbeat/venv/bin/python3 pulse.py
```

### Add a new sensor

```bash
cp checks/template_check.py checks/check_mine.py
# Edit check_mine.py with your logic
# Add entry to checks.json
```

## Safety Rails

| Feature | Default | Purpose |
|---------|---------|---------|
| Script timeout | 10 seconds | One bad sensor can't block the runner |
| Cooldown timer | 15 minutes | Prevents rapid-fire agent invocations |
| Daily invocation cap | 20 | Hard limit on LLM sessions per day |
| Namespaced state | Automatic | Scripts can't overwrite each other's data |
| Dead letter handling | Retry once, then alert | Failed items get logged and reported via Telegram |

## Requirements

- Python 3.11+
- An AI agent that accepts CLI invocation (e.g., `hermes chat -q "..."`)
- Cron or systemd timer for scheduling

## License

MIT
