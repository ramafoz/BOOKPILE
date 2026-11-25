# Installing BOOKPILE Local v1

BOOKPILE Local v1 is a single-user Windows application. It runs on your own
computer and can also be opened from a phone or tablet connected to the same
private Wi-Fi network. It does not require an online BOOKPILE account.

## Requirements

- Windows 10 or Windows 11, 64-bit.
- 64-bit Python 3.11 or newer.
- Node.js 20 LTS or newer, including npm.
- An internet connection during the first installation so dependencies can be
  downloaded. Routine catalogue use is local; only ISBN lookup and other
  external links need internet access.
- Enough free disk space for the application, cover photographs, and backups.

When installing Python, enable **Add Python to PATH**. Install Node.js from its
official LTS installer using the default options.

## Download and install

1. Download the BOOKPILE Local v1 ZIP from the GitHub release page.
2. Extract the complete ZIP to a permanent folder. Do not run BOOKPILE from
   inside the compressed archive. A folder such as
   `C:\Users\YourName\BOOKPILE` is suitable.
3. Open PowerShell in the extracted BOOKPILE folder.
4. Run:

   ```powershell
   Set-ExecutionPolicy -Scope Process RemoteSigned
   .\install-bookpile.ps1
   ```

The installer checks Python and Node.js, creates an isolated Python
environment, installs exact frontend dependencies, builds the application,
prepares an empty catalogue if no catalogue exists, and creates Start/Stop
desktop shortcuts. It never overwrites an existing catalogue or cover folder.

To install without desktop shortcuts:

```powershell
.\install-bookpile.ps1 -SkipDesktopShortcuts
```

## Start and stop

Double-click **Start BOOKPILE** on the desktop. BOOKPILE starts in the
background and displays its address. The address is also copied to the
clipboard.

- On the host computer, open the displayed address in a modern browser.
- On a phone or tablet, connect to the same private Wi-Fi and open the same
  address.
- If no home network is available, BOOKPILE falls back to
  `http://127.0.0.1:5173` for use on the host computer only.

Double-click **Stop BOOKPILE** when finished. Always stop BOOKPILE before
moving its folder or manually copying application files.

Windows Firewall may ask whether Node.js may communicate on the network.
Allow access on **Private networks** only. Do not expose ports 5173 or 8000 on
your router and do not use the local edition over a public or untrusted Wi-Fi.

## Update or reinstall

Before every update:

1. Download a full ZIP backup from **Settings → Data & backups**.
2. Stop BOOKPILE.
3. Keep that backup outside the BOOKPILE installation folder.

Release-specific update instructions will state whether files can be replaced
in place. Never replace `backend/data` with files from a release ZIP. Running
the installer again is safe for catalogue data, but dependencies may be
updated to the versions locked by that release.

## Uninstall

1. Download and verify a final full ZIP backup.
2. Stop BOOKPILE.
3. Delete the Start/Stop shortcuts.
4. Delete the extracted BOOKPILE folder only after confirming the external
   backup is readable and stored safely.

There is no cloud copy in BOOKPILE Local. Deleting the folder without a full
backup deletes the only catalogue and cover collection.

See [USER_GUIDE.md](USER_GUIDE.md) for normal use and
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) for startup problems.

## Licence and warranty

BOOKPILE is free software under `AGPL-3.0-or-later`, copyright © 2026 Javier
Ramalleira Fernández. It is provided without warranty. Read `COPYRIGHT` and
`LICENSE` in the installation folder for the complete terms.
