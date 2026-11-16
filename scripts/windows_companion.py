"""Run from the repository root: py -m scripts.windows_companion.

Pair using the token shown on the focus-session page. Ctrl+C stops collection.
"""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
from getpass import getpass
import json
from pathlib import PureWindowsPath
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class WindowsSensor:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("The companion requires Windows")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.GetForegroundWindow.argtypes = []
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LastInputInfo)]
        self.user32.GetLastInputInfo.restype = wintypes.BOOL
        self.kernel32.GetTickCount.argtypes = []
        self.kernel32.GetTickCount.restype = wintypes.DWORD
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                          wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    def sample(self, idle_threshold):
        info = LastInputInfo(ctypes.sizeof(LastInputInfo), 0)
        if not self.user32.GetLastInputInfo(ctypes.byref(info)):
            return "unknown", None
        idle_seconds = ((self.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000
        if idle_seconds >= idle_threshold:
            return "idle", None
        window = self.user32.GetForegroundWindow()
        if not window:
            return "unknown", None
        process_id = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
        handle = self.kernel32.OpenProcess(0x1000, False, process_id.value)
        if not handle:
            return "unknown", None
        try:
            size = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(size.value)
            if not self.kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                return "unknown", None
            return "active", PureWindowsPath(path.value).name.lower()
        finally:
            self.kernel32.CloseHandle(handle)


def api(server, token, path, payload=None):
    request = Request(server + "/api/v1/activity/companion" + path,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def transmit(server, token, payload):
    # Retain this exact interval across retries. No new sensing while disconnected.
    for attempt in range(6):
        try:
            return api(server, token, "/intervals", payload)
        except HTTPError as exc:
            if exc.code < 500:
                raise
        except (URLError, TimeoutError, OSError):
            pass
        print("Backend unavailable. Retrying the last interval; sensing is paused.", flush=True)
        time.sleep(2)
    raise RuntimeError("Backend unavailable. Restart the companion when the server is reachable.")


def run(server, token):
    sensor = WindowsSensor()
    status = api(server, token, "")
    sequence = status["next_sequence"]
    print("Monitoring enabled for this focus session. Ctrl+C stops collection.", flush=True)
    print("Records executable names and idle intervals. Idle threshold is 60 seconds.", flush=True)
    previous_state = None
    shown_nudges = set()
    while True:
        # Authenticate before sampling, including after a retry or suspend/resume.
        api(server, token, "")
        state, app_name = sensor.sample(status["idle_seconds"])
        started = datetime.now(timezone.utc)
        time.sleep(2)
        ended = datetime.now(timezone.utc)
        if not 0 < (ended - started).total_seconds() <= 5:
            continue
        payload = {"sequence": sequence, "started_at": started.isoformat(), "ended_at": ended.isoformat(),
                   "state": state, "app_name": app_name}
        result = transmit(server, token, payload) or {}
        for nudge in result.get("nudges", []):
            if nudge["id"] not in shown_nudges:
                print("TimeBlindAI reminder: " + nudge["message"], flush=True)
                shown_nudges.add(nudge["id"])
        sequence += 1
        current_state = (state, app_name)
        if current_state != previous_state:
            print(f"{ended:%H:%M:%S}  {app_name or state}", flush=True)
            previous_state = current_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--check", action="store_true", help="Read one native sample and exit without uploading")
    args = parser.parse_args()
    server = args.server.rstrip("/")
    parsed = urlparse(server)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("Use a backend HTTP(S) base URL")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        parser.error("Remote backends require HTTPS")
    try:
        if args.check:
            print(WindowsSensor().sample(60))
            return
        token = getpass("Paste the pairing token from the focus-session page: ").strip()
        if not token:
            parser.error("Pairing token is required")
        run(server, token)
    except KeyboardInterrupt:
        print("\nCompanion stopped.")
    except HTTPError as exc:
        if exc.code in (401, 403):
            print("Monitoring stopped. Enable monitoring in the app to pair again.")
        else:
            parser.exit(1, f"Companion request failed (HTTP {exc.code}). Restart with a fresh pairing token.\n")
    except (RuntimeError, URLError, TimeoutError, OSError) as exc:
        parser.exit(1, f"Companion stopped: {exc}\n")


if __name__ == "__main__":
    main()
