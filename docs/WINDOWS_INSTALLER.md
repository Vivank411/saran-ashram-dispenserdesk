# Windows installer (hospital computers)

One file, `DispensaryDesk-Setup-<version>.exe`, installs Dispensary Desk on hospital PCs. Python, Node.js, PostgreSQL and internet are not needed on those computers.

## Building the installer (developer PC)

Needs Python 3.11+, Node.js 20+ and Inno Setup 6 (`winget install JRSoftware.InnoSetup`).

```cmd
desktop\build.bat 1.0.0
```

Output: `desktop\Output\DispensaryDesk-Setup-1.0.0.exe` (about 22 MB). Raise the version number for each new release.

## Installing at the hospital

1. **Main computer first.** Run the setup on the PC that will stay switched on, choose **Main computer (server)** and finish. The last page shows this computer's name, for example `DISPENSARY-PC`. Write it down.
2. Open **Dispensary Desk** from the desktop. The first time, it shows the sign-up screen to create the Admin account.
3. **Each counter.** Run the same setup, choose **Counter computer** and type the main computer's name from step 1. The desktop shortcut opens the app from the main computer.

All computers must be on the same hospital network. On the main computer, set the network to **Private** in Windows Settings ➔ Network. The installer opens port 8000 only for private and domain networks.

## How it runs

| | Main computer | Counter |
|---|---|---|
| Server | Starts automatically at Windows boot, before anyone logs in, as the task *Dispensary Desk Server*. It restarts itself if it stops. | None |
| App window | Desktop shortcut opens `http://localhost:8000` in an Edge app window | Desktop shortcut opens `http://<main-pc>:8000` |
| Data | `C:\ProgramData\DispensaryDesk\dispensary.db` | Nothing stored |

## Data, backups and settings (main computer)

Everything is in `C:\ProgramData\DispensaryDesk`. The Start menu has a **Data and backups folder** shortcut.

- `dispensary.db`: all bills, stock and accounts.
- `backups\dispensary-YYYY-MM-DD.db`: an automatic daily backup, keeping the last 30. Start menu ➔ **Back up now** makes one immediately. Copy the `backups` folder to a USB drive regularly.
- `secrets.json`: sign-in signing keys. Keep it with the data if you ever move computers.
- `logs\server.log`: check this first if something goes wrong.
- `config.json`: holds the port (default 8000), how many daily backups to keep, and `env` for extra settings such as email OTP. Restart the computer after changing it.

**Restore a backup:** right-click the *Dispensary Desk Server* task in Task Scheduler and choose End. Copy the backup over `dispensary.db` and delete `dispensary.db-wal` and `dispensary.db-shm` if they exist. Then restart the computer.

**Move to a new main computer:** install on the new PC as the main computer. Stop the server on both PCs. Copy `dispensary.db` and `secrets.json` from the old PC to the same folder on the new PC, then restart the new PC. Re-run the setup on the counters with the new computer name.

## Updating

Run the newer `DispensaryDesk-Setup-x.y.z.exe` on each computer. It remembers whether the PC is the main computer or a counter, and which main computer to use. Data is kept, and database changes apply automatically when the server starts.

## Uninstalling

Use Windows Settings ➔ Apps ➔ Dispensary Desk ➔ Uninstall. This removes the program, the startup task and the firewall rule. The data in `C:\ProgramData\DispensaryDesk` is **kept**. Delete that folder yourself if you really want to erase everything.
