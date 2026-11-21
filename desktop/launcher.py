"""Dispensary Desk for Windows: one executable, several jobs.

  DispensaryDesk.exe                    run the server (started at boot by Task Scheduler on the server PC)
  DispensaryDesk.exe --open [URL]       open the app window (Edge/Chrome app mode); starts the local server if needed
  DispensaryDesk.exe --install-server   register the boot task + firewall rule, then start the server (installer)
  DispensaryDesk.exe --uninstall        stop the server, remove the task and firewall rule (uninstaller)
  DispensaryDesk.exe --backup-now       write a backup immediately

Data lives in %ProgramData%\\DispensaryDesk (database, secrets, backups, logs) and survives upgrades/uninstall.
"""
import json
import logging
import logging.handlers
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

APP_NAME = "Dispensary Desk"
TASK_NAME = "Dispensary Desk Server"
FIREWALL_RULE = "Dispensary Desk (port {port})"
DATA = Path(os.environ.get("DISPENSARY_DATA") or Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "DispensaryDesk")
CREATE_NO_WINDOW = 0x08000000
DEFAULT_CONFIG = {
    "port": 8000,
    "backup_keep_days": 30,
    # Extra backend settings, e.g. {"EMAIL_OTP": "true", "EMAIL_PROVIDER": "gmail_script", ...}
    "env": {},
}


# ---------------------------------------------------------------- paths & config

def bundle_dir() -> Path:
    """Folder holding migrations/ and web/ (PyInstaller's _internal), or the repo root when run from source."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def backend_dir() -> Path:
    """Where the `app` package lives when running from source (the frozen build has it inside the exe)."""
    return bundle_dir() / "backend"


def migrations_dir() -> Path:
    b = bundle_dir()
    return b / "migrations" if (b / "migrations").is_dir() else b / "backend" / "alembic"


def web_dir() -> Path:
    b = bundle_dir()
    return b / "web" if (b / "web").is_dir() else b / "frontend" / "dist"


def load_config() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / "config.json"
    cfg = dict(DEFAULT_CONFIG)
    if path.exists():
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            logging.getLogger("desktop").exception("config.json is invalid — using defaults")
    else:
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    return cfg


def load_secrets() -> dict:
    path = DATA / "secrets.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    values = {"JWT_SECRET": secrets.token_hex(32), "SYNC_SHARED_SECRET": secrets.token_hex(32)}
    path.write_text(json.dumps(values, indent=2), encoding="utf-8")
    return values


def db_path() -> Path:
    return DATA / "dispensary.db"


def server_env(cfg: dict) -> dict:
    env = {
        "ENVIRONMENT": "production",
        "APP_ROLE": "hospital",
        "STANDALONE": "true",
        "DESKTOP": "true",
        "RUN_SYNC_WORKER": "false",
        "COOKIE_SECURE": "false",  # plain http on the hospital LAN
        "DATABASE_URL": f"sqlite:///{db_path().as_posix()}",
        "STATIC_DIR": str(web_dir()),
        **load_secrets(),
    }
    env.update({k: str(v) for k, v in (cfg.get("env") or {}).items()})
    return env


# ---------------------------------------------------------------- logging

def setup_logging(name: str) -> None:
    (DATA / "logs").mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(DATA / "logs" / f"{name}.log", maxBytes=2_000_000, backupCount=5,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    # windowed build: there is no console, so anything printed must not crash
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


# ---------------------------------------------------------------- server

def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def server_healthy(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/health", timeout=timeout) as r:
            return r.status == 200
    except OSError:
        return False


def migrate(env: dict) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()  # no ini file: keeps logging untouched in the windowed build
    cfg.set_main_option("script_location", str(migrations_dir()))
    cfg.set_main_option("sqlalchemy.url", env["DATABASE_URL"])
    command.upgrade(cfg, "head")


def backup_now(keep_days: int) -> Path | None:
    src = db_path()
    if not src.exists():
        return None
    folder = DATA / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"dispensary-{datetime.now():%Y-%m-%d}.db"
    tmp = target.with_suffix(".tmp")
    source, dest = sqlite3.connect(src), sqlite3.connect(tmp)
    try:
        source.backup(dest)  # consistent copy even while the server is writing
    finally:
        dest.close()  # "with sqlite3.connect()" only commits; the files must be closed before the rename
        source.close()
    os.replace(tmp, target)
    backups = sorted(folder.glob("dispensary-*.db"))
    for old in backups[:-keep_days] if keep_days > 0 else []:
        old.unlink(missing_ok=True)
    logging.getLogger("desktop.backup").info("Backup written: %s", target)
    return target


def backup_loop(keep_days: int) -> None:
    log = logging.getLogger("desktop.backup")
    while True:
        try:
            if not (DATA / "backups" / f"dispensary-{datetime.now():%Y-%m-%d}.db").exists():
                backup_now(keep_days)
        except Exception:
            log.exception("Backup failed")
        time.sleep(3600)


def run_server() -> None:
    setup_logging("server")
    log = logging.getLogger("desktop")
    cfg = load_config()
    port = int(cfg["port"])
    if port_in_use(port):
        log.info("Port %s already in use — server already running; exiting", port)
        return
    env = server_env(cfg)
    os.environ.update(env)
    sys.path.insert(0, str(backend_dir()))
    log.info("Starting %s on port %s (data: %s)", APP_NAME, port, DATA)
    migrate(env)

    import uvicorn

    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings())
    threading.Thread(target=backup_loop, args=(int(cfg.get("backup_keep_days", 30)),), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=None, access_log=False)


# ---------------------------------------------------------------- app window

def open_window(url: str) -> None:
    """Edge (always present on Windows 10/11) in app mode looks like a normal program window."""
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for exe in candidates:
        if exe.is_file():
            subprocess.Popen([str(exe), f"--app={url}"], creationflags=CREATE_NO_WINDOW)
            return
    webbrowser.open(url)


def message(text: str, title: str = APP_NAME, error: bool = False) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)
    except Exception:
        print(text)


def open_app(url: str | None) -> None:
    setup_logging("launcher")
    cfg = load_config()
    local = url is None
    url = url or f"http://localhost:{cfg['port']}"
    if not server_healthy(url):
        if local:  # server PC: make sure the background server is running
            subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True, creationflags=CREATE_NO_WINDOW)
            deadline = time.time() + 60
            while time.time() < deadline and not server_healthy(url):
                time.sleep(1)
        if not server_healthy(url):
            where = "this computer" if local else url
            message(f"Dispensary Desk is not responding on {where}.\n\n"
                    + ("Restart the computer, or run 'Dispensary Desk Server' from the Start menu."
                       if local else "Check that the main (server) computer is switched on and on the same network."),
                    error=True)
            return
    open_window(url)


# ---------------------------------------------------------------- install / uninstall

TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Runs the Dispensary Desk server for this computer and the hospital network.</Description></RegistrationInfo>
  <Triggers><BootTrigger><Enabled>true</Enabled></BootTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author"><Exec><Command>{exe}</Command><WorkingDirectory>{cwd}</WorkingDirectory></Exec></Actions>
</Task>
"""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    logging.getLogger("desktop.install").info("%s -> %s %s", " ".join(cmd), r.returncode, (r.stdout + r.stderr).strip())
    return r


