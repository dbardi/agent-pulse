#!/usr/bin/env python3
"""
Check: Inbox Monitor

Scans the mail inbox directory for new email folders. Compares against
previous state to detect unseen items. Returns triggered=True when new
mail arrives, with sender and subject in the context.

Params (from checks.json):
    path (str): Path to the mail inbox directory

State (namespaced under check ID):
    items (dict): Map of folder_name → "seen" | "processed"
"""

import argparse
import json
import os
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Pulse check: inbox monitor")
    parser.add_argument("--params", required=True, help="JSON string of check parameters")
    parser.add_argument("--state", required=True, help="JSON string of previous state for this check")
    return parser.parse_args()


def detect(params: dict, state: dict) -> dict:
    inbox_path = os.path.expanduser(params.get("path", "~/mail/inbox"))
    known_items = state.get("items", {})

    if not os.path.isdir(inbox_path):
        return {
            "triggered": False,
            "context": "",
            "state_update": {},
            "error": f"Inbox path does not exist: {inbox_path}",
        }

    # List all subdirectories (each is one email)
    current_items = set()
    for entry in os.listdir(inbox_path):
        full = os.path.join(inbox_path, entry)
        if os.path.isdir(full):
            current_items.add(entry)

    # Find new items (not in state at all)
    new_items = current_items - set(known_items.keys())

    # Find seen-but-unprocessed items
    unprocessed = [k for k, v in known_items.items() if v == "seen"]

    # Items to trigger on: new + unprocessed
    trigger_items = new_items | set(unprocessed)

    if not trigger_items:
        return {"triggered": False, "context": "", "state_update": {}}

    # Build context by reading email.json from each new/unprocessed item
    senders = []
    subjects = []
    for item in sorted(trigger_items):
        email_file = os.path.join(inbox_path, item, "email.json")
        if os.path.isfile(email_file):
            try:
                with open(email_file) as f:
                    data = json.load(f)
                sender = data.get("from", "unknown")
                subject = data.get("subject", "(no subject)")
                senders.append(sender)
                subjects.append(subject)
            except (json.JSONDecodeError, OSError):
                senders.append("unknown")
                subjects.append("(parse error)")
        else:
            senders.append("unknown")
            subjects.append("(no email.json)")

    # Build context string
    lines = [f"{len(trigger_items)} new/unprocessed email(s):"]
    for i, item in enumerate(sorted(trigger_items)):
        lines.append(f"  - From: {senders[i]}, Subject: {subjects[i]} (dir: {item})")

    context = "\n".join(lines)

    # Update state: new items → "seen", unprocessed stay as "seen"
    updated_items = dict(known_items)
    for item in trigger_items:
        updated_items[item] = "seen"

    return {
        "triggered": True,
        "context": context,
        "state_update": {"items": updated_items},
    }


def main():
    args = parse_args()
    try:
        params = json.loads(args.params)
        state = json.loads(args.state)
    except json.JSONDecodeError as e:
        print(json.dumps({"triggered": False, "context": "", "state_update": {}, "error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    try:
        result = detect(params, state)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"triggered": False, "context": "", "state_update": {}, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
