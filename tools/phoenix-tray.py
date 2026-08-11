#!/usr/bin/env python3
"""
phoenix-tray.py — Phoenix system tray app
Sits in the system tray. Watches Downloads for new files and offers to intake
them into the Phoenix clone pool. Also lets you run suites from the tray menu.

Dependencies: pystray, pillow, plyer
  pip install pystray pillow plyer

Usage:
  python tools/phoenix-tray.py
  python tools/phoenix-tray.py --auto-intake   # no prompts, intake everything
"""

import os
import sys
import time
import queue
import threading
import subprocess
import argparse
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
    from plyer import notification
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install pystray pillow plyer")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT    = Path(__file__).resolve().parents[1]   # Phoenix-DevOps-oS/
INTAKE_PY    = REPO_ROOT / "phoenix-core" / "tools" / "intake.py"
USYS_PS1     = REPO_ROOT / "scripts" / "usys.ps1"
WATCH_DIR    = Path.home() / "Downloads"
SKIP_EXTS    = {".crdownload", ".tmp", ".part", ".download", ".partial"}
PYTHON       = sys.executable

# Files we've already seen this session (avoid double-intake on startup)
_seen: set = set()
_pending: queue.Queue = queue.Queue()   # files waiting for user decision


# ---------------------------------------------------------------------------
# Intake helpers
# ---------------------------------------------------------------------------

def intake_file(path: Path) -> bool:
    """Run intake.py on a file. Returns True on success."""
    try:
        result = subprocess.run(
            [PYTHON, str(INTAKE_PY), str(path)],
            capture_output=True, text=True, timeout=120
        )
        return result.returncode == 0
    except Exception:
        return False


def notify(title: str, message: str) -> None:
    try:
        notification.notify(title=title, message=message,
                            app_name="Phoenix", timeout=6)
    except Exception:
        pass  # notifications aren't critical


