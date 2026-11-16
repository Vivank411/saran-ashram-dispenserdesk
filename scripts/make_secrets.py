"""Create random secrets for this computer (once). Written as a .cmd file the run scripts can load."""
import secrets
import sys
from pathlib import Path

target = Path(sys.argv[1])
if target.exists():
    print(f"Secrets already exist: {target}")
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "@echo off",
        f'set "SYNC_SHARED_SECRET={secrets.token_hex(32)}"',
        f'set "HOSPITAL_JWT_SECRET={secrets.token_hex(32)}"',
        f'set "CLOUD_JWT_SECRET={secrets.token_hex(32)}"',
    ]
    target.write_text("\r\n".join(lines) + "\r\n", encoding="ascii")
    print(f"Created secrets: {target}")
