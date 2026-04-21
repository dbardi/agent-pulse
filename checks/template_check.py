#!/usr/bin/env python3
"""
Template for creating new Pulse check scripts.

USAGE:
    1. Copy this file: cp checks/template_check.py checks/check_mine.py
    2. Edit the detect() function with your sensor logic
    3. Add an entry to checks.json with your script name and params
    4. Test: python3 checks/check_mine.py --params '{"key": "value"}' --state '{}'

CONTRACT:
    Your script MUST print exactly one JSON object to stdout with three fields:
        triggered (bool)    - Does the agent need to wake up?
        context (str)       - What to tell the agent
        state_update (dict) - Data to merge into state.json under your check ID

    On error, print: {"triggered": false, "context": "", "state_update": {}, "error": "message"}
"""

import argparse
import json
import sys


def parse_args():
    parser = argparse.ArgumentParser(description="Pulse check script")
    parser.add_argument("--params", required=True, help="JSON string of check parameters")
    parser.add_argument("--state", required=True, help="JSON string of previous state for this check")
    return parser.parse_args()


def detect(params: dict, state: dict) -> dict:
    """
    YOUR SENSOR LOGIC GOES HERE.

    Args:
        params: The "params" object from checks.json for this check
        state:  The namespaced state from state.json for this check
                (e.g., state.json["my_check_id"] or {} on first run)

    Returns:
        dict with keys: triggered (bool), context (str), state_update (dict)
    """
    # Example: check if a file exists
    # path = params.get("path", "/tmp")
    # new_files = [f for f in os.listdir(path) if f not in state.get("seen_files", [])]
    #
    # if new_files:
    #     return {
    #         "triggered": True,
    #         "context": f"New files detected: {', '.join(new_files)}",
    #         "state_update": {
    #             "seen_files": state.get("seen_files", []) + new_files
    #         }
    #     }
    #
    # return {"triggered": False, "context": "", "state_update": {}}

    return {"triggered": False, "context": "", "state_update": {}}


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
