# PyInstaller build for the Windows desktop app. Run through desktop\build.bat (it builds the web app first).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 (SPECPATH is provided by PyInstaller)

hidden = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    + collect_submodules("alembic")
    + collect_submodules("sqlalchemy.dialects.sqlite")
    + ["argon2", "argon2._password_hasher", "tzdata", "email.message", "smtplib"]
)

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(ROOT / "backend")],
    datas=[
        (str(ROOT / "backend" / "alembic"), "migrations"),
        (str(ROOT / "frontend" / "dist"), "web"),
        *collect_data_files("tzdata"),
        *collect_data_files("alembic"),
    ],
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "psycopg", "psycopg_binary", "watchfiles", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DispensaryDesk",
    console=False,  # no black window; logs go to %ProgramData%\DispensaryDesk\logs
    icon=str(ROOT / "desktop" / "app.ico") if (ROOT / "desktop" / "app.ico").exists() else None,
    version=str(ROOT / "desktop" / "version_info.txt") if (ROOT / "desktop" / "version_info.txt").exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="DispensaryDesk")
