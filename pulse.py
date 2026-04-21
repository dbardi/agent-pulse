#!/usr/bin/env python3
"""
Pulse — Agent Heartbeat Runner

Runs zero-cost sensor scripts, batches triggered results, and invokes
an AI agent only when something needs attention.

Usage:
    python3 pulse.py [--config checks.json] [--state state.json] [--dry-run]
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = "checks.json"
DEFAULT_STATE = "state.json"
LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "heartbeat.log"

SCRIPT_TIMEOUT = 10          # seconds per check script
COOLDOWN_MINUTES = 15         # minimum minutes between agent invocations
DAILY_CAP = 20                # max agent invocations per day
MAX_RETRIES = 1               # retry failed items once before dead-lettering

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Also log to stderr for manual runs
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(console)


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path: str, state: dict):
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Safety rails
# ---------------------------------------------------------------------------

def is_cooled_down(state: dict) -> bool:
    """Check if enough time has passed since last agent invocation."""
    last_invocation = state.get("_meta", {}).get("last_invocation")
    if not last_invocation:
        return True
    last = datetime.fromisoformat(last_invocation)
    now = datetime.now(timezone.utc)
    diff = (now - last).total_seconds() / 60
    return diff >= COOLDOWN_MINUTES


def under_daily_cap(state: dict) -> bool:
    """Check if we haven't exceeded the daily invocation limit."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    invocations_today = state.get("_meta", {}).get("invocations", {}).get(today, 0)
    return invocations_today < DAILY_CAP


def is_dead_letter(state: dict, check_id: str) -> bool:
    """Check if this check has already been retried and failed."""
    check_state = state.get(check_id, {})
    failed = check_state.get("_failed", {})
    if not failed:
        return False
    retry_count = failed.get("retries", 0)
    return retry_count > MAX_RETRIES


# ---------------------------------------------------------------------------
# Script runner
# ---------------------------------------------------------------------------

