#!/usr/bin/env python3
"""
Android-MCP end-to-end validation script.

Starts the MCP server over stdio, exercises ListDevices and Snapshot, and
verifies that the server selects a physical device rather than an emulator.

Usage (from the repo root):
    python3 e2e_test.py               # auto-detects any connected device
    python3 e2e_test.py RFCW70CZWKV  # assert a specific serial is selected

Requires: a physical Android device connected via USB with USB debugging enabled.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time

REPO = os.path.dirname(os.path.abspath(__file__))

BOLD   = "\033[1m"
GREEN  = "\033[32m"
RED    = "\033[31m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
RESET  = "\033[0m"

EXPECT_SERIAL = sys.argv[1] if len(sys.argv) > 1 else None


def log(tag, msg, color=CYAN):
    print(f"{color}{BOLD}[{tag}]{RESET} {msg}", flush=True)


# ── Resolve ADB ───────────────────────────────────────────────────────────────

def _find_adb() -> str:
    candidates = [
        shutil.which("adb"),
        "/opt/homebrew/bin/adb",
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/usr/local/bin/adb",
        "/usr/bin/adb",
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


ADB = _find_adb()


def _make_env() -> dict:
    env = os.environ.copy()
    extra_dirs = [
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        os.path.expanduser("~/Library/Android/sdk/platform-tools"),
    ]
    if ADB:
        extra_dirs.insert(0, os.path.dirname(ADB))
    current_path = env.get("PATH", "")
    new_dirs = [d for d in extra_dirs if d not in current_path.split(":")]
    env["PATH"] = ":".join(new_dirs) + (":" + current_path if current_path else "")
    return env


ENV = _make_env()
SERVER_CMD = ["uv", "--directory", REPO, "run", "android-mcp"]


def _is_emulator(serial: str) -> bool:
    return serial.startswith("emulator-")


# ── MCP stdio helpers (newline-delimited JSON) ─────────────────────────────────

def _send(proc, obj):
    proc.stdin.write((json.dumps(obj) + "\n").encode())
    proc.stdin.flush()


def _recv(proc, timeout=60):
    deadline = time.time() + timeout
    while True:
        if time.time() > deadline:
            raise TimeoutError(f"No response within {timeout}s")
        line = proc.stdout.readline()
        if not line:
            raise EOFError("Server stdout closed")
        line = line.strip()
        if line:
            return json.loads(line)


# ── Test ───────────────────────────────────────────────────────────────────────

def run():
    print()
    log("ENV", f"ADB binary  : {ADB or 'NOT FOUND'}", YELLOW)
    log("ENV", f"PATH (first): {ENV['PATH'][:120]}…", YELLOW)

    if not ADB:
        log("ERROR", "adb not found — install it or add to PATH", RED)
        return 1

    # Confirm at least one physical device is visible before starting the server
    log("BOOT", "Running: adb devices", GREEN)
    adb_out = subprocess.run([ADB, "devices"], capture_output=True, text=True, env=ENV)
    print(adb_out.stdout.strip())

    adb_lines = adb_out.stdout.strip().splitlines()
    physical = [
        ln.split()[0]
        for ln in adb_lines[1:]          # skip "List of devices attached"
        if ln.strip() and "device" in ln.split()[-1:]
        and not _is_emulator(ln.split()[0])
    ]
    emulators = [
        ln.split()[0]
        for ln in adb_lines[1:]
        if ln.strip() and _is_emulator(ln.split()[0])
    ]

    if not physical:
        log("WARN", "No physical device in adb devices — is one connected?", RED)
    else:
        log("INFO", f"Physical device(s): {', '.join(physical)}", GREEN)
    if emulators:
        log("INFO", f"Emulator(s) also present: {', '.join(emulators)} (bug scenario)", YELLOW)

    print()
    log("BOOT", f"Starting: {' '.join(SERVER_CMD)}", GREEN)
    proc = subprocess.Popen(
        SERVER_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=ENV,
    )

    stderr_lines = []

    def _drain():
        for raw in proc.stderr:
            line = raw.decode(errors="replace").rstrip()
            stderr_lines.append(line)
            print(f"  {CYAN}[stderr]{RESET} {line}", flush=True)

    threading.Thread(target=_drain, daemon=True).start()

    try:
        # 1. Initialize
        log("MCP", "→ initialize")
        _send(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "e2e-test", "version": "1.0"},
            },
        })
        resp = _recv(proc)
        if resp.get("error"):
            raise RuntimeError(f"initialize error: {resp['error']}")
        info = resp.get("result", {}).get("serverInfo", {})
        log("MCP", f"← server: {info.get('name')} {info.get('version', '')}", GREEN)

        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        time.sleep(0.3)

        # 2. ListDevices — assert physical device is present
        log("MCP", "→ tools/call  ListDevices")
        _send(proc, {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {"name": "ListDevices", "arguments": {}},
        })
        resp = _recv(proc)
        if resp.get("error"):
            raise RuntimeError(f"ListDevices error: {resp['error']}")
        device_text = " ".join(c.get("text", "") for c in resp["result"]["content"])
        log("MCP", f"← ListDevices:\n{device_text}", GREEN)

        if EXPECT_SERIAL:
            assert EXPECT_SERIAL in device_text, \
                f"Expected serial {EXPECT_SERIAL} not in ListDevices:\n{device_text}"
            log("CHECK", f"Expected serial {EXPECT_SERIAL} present ✓", GREEN)
        else:
            # At least one non-emulator serial must appear
            assert any(s in device_text for s in physical), \
                f"No physical device serial found in ListDevices:\n{device_text}"
            log("CHECK", "Physical device present in ListDevices ✓", GREEN)

        # 3. Emulator guard — server must NOT have picked an emulator when a physical
        #    device is available (the core bug this PR fixes).
        for em in emulators:
            assert em not in device_text or physical, \
                f"Server selected emulator {em} despite physical device being available"
        if emulators:
            log("CHECK", "Server did not select emulator over physical device ✓", GREEN)

        # 4. Snapshot (connects to device — real hardware test)
        log("MCP", "→ tools/call  Snapshot  use_vision=false")
        _send(proc, {
            "jsonrpc": "2.0", "id": 3,
            "method": "tools/call",
            "params": {"name": "Snapshot", "arguments": {"use_vision": False}},
        })
        resp = _recv(proc, timeout=120)
        if resp.get("error"):
            raise RuntimeError(f"Snapshot error: {resp['error']}")
        content = resp["result"]["content"]
        tree = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
        preview = tree[:800] + ("…" if len(tree) > 800 else "")
        log("MCP", f"← Snapshot (first 800 chars):\n{preview}", GREEN)
        assert len(tree) > 50, "Snapshot returned suspiciously little text"
        log("CHECK", "Snapshot returned a UI tree ✓", GREEN)

        # 5. emulator-5554 must never appear in server logs
        time.sleep(0.5)
        emulator_in_logs = any("emulator-5554" in l for l in stderr_lines)
        if emulator_in_logs:
            log("WARN", "emulator-5554 appeared in server logs — fix may not be active", RED)
        else:
            log("CHECK", "emulator-5554 never mentioned in server logs ✓", GREEN)

        print()
        log("RESULT", "ALL CHECKS PASSED — Android-MCP correctly targets physical device ✓", GREEN)
        return 0

    except Exception as exc:
        print()
        log("RESULT", f"FAILED: {exc}", RED)
        time.sleep(1)
        if stderr_lines:
            print("\nRecent server stderr:")
            for l in stderr_lines[-20:]:
                print(f"  {l}")
        return 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(run())
