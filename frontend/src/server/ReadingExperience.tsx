import { type FormEvent, useEffect, useState } from "react";
import { BookOpenCheck, ExternalLink, Pencil, Trash2, X } from "lucide-react";
import {
  type BookReading,
  type GoodreadsReview,
  type PersonalReadingState,
  type ReadingSession,
  type ServerBookSummary,
  ServerApiError,
  serverApi,
} from "./serverApi";

const READING_LABELS: Record<PersonalReadingState, string> = {
  PENDING: "Pending",
  READING: "Reading...",
  REREADING: "Re-reading...",
  READ: "Read",
};

function errorMessage(error: unknown): string {
  return error instanceof ServerApiError || error instanceof Error
    ? error.message
    : "BOOKPILE could not complete that request.";
}

function today(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function readableDate(value: string | null): string {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function sessionDescription(session: ReadingSession): string {
  if (session.dates_unknown) return "Reading dates unknown";
  if (session.state === "ACTIVE") return `Since ${readableDate(session.started_date)}`;
  return `${readableDate(session.started_date)} – ${readableDate(session.finished_date)}`;
}

export function ReadingStatusBadge({ reading, onClick }: {
  reading: BookReading | null | undefined;
  onClick: () => void;
  interactive?: boolean;
}) {
  if (!reading) return <span className="server-reading-status loading">Loading…</span>;
  const label = READING_LABELS[reading.state];
  const unavailable = reading.active_reader_present && (reading.state === "PENDING" || reading.state === "READ");
  return reading.writable
    ? <button type="button" disabled={unavailable} className={`server-reading-status ${reading.state.toLowerCase()}`} onClick={onClick} title={unavailable ? "This physical copy is currently being read" : "Update your reading status"}>{label}</button>
    : <span className={`server-reading-status ${reading.state.toLowerCase()}`} title="This reading perspective is read-only">{label}</span>;
}

export function ReadingSummary({ reading, perspectiveName }: {
  reading: BookReading;
  perspectiveName: string;
}) {
  return <section className="server-reading-summary">
    <div className="server-section-heading"><div><h3>Reading history</h3><p>{perspectiveName}'s personal reading record</p></div><span className={`server-reading-status ${reading.state.toLowerCase()}`}>{READING_LABELS[reading.state]}</span></div>
    {reading.sessions.length
      ? <ol>{reading.sessions.map((session, index) => <li key={session.id}><b>Reading {index + 1}</b><span>{sessionDescription(session)}</span></li>)}</ol>
      : <p className="server-field-help">No reading sessions recorded for this perspective.</p>}
  </section>;
}

export function GoodreadsSummary({ reviews }: { reviews: GoodreadsReview[] }) {
  if (!reviews.length) return null;
  return <section><h3>Goodreads reviews</h3><div className="server-goodreads-list">{reviews.map((review) => <a key={review.user_id} href={review.url} target="_blank" rel="noreferrer"><ExternalLink size={15} /> {review.username}'s review</a>)}</div></section>;
}

export function ReadingActionDialog({ libraryId, book, reading, onClose, onChanged }: {
  libraryId: string;
  book: ServerBookSummary;
  reading: BookReading;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const active = reading.sessions.find((session) => session.state === "ACTIVE");
  const finishing = reading.state === "READING" || reading.state === "REREADING";
  const rereading = reading.state === "READ";
  const [date, setDate] = useState(today());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const title = finishing ? (reading.state === "REREADING" ? "Finish re-reading?" : "Did you finish?") : rereading ? "Re-read this book?" : "Start reading?";

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (finishing && active) await serverApi.finishReading(libraryId, book.id, active.id, date);
      else await serverApi.startReading(libraryId, book.id, date);
      await onChanged(); onClose();
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function cancelActive() {
    if (!active || !window.confirm(`Cancel this active ${reading.state === "REREADING" ? "re-reading" : "reading"}? The active session will be permanently removed.`)) return;
    setBusy(true); setError("");
    try { await serverApi.cancelReading(libraryId, book.id, active.id); await onChanged(); onClose(); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className="server-modal-backdrop"><section className="server-catalogue-dialog server-reading-action-dialog" role="dialog" aria-modal="true">
    <button className="server-dialog-close" type="button" onClick={onClose} aria-label="Close"><X /></button>
    <p className="server-card-eyebrow">Personal reading</p><h2>{title}</h2>
    <p><b>{book.title}</b><br /><span className="server-book-author">{book.display_author}</span></p>
    {error && <div className="server-message error">{error}</div>}
    <form onSubmit={submit}><label>{finishing ? "Finished" : "Started"}<input type="date" required value={date} onChange={(event) => setDate(event.target.value)} /></label>
      <div className="server-dialog-actions">{finishing && <button className="danger" type="button" disabled={busy} onClick={() => void cancelActive()}>Cancel reading</button>}<button type="button" onClick={onClose} disabled={busy}>Back</button><button className="confirm" type="submit" disabled={busy}>{busy ? "Saving…" : "Confirm"}</button></div>
    </form>
  </section></div>;
}

type HistoricalDraft = { id: string | null; started_date: string; finished_date: string; dates_unknown: boolean };
const EMPTY_HISTORY: HistoricalDraft = { id: null, started_date: "", finished_date: "", dates_unknown: false };

export function ReadingManager({ libraryId, book, onClose, onChanged }: {
  libraryId: string;
  book: ServerBookSummary;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [reading, setReading] = useState<BookReading | null>(null);
  const [reviews, setReviews] = useState<GoodreadsReview[]>([]);
  const [reviewUrl, setReviewUrl] = useState("");
  const [draft, setDraft] = useState<HistoricalDraft>(EMPTY_HISTORY);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    const [nextReading, nextReviews] = await Promise.all([
      serverApi.bookReading(libraryId, book.id),
      serverApi.goodreadsReviews(libraryId, book.id),
    ]);
    setReading(nextReading); setReviews(nextReviews);
    setReviewUrl(nextReviews.find((review) => review.user_id === nextReading.perspective_user_id)?.url ?? "");
  }

  useEffect(() => {
    setBusy(true); load().catch((caught) => setError(errorMessage(caught))).finally(() => setBusy(false));
  // The selected self perspective is resolved by the API when the query value is empty.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [libraryId, book.id]);

  async function saveHistory(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    const payload = { started_date: draft.dates_unknown ? null : draft.started_date || null, finished_date: draft.dates_unknown ? null : draft.finished_date || null, dates_unknown: draft.dates_unknown };
    try {
      if (draft.id) await serverApi.updateHistoricalReading(libraryId, book.id, draft.id, payload);
      else await serverApi.addHistoricalReading(libraryId, book.id, payload);
      setDraft(EMPTY_HISTORY); await load(); await onChanged();
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function remove(session: ReadingSession) {
    if (!window.confirm(`Permanently delete this reading (${sessionDescription(session)})? This cannot be undone.`)) return;
    setBusy(true); setError("");
    try { await serverApi.deleteHistoricalReading(libraryId, book.id, session.id); setDraft(EMPTY_HISTORY); await load(); await onChanged(); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function saveGoodreads(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await serverApi.setMyGoodreadsReview(libraryId, book.id, reviewUrl.trim() || null); await load(); await onChanged(); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className="server-modal-backdrop"><section className="server-catalogue-dialog server-reading-manager" role="dialog" aria-modal="true">
    <button className="server-dialog-close" type="button" onClick={onClose} aria-label="Close"><X /></button>
    <p className="server-card-eyebrow">My personal data</p><h2>My reading</h2><p><b>{book.title}</b> — {book.display_author}</p>
    {error && <div className="server-message error">{error}</div>}
    {busy && !reading ? <p>Loading your reading record…</p> : reading && <>
      <section><div className="server-section-heading"><h3>Reading history</h3><span className={`server-reading-status ${reading.state.toLowerCase()}`}>{READING_LABELS[reading.state]}</span></div>
        {reading.sessions.length ? <ol className="server-reading-manager-list">{reading.sessions.map((session, index) => <li key={session.id}><span><b>Reading {index + 1}</b><small>{sessionDescription(session)}</small></span>{session.state === "COMPLETED" && <span><button type="button" onClick={() => setDraft({ id: session.id, started_date: session.started_date ?? "", finished_date: session.finished_date ?? "", dates_unknown: session.dates_unknown })}><Pencil size={15} /> Edit</button><button type="button" onClick={() => void remove(session)}><Trash2 size={15} /> Delete</button></span>}</li>)}</ol> : <p className="server-field-help">No readings recorded yet.</p>}
      </section>
      <form className="server-personal-reading-form" onSubmit={saveHistory}><fieldset><legend>{draft.id ? "Edit historical reading" : "Add historical reading"}</legend>
        <label className="server-compact-check"><input type="checkbox" checked={draft.dates_unknown} onChange={(event) => setDraft({ ...draft, dates_unknown: event.target.checked, started_date: event.target.checked ? "" : draft.started_date, finished_date: event.target.checked ? "" : draft.finished_date })} /> Reading dates unknown</label>
        {!draft.dates_unknown && <div><label>Started<input type="date" required value={draft.started_date} onChange={(event) => setDraft({ ...draft, started_date: event.target.value })} /></label><label>Finished<input type="date" required value={draft.finished_date} onChange={(event) => setDraft({ ...draft, finished_date: event.target.value })} /></label></div>}
        <span className="server-form-actions">{draft.id && <button type="button" onClick={() => setDraft(EMPTY_HISTORY)}>Cancel edit</button>}<button className="confirm" type="submit" disabled={busy}>{draft.id ? "Save reading" : "Add reading"}</button></span>
      </fieldset></form>
      <form className="server-personal-reading-form" onSubmit={saveGoodreads}><fieldset><legend>My Goodreads review</legend><label>Review URL<input type="url" placeholder="https://www.goodreads.com/review/show/..." value={reviewUrl} onChange={(event) => setReviewUrl(event.target.value)} /></label><p className="server-field-help">Leave this empty to remove your saved review link.</p><span className="server-form-actions"><button className="confirm" type="submit" disabled={busy}>Save Goodreads link</button></span></fieldset></form>
      {!!reviews.filter((review) => review.user_id !== reading.perspective_user_id).length && <GoodreadsSummary reviews={reviews.filter((review) => review.user_id !== reading.perspective_user_id)} />}
    </>}
    <div className="server-dialog-actions"><button type="button" onClick={onClose}><BookOpenCheck size={16} /> Close</button></div>
  </section></div>;
}