def install_server() -> int:
    setup_logging("install")
    cfg = load_config()
    load_secrets()
    exe = Path(sys.executable).resolve()
    xml = TASK_XML.replace("{exe}", str(exe)).replace("{cwd}", str(exe.parent))
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
        f.write(xml)
    try:
        r = _run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", f.name, "/F"])
    finally:
        os.unlink(f.name)
    rule = FIREWALL_RULE.format(port=cfg["port"])
    _run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule}"])
    _run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={rule}", "dir=in", "action=allow", "protocol=TCP",
          f"localport={cfg['port']}", "profile=private,domain"])
    _run(["schtasks", "/End", "/TN", TASK_NAME])
    _run(["schtasks", "/Run", "/TN", TASK_NAME])
    return r.returncode


def uninstall() -> int:
    setup_logging("install")
    cfg = load_config()
    _run(["schtasks", "/End", "/TN", TASK_NAME])
    _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    _run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={FIREWALL_RULE.format(port=cfg['port'])}"])
    # stop any other running copy (server or app launcher), but not this uninstall process itself
    _run(["taskkill", "/F", "/IM", Path(sys.executable).name, "/FI", f"PID ne {os.getpid()}"])
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        run_server()
        return 0
    cmd = argv[0]
    if cmd == "--open":
        open_app(argv[1] if len(argv) > 1 else None)
    elif cmd == "--install-server":
        return install_server()
    elif cmd == "--uninstall":
        return uninstall()
    elif cmd == "--backup-now":
        setup_logging("launcher")
        path = backup_now(int(load_config().get("backup_keep_days", 30)))
        message(f"Backup saved:\n{path}" if path else "No database yet — nothing to back up.")
    else:
        message(__doc__ or "", error=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
