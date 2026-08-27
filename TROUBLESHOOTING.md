# Troubleshooting BOOKPILE Local v1

## PowerShell blocks the installer

Open a new PowerShell window in the BOOKPILE folder and run:

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned
.\install-bookpile.ps1
```

The `Process` scope applies only to that PowerShell session.

## Python is not found

Install 64-bit Python 3.11 or newer and enable **Add Python to PATH**. Close and
reopen PowerShell before running the installer again.

If Windows opens the Microsoft Store instead of Python, disable the Python app
execution aliases in Windows Settings or install Python from python.org.

## Node.js or npm is not found

Install Node.js 20 LTS or newer with its default npm component. Close and
reopen PowerShell, then rerun the installer.

## Installation cannot download dependencies

Check the internet connection, proxy, antivirus, and firewall. Run the same
installer again after connectivity is restored; it reuses the existing local
environment and does not overwrite catalogue data.

## BOOKPILE says a port is occupied

Use **Stop BOOKPILE**, then try again. BOOKPILE uses local ports 5173 and 8000.
If another application owns either port, stop that application before
launching BOOKPILE.

## BOOKPILE does not become ready

Inspect the local logs under `.bookpile-runtime`. Stop BOOKPILE and start it
again. If dependencies or the frontend build are missing, rerun
`install-bookpile.ps1`.

## The phone cannot connect

- Confirm the phone and computer use the same private Wi-Fi.
- Use the exact address shown by Start BOOKPILE; `localhost` works only on the
  host computer.
- Allow Node.js through Windows Firewall on Private networks.
- Disable guest/client isolation on the Wi-Fi network if it prevents devices
  from seeing each other.
- A VPN may interfere with address detection or local routing.

## ISBN lookup appears slow

Catalogue matches are local and normally quick. Unknown ISBNs query external
providers and may take longer. Keep the lookup open while the progress message
is shown, or enter the book manually if providers are unavailable.

## Preserve data before deeper troubleshooting

If BOOKPILE still opens, download a full ZIP backup. If it does not, stop it
and copy the complete `backend\data` folder elsewhere before deleting,
reinstalling, or replacing any files. See
[BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md).
