"""Read Windows active firewall policy without changing or logging it."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.firewall.model import FirewallProfile, FirewallRule
from personalcontext.network.firewall.policy import firewall_allows_private_only
from personalcontext.network.firewall.script import SCRIPT


def _parse(payload: object) -> tuple[list[FirewallProfile], list[FirewallRule]] | None:
    try:
        if not isinstance(payload, dict) or payload.keys() != {"profiles", "rules"}:
            return None
        profiles, rules = payload["profiles"], payload["rules"]
        if not isinstance(profiles, list) or not isinstance(rules, list) or len(rules) > 4096:
            return None
        parsed_profiles = []
        for item in profiles:
            if not isinstance(item, dict) or item.keys() != {"name", "enabled", "inbound"}:
                return None
            if not isinstance(item["name"], str) or type(item["enabled"]) is not bool or not isinstance(item["inbound"], str):
                return None
            parsed_profiles.append(FirewallProfile(item["name"], item["enabled"], item["inbound"]))
        parsed_rules = []
        for item in rules:
            if (not isinstance(item, dict)
                    or item.keys() != {"profiles", "protocol", "ports", "remote", "local", "program", "edge", "unrestricted"}):
                return None
            if any(not isinstance(item[name], list) or not all(isinstance(v, str) for v in item[name])
                   for name in ("profiles", "ports", "remote", "local")):
                return None
            if any(not isinstance(item[name], str) for name in ("protocol", "program", "edge")) or type(item["unrestricted"]) is not bool:
                return None
            parsed_rules.append(FirewallRule(frozenset(item["profiles"]), item["protocol"], tuple(item["ports"]),
                                             tuple(item["remote"]), item["program"], tuple(item["local"]), item["edge"],
                                             item["unrestricted"]))
        return parsed_profiles, parsed_rules
    except (KeyError, TypeError, ValueError):
        return None


def read_firewall_snapshot(boundary: PrivateBoundary) -> tuple[list[FirewallProfile], list[FirewallRule]] | None:
    """Read a bounded policy snapshot for the selected interface; never log it."""
    if sys.platform != "win32" or not isinstance(boundary, PrivateBoundary):
        return None
    try:
        system_root = os.environ["SystemRoot"]
        shell = Path(system_root) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        env = os.environ.copy()
        env["PC_FIREWALL_ADDRESS"] = boundary.address
        encoded = base64.b64encode(SCRIPT.encode("utf-16le")).decode("ascii")
        result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                capture_output=True, timeout=45, env=env,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        if result.returncode != 0 or not 0 < len(result.stdout) <= 4 * 1024 * 1024:
            return None
        return _parse(json.loads(result.stdout.decode("utf-8-sig")))
    except (OSError, subprocess.SubprocessError, KeyError, UnicodeError, ValueError):
        return None


def inspect_firewall(boundary: PrivateBoundary, executable: str) -> bool:
    """Return false if Windows policy cannot be read or cannot be shown restricted."""
    snapshot = read_firewall_snapshot(boundary)
    return snapshot is not None and firewall_allows_private_only(boundary, executable, *snapshot)
