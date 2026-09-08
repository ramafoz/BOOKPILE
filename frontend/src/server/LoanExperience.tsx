import { type FormEvent, useCallback, useEffect, useState } from "react";
import { CalendarClock, Handshake, RotateCcw, Trash2, X } from "lucide-react";
import { serverApi, type BookLoans, type LoanRecord, type LoanWrite, type ServerBookSummary } from "./serverApi";

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Loan data could not be loaded.";
}

function dateLabel(value: string | null) {
  return value || "Unknown";
}

export function LoanSummary({ loans }: { loans: BookLoans | null }) {
  if (!loans?.loans.length) return null;
  const active = loans.loans.find((item) => item.state === "ACTIVE");
  return <section className="server-loan-summary"><h3>Loan history</h3>
    {active && <p className={active.overdue ? "overdue" : ""}><Handshake size={16} /><b>{active.loaned_to ? `On loan to ${active.loaned_to}` : "On loan"}</b>{active.loaned_date && ` since ${active.loaned_date}`}{active.expected_return_date && ` · expected ${active.expected_return_date}`}{active.overdue && " · overdue"}</p>}
    <ul>{loans.loans.filter((item) => item.state === "RETURNED").map((item) => <li key={item.id}>Loaned {dateLabel(item.loaned_date)} · returned {dateLabel(item.returned_date)}{item.loaned_to ? ` · ${item.loaned_to}` : ""}</li>)}</ul>
  </section>;
}

const EMPTY: LoanWrite & { returned_date: string | null } = {
  loaned_to: "", notes: null, loaned_date: null, expected_return_date: null, returned_date: null,
};

export default function LoanManager({ libraryId, book, onClose, onChanged }: {
  libraryId: string;
  book: ServerBookSummary;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [data, setData] = useState<BookLoans | null>(null);
  const [activeDraft, setActiveDraft] = useState(EMPTY);
  const [historyDraft, setHistoryDraft] = useState(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [returnDate, setReturnDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => setData(await serverApi.bookLoans(libraryId, book.id)), [book.id, libraryId]);
  useEffect(() => { void load().catch((caught) => setError(errorMessage(caught))); }, [load]);
  const active = data?.loans.find((item) => item.state === "ACTIVE");
  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await action(); await load(); await onChanged(); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }
  async function saveActive(event: FormEvent) {
    event.preventDefault();
    const payload: LoanWrite = {
      loaned_to: activeDraft.loaned_to,
      notes: activeDraft.notes,
      loaned_date: activeDraft.loaned_date,
      expected_return_date: activeDraft.expected_return_date,
    };
    await run(() => serverApi.startLoan(libraryId, book.id, payload));
    setActiveDraft(EMPTY);
  }
  async function saveHistory(event: FormEvent) {
    event.preventDefault();
    const action = editingId
      ? () => serverApi.updateHistoricalLoan(libraryId, book.id, editingId, historyDraft)
      : () => serverApi.addHistoricalLoan(libraryId, book.id, historyDraft);
    await run(action); setHistoryDraft(EMPTY); setEditingId(null);
  }
  function edit(item: LoanRecord) {
    setEditingId(item.id); setHistoryDraft({
      loaned_to: item.loaned_to ?? "", notes: item.notes ?? null,
      loaned_date: item.loaned_date, expected_return_date: item.expected_return_date,
      returned_date: item.returned_date,
    });
  }
  function fields(value: typeof EMPTY, update: (next: typeof EMPTY) => void) {
    return <div className="server-form-grid">
      <label>Loaned to *<input required maxLength={300} value={value.loaned_to} onChange={(e) => update({ ...value, loaned_to: e.target.value })} /></label>
      <label>Loan date <small>optional / unknown</small><input type="date" value={value.loaned_date ?? ""} onChange={(e) => update({ ...value, loaned_date: e.target.value || null })} /></label>
      <label>Expected return <small>optional</small><input type="date" value={value.expected_return_date ?? ""} onChange={(e) => update({ ...value, expected_return_date: e.target.value || null })} /></label>
      <label className="wide">Private Owner notes<textarea rows={2} maxLength={4000} value={value.notes ?? ""} onChange={(e) => update({ ...value, notes: e.target.value || null })} /></label>
    </div>;
  }
  return <div className="server-modal-backdrop"><section className="server-catalogue-dialog server-loan-manager" role="dialog" aria-modal="true">
    <button className="server-dialog-close" onClick={onClose} aria-label="Close"><X /></button>
    <p className="server-card-eyebrow">Shared physical custody</p><h2>Loans</h2><p><b>{book.title}</b> — {book.display_author}</p>
    {error && <div className="server-message error">{error}</div>}
    {active ? <fieldset><legend>Current loan</legend><LoanSummary loans={data} /><div className="server-form-grid"><label>Returned date <small>leave blank if unknown</small><input type="date" value={returnDate} onChange={(e) => setReturnDate(e.target.value)} /></label></div><div className="server-form-actions"><button disabled={busy} onClick={() => { if (window.confirm("Cancel this loan without retaining it in history?")) void run(() => serverApi.cancelLoan(libraryId, book.id)); }}><Trash2 size={15} /> Cancel loan</button><button className="confirm" disabled={busy} onClick={() => void run(() => serverApi.returnLoan(libraryId, book.id, returnDate || null))}><RotateCcw size={15} /> Return book</button></div></fieldset>
      : <form onSubmit={saveActive}><fieldset><legend>Loan this book</legend>{fields(activeDraft, setActiveDraft)}<div className="server-form-actions"><button className="confirm" disabled={busy}><Handshake size={15} /> Start loan</button></div></fieldset></form>}
    <form onSubmit={saveHistory}><fieldset><legend>{editingId ? "Correct historical loan" : "Add historical loan"}</legend>{fields(historyDraft, setHistoryDraft)}<label>Returned date <small>optional / unknown</small><input type="date" value={historyDraft.returned_date ?? ""} onChange={(e) => setHistoryDraft({ ...historyDraft, returned_date: e.target.value || null })} /></label><div className="server-form-actions">{editingId && <button type="button" onClick={() => { setEditingId(null); setHistoryDraft(EMPTY); }}>Cancel edit</button>}<button className="confirm" disabled={busy}><CalendarClock size={15} /> {editingId ? "Save correction" : "Add history"}</button></div></fieldset></form>
    {!!data?.loans.filter((item) => item.state === "RETURNED").length && <fieldset><legend>Returned loans</legend><div className="server-loan-history">{data.loans.filter((item) => item.state === "RETURNED").map((item) => <article key={item.id}><span><b>{item.loaned_to}</b><small>{dateLabel(item.loaned_date)} → {dateLabel(item.returned_date)}</small></span><button type="button" onClick={() => edit(item)}>Edit</button><button type="button" aria-label="Delete historical loan" onClick={() => { if (window.confirm("Permanently delete this historical loan?")) void run(() => serverApi.deleteHistoricalLoan(libraryId, book.id, item.id)); }}><Trash2 size={15} /></button></article>)}</div></fieldset>}
    <div className="server-dialog-actions"><button onClick={onClose}>Close</button></div>
  </section></div>;
}
