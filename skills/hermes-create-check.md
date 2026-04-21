# Agent Pulse — Create New Check (Hermes)

You are creating a new check script for the Agent Pulse heartbeat framework.

## What You'll Receive
The user will describe what they want to monitor. Create a check script that follows the Three-Field Contract.

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
    """
    Run the check. Return a Three-Field Contract result.
    
    - params: from checks.json for this check
    - state: previous state from state.json (namespaced under this check's ID)
    
    Return: {"triggered": bool, "context": str, "state_update": dict}
    """
    result = {
        "triggered": False,
        "context": "",
        "state_update": {}
    }
    
    # YOUR LOGIC HERE
    # 1. Perform cheap local checks (no LLM, no API calls)
    # 2. Compare against previous state to detect changes
    # 3. If something needs attention, set triggered=True and describe it in context
    # 4. Return state_update with any data needed for next run
    
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
1. **No external dependencies** — use only Python stdlib (os, json, subprocess, shutil, glob, re, pathlib, etc.)
2. **Cheap checks only** — no LLM calls, no expensive API calls, no network requests unless absolutely necessary
3. **Stateless scripts** — read state via `--state`, return updates via `state_update`. Never read/write state.json directly.
4. **10-second budget** — scripts are killed after 10 seconds. Keep it fast.
5. **Namespaced state** — the runner wraps your state_update under the check ID. Just return flat data.
6. **Seen vs Processed** — for items that need agent action, track as `"seen"` in state. The runner will update to `"processed"` after the agent handles it. Only trigger on `"seen"` items.
7. **Human-readable context** — the `context` string is passed directly to the agent. Be specific: include file paths, values, counts, sender names.

## Examples

### Detecting new files
```python
def detect(params, state):
    watch_path = os.path.expanduser(params.get("path", "/tmp"))
    known = state.get("items", {})
    
    current = set()
    for entry in os.listdir(watch_path):
        full = os.path.join(watch_path, entry)
        if os.path.isdir(full):
            current.add(entry)
    
    new_items = current - set(known.keys())
    
    if new_items:
        return {
            "triggered": True,
            "context": f"{len(new_items)} new item(s) detected in {watch_path}",
            "state_update": {
                "items": {**known, **{k: "seen" for k in new_items}}
            }
        }
    
    return {"triggered": False, "context": "", "state_update": {"items": known}}
```

### Checking a threshold
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

## After Creating
1. Save the script to the `checks/` directory
2. Remind the user to add an entry to `checks.json`:
```json
{
  "id": "<check_id>",
  "script": "<filename>.py",
  "params": { ... }
}
```
3. Test it: `python3 checks/<filename>.py --params '{}' --state '{}'`
4. Run a dry test: `python3 pulse.py --config checks.json --state state.json --dry-run`