def run_check(check: dict, state: dict) -> dict:
    """Run a single check script with timeout and error handling."""
    check_id = check["id"]
    script = str(Path(__file__).parent / "checks" / check["script"])
    params = json.dumps(check.get("params", {}))
    check_state = json.dumps(state.get(check_id, {}))

    if not os.path.isfile(script):
        logging.error(f"[{check_id}] Script not found: {script}")
        return {"id": check_id, "triggered": False, "context": "", "state_update": {}, "error": "script not found"}

    try:
        result = subprocess.run(
            [sys.executable, script, "--params", params, "--state", check_state],
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()[:500]
            logging.error(f"[{check_id}] Script exited {result.returncode}: {stderr}")
            return {"id": check_id, "triggered": False, "context": "", "state_update": {}, "error": stderr}

        # Parse stdout as JSON
        output = json.loads(result.stdout.strip())
        return {
            "id": check_id,
            "triggered": output.get("triggered", False),
            "context": output.get("context", ""),
            "state_update": output.get("state_update", {}),
            "error": output.get("error", ""),
        }

    except subprocess.TimeoutExpired:
        logging.error(f"[{check_id}] Script timed out after {SCRIPT_TIMEOUT}s")
        return {"id": check_id, "triggered": False, "context": "", "state_update": {}, "error": "timeout"}

    except json.JSONDecodeError as e:
        logging.error(f"[{check_id}] Invalid JSON output: {e}")
        return {"id": check_id, "triggered": False, "context": "", "state_update": {}, "error": f"invalid json: {e}"}

    except Exception as e:
        logging.error(f"[{check_id}] Unexpected error: {e}")
        return {"id": check_id, "triggered": False, "context": "", "state_update": {}, "error": str(e)}


# ---------------------------------------------------------------------------
# Agent invocation
# ---------------------------------------------------------------------------

def invoke_agent(contexts: list[dict], state: dict, dry_run: bool = False) -> bool:
    """Invoke the AI agent with batched context from all triggered checks."""
    if not contexts:
        return False

    # Build the prompt
    lines = ["HEARTBEAT ALERT — the following sensors triggered:\n"]
    for i, ctx in enumerate(contexts, 1):
        check_id = ctx["id"]
        context = ctx["context"]
        lines.append(f"{i}. [{check_id}] {context}")

    # Add instructions for email handling
    lines.append("\nRead the relevant data files and take appropriate action.")
    lines.append("For emails: read /home/hermes/mail/inbox/<dir>/email.json, summarize the content, and reply via Resend if appropriate.")
    lines.append("After processing, report a brief summary back.")

    prompt = "\n".join(lines)

    if dry_run:
        logging.info(f"[DRY RUN] Would invoke agent with prompt:\n{prompt}")
        print(f"\n--- DRY RUN: Agent invocation ---\n{prompt}\n")
        return False

    # Build the command
    cmd = [
        "hermes", "chat", "-q", prompt,
        "--skills", "resend-email-setup,telegram-communication-protocol",
    ]

    logging.info(f"Invoking agent with {len(contexts)} triggered checks")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            logging.info(f"Agent invocation completed successfully")
            logging.debug(f"Agent output: {result.stdout[:1000]}")
            return True
        else:
            logging.error(f"Agent invocation failed (exit {result.returncode}): {result.stderr[:500]}")
            return False
    except subprocess.TimeoutExpired:
        logging.error("Agent invocation timed out after 120s")
        return False
    except Exception as e:
        logging.error(f"Agent invocation error: {e}")
        return False


# ---------------------------------------------------------------------------
# Dead letter alert
# ---------------------------------------------------------------------------

def alert_dead_letter(check_id: str, state: dict):
    """Send a Telegram alert for items that exceeded max retries."""
    logging.warning(f"[DEAD LETTER] {check_id} exceeded max retries — alerting user")

    # Use Telegram Bot API to send alert
    try:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            logging.error("Cannot send dead letter alert: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
            return

        message = f"⚠️ DEAD LETTER: Check `{check_id}` has failed after {MAX_RETRIES} retries and requires manual attention."

        subprocess.run([
            "curl", "-s", "-X", "POST",
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}),
        ], timeout=10)
    except Exception as e:
        logging.error(f"Failed to send dead letter alert: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pulse — Agent Heartbeat Runner")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to checks.json")
    parser.add_argument("--state", default=DEFAULT_STATE, help="Path to state.json")
    parser.add_argument("--dry-run", action="store_true", help="Run checks but don't invoke agent")
    args = parser.parse_args()

    setup_logging()

    # Load config and state
    try:
        with open(args.config) as f:
            config = json.load(f)
    except FileNotFoundError:
        logging.error(f"Config not found: {args.config}")
        print(f"Error: Config not found: {args.config}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"Invalid config JSON: {e}")
        sys.exit(1)

    checks = config.get("checks", [])
    state = load_state(args.state)

    if not checks:
        logging.info("No checks configured — nothing to do")
        return

    logging.info(f"Running {len(checks)} check(s)")

    # Run all checks
    results = []
    for check in checks:
        check_id = check["id"]

        # Skip dead-lettered checks
        if is_dead_letter(state, check_id):
            logging.info(f"[{check_id}] Skipping — dead lettered (exceeded retries)")
            continue

        result = run_check(check, state)
        results.append(result)

        # Handle errors — track failures
        if result["error"]:
            failed = state.get(check_id, {}).get("_failed", {})
            retries = failed.get("retries", 0) + 1
            state.setdefault(check_id, {})["_failed"] = {"retries": retries, "last_error": result["error"], "last_attempt": datetime.now(timezone.utc).isoformat()}

            if retries > MAX_RETRIES:
                alert_dead_letter(check_id, state)
        else:
            # Clear any previous failure state on success
            state.get(check_id, {}).pop("_failed", None)

        # Namespaced state update
        if result["state_update"]:
            state[check_id] = {**state.get(check_id, {}), **result["state_update"]}
            # Preserve _failed if it exists
            # (already handled above)

        status = "TRIGGERED" if result["triggered"] else "OK"
        error_tag = f" (error: {result['error'][:80]})" if result["error"] else ""
        logging.info(f"[{check_id}] {status}{error_tag}")

    # Determine if we should invoke the agent
    triggered = [r for r in results if r["triggered"]]

    if triggered:
        if not is_cooled_down(state):
            logging.info(f"Cooldown active — skipping agent invocation ({len(triggered)} items queued)")
        elif not under_daily_cap(state):
            logging.warning(f"Daily cap ({DAILY_CAP}) reached — skipping agent invocation")
        else:
            success = invoke_agent(triggered, state, dry_run=args.dry_run)

            if success or args.dry_run:
                # Update invocation metadata
                now = datetime.now(timezone.utc)
                today = now.strftime("%Y-%m-%d")
                state.setdefault("_meta", {})
                state["_meta"]["last_invocation"] = now.isoformat()
                state["_meta"].setdefault("invocations", {})
                state["_meta"]["invocations"][today] = state["_meta"]["invocations"].get(today, 0) + 1

                # Mark triggered items as processed
                for r in triggered:
                    check_state = state.get(r["id"], {})
                    if "_pending" in check_state:
                        for item_id in list(check_state["_pending"]):
                            check_state["_pending"][item_id] = "processed"
            else:
                logging.error("Agent invocation failed — items remain in 'seen' state for next run")
    else:
        logging.info("All checks silent — no action needed")

    # Save state
    state["_meta"] = state.get("_meta", {})
    state["_meta"]["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(args.state, state)


if __name__ == "__main__":
    main()
