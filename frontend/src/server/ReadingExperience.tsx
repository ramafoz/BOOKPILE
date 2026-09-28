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
import type { AppLocale } from "./locale";
import { readingCopy, type ReadingCopy } from "./readingCopy";

function readingLabels(copy: ReadingCopy): Record<PersonalReadingState, string> {
  return { PENDING: copy("pending"), READING: copy("reading"), REREADING: copy("rereading"), READ: copy("read") };
}

function errorMessage(error: unknown, copy: ReadingCopy): string {
  return error instanceof ServerApiError || error instanceof Error
    ? error.message
    : copy("requestFailed");
}

function today(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function readableDate(value: string | null, locale: AppLocale, copy: ReadingCopy): string {
  if (!value) return copy("unknown");
  return new Intl.DateTimeFormat(locale === "gl" ? "gl-ES" : "en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function sessionDescription(session: ReadingSession, locale: AppLocale, copy: ReadingCopy): string {
  if (session.dates_unknown) return copy("datesUnknown");
  if (session.state === "ACTIVE") return copy("since", { date: readableDate(session.started_date, locale, copy) });
  return copy("dateRange", { start: readableDate(session.started_date, locale, copy), finish: readableDate(session.finished_date, locale, copy) });
}

export function ReadingStatusBadge({ reading, onClick, locale }: {
  reading: BookReading | null | undefined;
  onClick: () => void;
  locale: AppLocale;
  interactive?: boolean;
}) {
  const copy = readingCopy(locale);
  if (!reading) return <span className="server-reading-status loading">{copy("loading")}</span>;
  const label = readingLabels(copy)[reading.state];
  const unavailable = reading.active_reader_present && (reading.state === "PENDING" || reading.state === "READ");
  return reading.writable
    ? <button type="button" disabled={unavailable} className={`server-reading-status ${reading.state.toLowerCase()}`} onClick={onClick} title={unavailable ? copy("copyBeingRead") : copy("updateStatus")}>{label}</button>
    : <span className={`server-reading-status ${reading.state.toLowerCase()}`} title={copy("readOnly")}>{label}</span>;
}

export function ReadingSummary({ reading, perspectiveName, locale }: {
  reading: BookReading;
  perspectiveName: string;
  locale: AppLocale;
}) {
  const copy = readingCopy(locale);
  return <section className="server-reading-summary">
    <div className="server-section-heading"><div><h3>{copy("history")}</h3><p>{copy("personalRecord", { name: perspectiveName })}</p></div><span className={`server-reading-status ${reading.state.toLowerCase()}`}>{readingLabels(copy)[reading.state]}</span></div>
    {reading.sessions.length
      ? <ol>{reading.sessions.map((session, index) => <li key={session.id}><b>{copy("readingNumber", { number: index + 1 })}</b><span>{sessionDescription(session, locale, copy)}</span></li>)}</ol>
      : <p className="server-field-help">{copy("noSessions")}</p>}
  </section>;
}

export function GoodreadsSummary({ reviews, locale }: { reviews: GoodreadsReview[]; locale: AppLocale }) {
  const copy = readingCopy(locale);
  if (!reviews.length) return null;
  return <section><h3>{copy("goodreadsReviews")}</h3><div className="server-goodreads-list">{reviews.map((review) => <a key={review.user_id} href={review.url} target="_blank" rel="noreferrer"><ExternalLink size={15} /> {copy("usersReview", { username: review.username })}</a>)}</div></section>;
}

export function ReadingActionDialog({ libraryId, book, reading, locale, onClose, onChanged }: {
  libraryId: string;
  book: ServerBookSummary;
  reading: BookReading;
  locale: AppLocale;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const copy = readingCopy(locale);
  const active = reading.sessions.find((session) => session.state === "ACTIVE");
  const finishing = reading.state === "READING" || reading.state === "REREADING";
  const rereading = reading.state === "READ";
  const [date, setDate] = useState(today());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const title = finishing ? (reading.state === "REREADING" ? copy("finishRereading") : copy("didYouFinish")) : rereading ? copy("rereadBook") : copy("startReading");

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (finishing && active) await serverApi.finishReading(libraryId, book.id, active.id, date);
      else await serverApi.startReading(libraryId, book.id, date);
      await onChanged(); onClose();
    } catch (caught) { setError(errorMessage(caught, copy)); }
    finally { setBusy(false); }
  }

  async function cancelActive() {
    if (!active || !window.confirm(copy("cancelActive", { kind: reading.state === "REREADING" ? copy("kindRereading") : copy("kindReading") }))) return;
    setBusy(true); setError("");
    try { await serverApi.cancelReading(libraryId, book.id, active.id); await onChanged(); onClose(); }
    catch (caught) { setError(errorMessage(caught, copy)); }
    finally { setBusy(false); }
  }

  return <div className="server-modal-backdrop"><section className="server-catalogue-dialog server-reading-action-dialog" role="dialog" aria-modal="true">
    <button className="server-dialog-close" type="button" onClick={onClose} aria-label={copy("close")}><X /></button>
    <p className="server-card-eyebrow">{copy("personalReading")}</p><h2>{title}</h2>
    <p><b>{book.title}</b><br /><span className="server-book-author">{book.display_author}</span></p>
    {error && <div className="server-message error">{error}</div>}
    <form onSubmit={submit}><label>{finishing ? copy("finished") : copy("started")}<input type="date" required value={date} onChange={(event) => setDate(event.target.value)} /></label>
      <div className="server-dialog-actions">{finishing && <button className="danger" type="button" disabled={busy} onClick={() => void cancelActive()}>{copy("cancelReading")}</button>}<button type="button" onClick={onClose} disabled={busy}>{copy("back")}</button><button className="confirm" type="submit" disabled={busy}>{busy ? copy("saving") : copy("confirm")}</button></div>
    </form>
  </section></div>;
}

type HistoricalDraft = { id: string | null; started_date: string; finished_date: string; dates_unknown: boolean };
const EMPTY_HISTORY: HistoricalDraft = { id: null, started_date: "", finished_date: "", dates_unknown: false };

export function ReadingManager({ libraryId, book, locale, onClose, onChanged }: {
  libraryId: string;
  book: ServerBookSummary;
  locale: AppLocale;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const copy = readingCopy(locale);
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
    setBusy(true); load().catch((caught) => setError(errorMessage(caught, copy))).finally(() => setBusy(false));
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
    } catch (caught) { setError(errorMessage(caught, copy)); }
    finally { setBusy(false); }
  }

  async function remove(session: ReadingSession) {
    if (!window.confirm(copy("permanentDelete", { description: sessionDescription(session, locale, copy) }))) return;
    setBusy(true); setError("");
    try { await serverApi.deleteHistoricalReading(libraryId, book.id, session.id); setDraft(EMPTY_HISTORY); await load(); await onChanged(); }
    catch (caught) { setError(errorMessage(caught, copy)); }
    finally { setBusy(false); }
  }

  async function saveGoodreads(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await serverApi.setMyGoodreadsReview(libraryId, book.id, reviewUrl.trim() || null); await load(); await onChanged(); }
    catch (caught) { setError(errorMessage(caught, copy)); }
    finally { setBusy(false); }
  }

  return <div className="server-modal-backdrop"><section className="server-catalogue-dialog server-reading-manager" role="dialog" aria-modal="true">
    <button className="server-dialog-close" type="button" onClick={onClose} aria-label={copy("close")}><X /></button>
    <p className="server-card-eyebrow">{copy("myPersonalData")}</p><h2>{copy("myReading")}</h2><p><b>{book.title}</b> — {book.display_author}</p>
    {error && <div className="server-message error">{error}</div>}
    {busy && !reading ? <p>{copy("loadingRecord")}</p> : reading && <>
      <section><div className="server-section-heading"><h3>{copy("history")}</h3><span className={`server-reading-status ${reading.state.toLowerCase()}`}>{readingLabels(copy)[reading.state]}</span></div>
        {reading.sessions.length ? <ol className="server-reading-manager-list">{reading.sessions.map((session, index) => <li key={session.id}><span><b>{copy("readingNumber", { number: index + 1 })}</b><small>{sessionDescription(session, locale, copy)}</small></span>{session.state === "COMPLETED" && <span><button type="button" onClick={() => setDraft({ id: session.id, started_date: session.started_date ?? "", finished_date: session.finished_date ?? "", dates_unknown: session.dates_unknown })}><Pencil size={15} /> {copy("edit")}</button><button type="button" onClick={() => void remove(session)}><Trash2 size={15} /> {copy("delete")}</button></span>}</li>)}</ol> : <p className="server-field-help">{copy("noReadings")}</p>}
      </section>
      <form className="server-personal-reading-form" onSubmit={saveHistory}><fieldset><legend>{draft.id ? copy("editHistorical") : copy("addHistorical")}</legend>
        <label className="server-compact-check"><input type="checkbox" checked={draft.dates_unknown} onChange={(event) => setDraft({ ...draft, dates_unknown: event.target.checked, started_date: event.target.checked ? "" : draft.started_date, finished_date: event.target.checked ? "" : draft.finished_date })} /> {copy("datesUnknown")}</label>
        {!draft.dates_unknown && <div><label>{copy("started")}<input type="date" required value={draft.started_date} onChange={(event) => setDraft({ ...draft, started_date: event.target.value })} /></label><label>{copy("finished")}<input type="date" required value={draft.finished_date} onChange={(event) => setDraft({ ...draft, finished_date: event.target.value })} /></label></div>}
        <span className="server-form-actions">{draft.id && <button type="button" onClick={() => setDraft(EMPTY_HISTORY)}>{copy("cancelEdit")}</button>}<button className="confirm" type="submit" disabled={busy}>{draft.id ? copy("saveReading") : copy("addReading")}</button></span>
      </fieldset></form>
      <form className="server-personal-reading-form" onSubmit={saveGoodreads}><fieldset><legend>{copy("myGoodreadsReview")}</legend><label>{copy("reviewUrl")}<input type="url" placeholder="https://www.goodreads.com/review/show/..." value={reviewUrl} onChange={(event) => setReviewUrl(event.target.value)} /></label><p className="server-field-help">{copy("removeReviewHelp")}</p><span className="server-form-actions"><button className="confirm" type="submit" disabled={busy}>{copy("saveGoodreads")}</button></span></fieldset></form>
      {!!reviews.filter((review) => review.user_id !== reading.perspective_user_id).length && <GoodreadsSummary reviews={reviews.filter((review) => review.user_id !== reading.perspective_user_id)} locale={locale} />}
    </>}
    <div className="server-dialog-actions"><button type="button" onClick={onClose}><BookOpenCheck size={16} /> {copy("close")}</button></div>
  </section></div>;
}
