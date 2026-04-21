#!/usr/bin/env python3
"""
Check: System Health

Monitors disk usage and process status. Triggers when disk exceeds
threshold or when required processes are not running.

Params (from checks.json):
    disk_limit (int): Disk usage percentage threshold (default: 90)
    processes (list[str]): List of process names that must be running
"""

import argparse
import json
import os
import shutil
import subprocess
import sys


def parse_args():
    parser = argparse.ArgumentParser(description="Pulse check: system health")
    parser.add_argument("--params", required=True, help="JSON string of check parameters")
    parser.add_argument("--state", required=True, help="JSON string of previous state for this check")
    return parser.parse_args()


def check_disk(limit: int) -> list[str]:
    """Check disk usage on all mounted filesystems. Returns list of warnings."""
    warnings = []
    # Only check real filesystems (skip squashfs, tmpfs, sysfs, etc.)
    real_fs_types = {"ext4", "ext3", "ext2", "xfs", "btrfs", "zfs", "ntfs", "vfat", "apfs"}
    try:
        mount_output = subprocess.run(
            ["findmnt", "-lno", "TARGET,FSTYPE"],
            capture_output=True, text=True, timeout=5
        )
        if mount_output.returncode != 0:
            targets = ["/"]
        else:
            targets = []
            for line in mount_output.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1] in real_fs_types:
                    targets.append(parts[0])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        targets = ["/"]

    for target in targets:
        try:
            usage = shutil.disk_usage(target)
            if usage.total == 0:
                continue
            percent = int((usage.used / usage.total) * 100)
            if percent >= limit:
                warnings.append(f"Disk {target} at {percent}% (threshold: {limit}%)")
        except (OSError, PermissionError):
            continue

    return warnings


def check_processes(required: list[str]) -> list[str]:
    """Check if required processes are running. Returns list of missing."""
    if not required:
        return []

    missing = []
    try:
        ps_output = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=5
        )
        running = ps_output.stdout.lower()
        for proc in required:
            if proc.lower() not in running:
                missing.append(proc)
    except (subprocess.TimeoutExpired, OSError) as e:
        missing.append(f"(error checking processes: {e})")

    return missing


def detect(params: dict, state: dict) -> dict:
    disk_limit = params.get("disk_limit", 90)
    required_procs = params.get("processes", [])

    alerts = []

    # Check disk
    disk_warnings = check_disk(disk_limit)
    alerts.extend(disk_warnings)

    # Check processes
    missing_procs = check_processes(required_procs)
    for proc in missing_procs:
        alerts.append(f"Process not running: {proc}")

    if not alerts:
        return {"triggered": False, "context": "", "state_update": {}}

    context = "System health issues detected:\n" + "\n".join(f"  - {a}" for a in alerts)

    return {
        "triggered": True,
        "context": context,
        "state_update": {
            "last_alert": context,
            "alert_count": len(alerts),
        },
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
