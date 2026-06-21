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

## Stack

- Backend: FastAPI + SQLite
- Frontend: React + Vite + TypeScript

## Run locally

### One-command start

From the project root:

```powershell
.\start-bookpile.ps1
```

This opens the backend and frontend in separate PowerShell windows and prints
both the desktop URL and the URL to use from another device on the same Wi-Fi.
Keep both windows open while using BOOKPILE.

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

The frontend proxies API requests to FastAPI on the host computer, so no mobile
configuration is required. Windows may ask once whether Node.js or Python may
communicate on private networks; allow access for **private networks only**.

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
