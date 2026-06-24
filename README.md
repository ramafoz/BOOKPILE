# BOOKPILE

A local-first personal library manager for cataloguing books and finding their
exact physical location.

## Version 1

- Create, edit, delete, search, and filter books.
- Track `PENDING`, `CURRENTLY_READING`, and `READ` status.
- Show total, pending, currently-reading, and read counts.
- Model the library as `Bookcase → Shelf → Container → Book`.
- Locate a book by bookcase, shelf, layer, row/pile, container number, and
  position.
- Inspect and safely delete shelves and containers without deleting books.
- Reorganize books quickly, swapping positions when the destination is occupied.
- Record optional acquisition, reading-started, and finished-reading dates,
  including read books whose exact reading date is unknown.
- Preserve the original collection as historical books with unknown acquisition
  dates.
- Add, replace, and remove optimized cover photos from desktop or mobile.
- Download a verified ZIP backup containing SQLite, covers, manifest, and
  checksums.
- Export all books, dates, and physical locations as an Excel-friendly CSV.
- Inspect and restore validated BOOKPILE backups with an automatic pre-restore
  safety backup and rollback protection.
- Add books rapidly in batches while retaining the physical container and
  advancing positions upward or downward.
- Sort by title, author, physical position, or lifecycle dates and filter by
  date ranges and physical location.
- Insert a new book into an occupied container position by shifting the
  contiguous books one place after explicit confirmation.
- Browse a read-only visual library index with exploded background/foreground
  layers and click-through catalogue filters.

## Stack

- Backend: FastAPI + SQLite
- Frontend: React + Vite + TypeScript

## Run locally

### One-command start

From the project root:

```powershell
.\start-bookpile.ps1
```

This builds the optimized frontend when necessary, opens the backend and
frontend in separate PowerShell windows, and prints the single LAN URL to use
from the computer or another device on the same Wi-Fi. Keep both windows open
while using BOOKPILE.

### Desktop shortcuts

Install the shortcuts once:

```powershell
.\install-desktop-shortcuts.ps1
```

After that:

- Double-click **Start BOOKPILE** to start both servers invisibly. A confirmation
  displays the mobile URL and copies it to the clipboard.
- Double-click **Stop BOOKPILE** to stop only the BOOKPILE processes.
- Runtime logs are stored locally in `.bookpile-runtime/`.

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API runs at <http://localhost:8000> and its interactive documentation at
<http://localhost:8000/docs>.

### Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

## Use from a phone on the same Wi-Fi

Run `.\start-bookpile.ps1`, then open the displayed LAN URL on the phone, for
example:

```text
http://192.168.1.50:5173
```

The optimized frontend proxies API requests to FastAPI on the host computer, so
no mobile configuration is required. Vite development mode is not used for this
launcher, which substantially reduces the number of files transferred to the
phone. Windows may ask once whether Node.js may communicate on private
networks; allow access for **private networks only**.

## Data

SQLite data is stored in `backend/data/bookpile.db` and is intentionally
excluded from Git. Back up that file to preserve your catalogue.

## Roadmap

1. Random and oldest-pending reading suggestions.
2. Acquisition and reading dates.
3. Visual shelf representation.
4. Goodreads metadata.
5. Cover images.
6. OCR/camera recognition.
