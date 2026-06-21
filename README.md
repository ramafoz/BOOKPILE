# BOOKPILE

A local-first personal library manager for cataloguing books and finding their
exact physical location.

## Version 1

- Create, edit, delete, search, and filter books.
- Track `PENDING` and `READ` status.
- Show total, pending, and read counts.
- Model the library as `Bookcase → Shelf → Container → Book`.
- Locate a book by bookcase, shelf, layer, row/pile, container number, and
  position.

## Stack

- Backend: FastAPI + SQLite
- Frontend: React + Vite + TypeScript

## Run locally

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
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

