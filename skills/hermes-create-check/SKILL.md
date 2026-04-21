---
name: agent-pulse-create-check
version: 1.1.0
description: Create new check scripts for the Agent Pulse heartbeat framework using the Three-Field Contract. Use when asked to create a new sensor, check, or monitor for Agent Pulse.
metadata:
  hermes:
    tags: [agent-pulse, heartbeat, monitoring, check-creation, sensors]
    related_skills: [pulse-heartbeat-framework]
---

# Agent Pulse — Create New Check

Create Python check scripts for the Agent Pulse heartbeat framework following the Three-Field Contract.

## Trigger

User says something like:
- "Create a pulse check that monitors X"
- "Add a new sensor for X"
- "Write a check script for X"
- "I want pulse to watch X"

## What You Need from the User

1. What to monitor (file changes, API health, process status, log patterns, etc.)
2. What should trigger an alert (threshold, presence/absence, change detection)
3. Any params that should be configurable via checks.json

## Three-Field Contract

Every check script must return exactly this JSON to stdout:

```json
{
  "triggered": true,
  "context": "Human-readable description of what was detected",
  "state_update": { "key": "value" }
}
```

On error:
```json
{
  "triggered": false,
  "context": "",
  "state_update": {},
  "error": "error message"
}
```

| Field | Type | Purpose |
|-------|------|---------|
| `triggered` | `bool` | Does the agent need to wake up? |
| `context` | `string` | What to tell the agent (be specific — paths, values, counts) |
| `state_update` | `object` | Data to merge into state.json for next run (flat, runner namespaces it) |

## Script Template

```python
#!/usr/bin/env python3
"""
Check: <NAME>

<DESCRIPTION>

Params (from checks.json):
  - param_name: description

State (from state.json, namespaced under this check's ID):
  - tracked items or previous state
"""

import argparse
import json
import sys


def parse_args():
    parser = argparse.ArgumentParser(description="Agent Pulse check script")
    parser.add_argument("--params", required=True, help="JSON string of check parameters")
    parser.add_argument("--state", required=True, help="JSON string of previous state")
    return parser.parse_args()


def detect(params: dict, state: dict) -> dict:
    """Run the check. Return a Three-Field Contract result."""
    result = {
        "triggered": False,
        "context": "",
        "state_update": {}
    }
    # YOUR LOGIC HERE
    return result


def main():
    args = parse_args()
    try:
        params = json.loads(args.params)
        state = json.loads(args.state)
    except json.JSONDecodeError as e:
        print(json.dumps({"triggered": False, "context": "", "state_update": {}, "error": str(e)}))
        sys.exit(1)

    result = detect(params, state)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

## Rules

1. **No external dependencies** — Python stdlib only (os, json, subprocess, shutil, glob, re, pathlib, datetime, etc.)
2. **Cheap checks only** — no LLM calls, no expensive API calls, no heavy network requests
3. **Stateless scripts** — read state via `--state`, return updates via `state_update`. Never read/write state.json directly
4. **10-second budget** — scripts are killed after 10 seconds. Keep it fast
5. **Namespaced state** — the runner wraps your state_update under the check ID. Return flat data only
6. **Seen vs Processed** — for items needing agent action, track as `"seen"`. The runner updates to `"processed"` after handling. Only trigger on `"seen"` items
7. **Specific context** — include file paths, values, counts, sender names in the context string

## Steps

1. Ask the user what they want to monitor if not already specified
2. Create the check script in the `checks/` directory of the Pulse installation
3. Write clean, commented Python using the template above
4. Provide the `checks.json` entry to add:

```json
{
  "id": "<descriptive_snake_case_id>",
  "script": "<filename>.py",
  "params": { ... }
}
```

5. Test: `python3 checks/<filename>.py --params '{}' --state '{}'`
6. Dry run: `python3 pulse.py --config checks.json --state state.json --dry-run`

## Examples

### File appearance detection

```python
def detect(params, state):
    watch_path = os.path.expanduser(params.get("path", "/tmp"))
    known = state.get("items", {})
    current = {e for e in os.listdir(watch_path) if os.path.isdir(os.path.join(watch_path, e))}
    new_items = current - set(known.keys())
    if new_items:
        return {
            "triggered": True,
            "context": f"{len(new_items)} new item(s) in {watch_path}: {', '.join(sorted(new_items))}",
            "state_update": {"items": {**known, **{k: "seen" for k in new_items}}}
        }
    return {"triggered": False, "context": "", "state_update": {"items": known}}
```

### Threshold monitoring

```python
def detect(params, state):
    threshold = params.get("limit", 90)
    usage = shutil.disk_usage("/")
    percent = int((usage.used / usage.total) * 100)
    if percent >= threshold:
        return {
            "triggered": True,
            "context": f"Disk / at {percent}% (threshold: {threshold}%)",
            "state_update": {"last_percent": percent}
        }
    return {"triggered": False, "context": "", "state_update": {"last_percent": percent}}
```

## Pitfalls

- Do NOT read state.json directly — always use `--state` argument
- Do NOT use `print()` for anything except the final JSON result — use stderr for debug output
- Do NOT import third-party packages — stdlib only
- The `context` string is your only communication to the agent — make it count