def run_suite(name: str) -> None:
    """Launch a usys suite in a new terminal window."""
    cmd = (
        f'pwsh -NoProfile -ExecutionPolicy Bypass -Command '
        f'". \'{USYS_PS1}\'; usys run {name}"'
    )
    subprocess.Popen(
        ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-Command", f". '{USYS_PS1}'; usys run {name}"],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )


# ---------------------------------------------------------------------------
# Downloads watcher (runs in background thread)
# ---------------------------------------------------------------------------

class DownloadsWatcher(threading.Thread):
    def __init__(self, auto_intake: bool = False):
        super().__init__(daemon=True, name="PhoenixWatcher")
        self.auto_intake = auto_intake
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        class Handler(FileSystemEventHandler):
            def __init__(self, auto_intake):
                self.auto_intake = auto_intake

            def on_created(self, event):
                if event.is_directory:
                    return
                path = Path(event.src_path)
                if path in _seen:
                    return
                if path.suffix.lower() in SKIP_EXTS:
                    return
                _seen.add(path)
                # Give the browser a moment to finish writing
                time.sleep(2)
                if not path.exists():
                    return
                if self.auto_intake:
                    ok = intake_file(path)
                    if ok:
                        notify("Phoenix ✓", f"Intaked: {path.name}")
                    else:
                        notify("Phoenix ✗", f"Intake failed: {path.name}")
                else:
                    _pending.put(path)
                    notify("Phoenix", f"New file: {path.name}\nOpen Phoenix tray → Pending")

        # watchdog not always available — fall back to polling
        try:
            from watchdog.observers import Observer
            observer = Observer()
            observer.schedule(Handler(self.auto_intake), str(WATCH_DIR), recursive=False)
            observer.start()
            while not self._stop_event.is_set():
                time.sleep(1)
            observer.stop()
            observer.join()
        except ImportError:
            # Pure polling fallback — no watchdog needed
            self._poll_loop()

    def _poll_loop(self):
        """Fallback: poll Downloads dir every 2 seconds."""
        known = set(WATCH_DIR.iterdir()) if WATCH_DIR.exists() else set()
        known |= _seen
        while not self._stop_event.is_set():
            time.sleep(2)
            if not WATCH_DIR.exists():
                continue
            current = set(WATCH_DIR.iterdir())
            new_files = current - known
            for path in new_files:
                if path.is_dir():
                    continue
                if path.suffix.lower() in SKIP_EXTS:
                    continue
                if path in _seen:
                    continue
                _seen.add(path)
                time.sleep(2)   # let the file finish writing
                if not path.exists():
                    continue
                if self.auto_intake:
                    ok = intake_file(path)
                    notify("Phoenix ✓" if ok else "Phoenix ✗",
                           f"{'Intaked' if ok else 'Intake failed'}: {path.name}")
                else:
                    _pending.put(path)
                    notify("Phoenix", f"New file: {path.name}\nOpen Phoenix tray → Pending")
            known = current


# ---------------------------------------------------------------------------
# Tray icon
# ---------------------------------------------------------------------------

def make_icon_image(color: str = "#3b82d4") -> Image.Image:
    """Draw a simple Phoenix 'P' icon. No external assets needed."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    # Background circle
    d.ellipse([2, 2, size - 2, size - 2], fill=color)
    # Simple 'P' shape
    d.rectangle([18, 14, 26, 50], fill="white")
    d.ellipse([18, 14, 46, 34], fill=color)
    d.ellipse([20, 16, 44, 32], fill="white")
    d.rectangle([20, 22, 44, 28], fill=color)
    return img


class PhoenixTray:
    def __init__(self, auto_intake: bool = False):
        self.auto_intake = auto_intake
        self.watcher     = None
        self.icon        = None
        self._watching   = False

    # ---- menu actions -------------------------------------------------------

    def toggle_watch(self, icon, item):
        if self._watching:
            self._stop_watch()
        else:
            self._start_watch()
        self._refresh_menu()

    def _start_watch(self):
        self.watcher = DownloadsWatcher(auto_intake=self.auto_intake)
        self.watcher.start()
        self._watching = True
        mode = "auto-intake" if self.auto_intake else "prompt"
        notify("Phoenix", f"Watching Downloads ({mode})")

    def _stop_watch(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        self._watching = False
        notify("Phoenix", "Watcher stopped")

    def show_pending(self, icon, item):
        pending = []
        while not _pending.empty():
            try:
                pending.append(_pending.get_nowait())
            except queue.Empty:
                break

        if not pending:
            notify("Phoenix", "No pending files.")
            return

        # Open a small PowerShell prompt window for Y/N on each file
        lines = []
        for p in pending:
            lines.append(
                f"Write-Host \"`nNew file: {p}\" -ForegroundColor Yellow; "
                f"$c = Read-Host 'Intake into Phoenix? [Y/n]'; "
                f"if ($c -eq '' -or $c -match '^[Yy]') "
                f"{{ & '{PYTHON}' '{INTAKE_PY}' '{p}' }}"
            )
        script = "; ".join(lines) + "; Write-Host ''; Write-Host 'Done.' -ForegroundColor Green; Start-Sleep 2"
        subprocess.Popen(
            ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )

    def run_debian(self, icon, item):
        run_suite("debian")

    def run_ubuntu(self, icon, item):
        run_suite("ubuntu")

    def open_clonepool(self, icon, item):
        clonepool = Path.home() / "Phoenix" / "clonepool"
        if clonepool.exists():
            subprocess.Popen(["explorer", str(clonepool)])

    def quit_app(self, icon, item):
        self._stop_watch()
        icon.stop()

    # ---- menu builder -------------------------------------------------------

    def _watch_label(self):
        return "⏹  Stop watcher" if self._watching else "▶  Watch Downloads"

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda text, item: self._watch_label(), self.toggle_watch),
            pystray.MenuItem("📋  Pending files…",   self.show_pending),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🐧  Run Debian VM",    self.run_debian),
            pystray.MenuItem("🟠  Run Ubuntu VM",    self.run_ubuntu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📂  Open clonepool",   self.open_clonepool),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("✕  Quit Phoenix tray", self.quit_app),
        )

    def _refresh_menu(self):
        if self.icon:
            self.icon.menu = self._build_menu()
            self.icon.update_menu()

    # ---- run ----------------------------------------------------------------

    def run(self):
        img  = make_icon_image()
        self.icon = pystray.Icon(
            name  = "Phoenix",
            icon  = img,
            title = "Phoenix",
            menu  = self._build_menu(),
        )
        # Auto-start watcher
        self._start_watch()
        self._refresh_menu()
        self.icon.run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phoenix system tray app")
    parser.add_argument("--auto-intake", action="store_true",
                        help="Intake every new download automatically (no prompt)")
    args = parser.parse_args()

    if not INTAKE_PY.exists():
        print(f"ERROR: intake.py not found at {INTAKE_PY}")
        print("Make sure you're running from inside the Phoenix-DevOps-oS repo.")
        sys.exit(1)

    print("Phoenix tray starting...")
    print(f"  Watching : {WATCH_DIR}")
    print(f"  Mode     : {'auto-intake' if args.auto_intake else 'prompt'}")
    print(f"  intake.py: {INTAKE_PY}")

    app = PhoenixTray(auto_intake=args.auto_intake)
    app.run()


if __name__ == "__main__":
    main()
