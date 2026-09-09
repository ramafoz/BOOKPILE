import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, BarChart3, BookCheck, BookOpen, Clock3, Gauge, Handshake, Repeat2 } from "lucide-react";
import {
  serverApi,
  type CatalogueMetadataOptions,
  type ReadingPerspective,
  type ReadingStatistics,
  type LoanStatistics,
} from "./serverApi";

const EMPTY_OPTIONS: CatalogueMetadataOptions = {
  languages: [], original_languages: [], publishers: [], genres: [], series_names: [], contributor_roles: [],
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Statistics could not be loaded.";
}

function DurationCard({ title, value }: { title: string; value: ReadingStatistics["pending_duration"] }) {
  return <article className="server-statistics-duration"><Clock3 /><div><span>{title}</span><b>{value.average_days === null ? "—" : `${value.average_days.toFixed(1)} days`}</b><small>{value.median_days === null ? "No usable dates" : `Median ${value.median_days.toFixed(1)} · ${value.sample_size} measured · ${value.excluded} excluded`}</small></div></article>;
}

export default function StatisticsWorkspace({ libraryId, perspective }: {
  libraryId: string;
  perspective: ReadingPerspective;
}) {
  const [statistics, setStatistics] = useState<ReadingStatistics | null>(null);
  const [loanStatistics, setLoanStatistics] = useState<LoanStatistics | null>(null);
  const [options, setOptions] = useState(EMPTY_OPTIONS);
  const [filters, setFilters] = useState<{ language?: string; genre?: string; publisher?: string; reading_year?: number }>({});
  const [draft, setDraft] = useState(filters);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

  const load = useCallback(async (next = filters) => {
    setBusy(true); setError("");
    try {
      const [reading, loans] = await Promise.all([
        serverApi.readingStatistics(libraryId, perspective.user_id, next),
        serverApi.loanStatistics(libraryId, { language: next.language, genre: next.genre, publisher: next.publisher, loan_year: next.reading_year }),
      ]);
      setStatistics(reading); setLoanStatistics(loans);
    }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }, [filters, libraryId, perspective.user_id]);

  useEffect(() => {
    setFilters({}); setDraft({});
    void Promise.all([
      serverApi.readingStatistics(libraryId, perspective.user_id),
      serverApi.loanStatistics(libraryId),
      serverApi.catalogueOptions(libraryId),
    ]).then(([result, loans, metadata]) => { setStatistics(result); setLoanStatistics(loans); setOptions(metadata); setError(""); })
      .catch((caught) => setError(errorMessage(caught))).finally(() => setBusy(false));
  }, [libraryId, perspective.user_id]);

  function apply(event: React.FormEvent) {
    event.preventDefault(); setFilters(draft); void load(draft);
  }

  return <section className={`server-statistics-workspace ${busy ? "loading" : ""}`}>
    <header><div><p className="server-card-eyebrow">Personal reading perspective</p><h2>{perspective.username}'s statistics</h2><p>Reading events are personal; catalogue ownership remains shared.</p></div><BarChart3 size={42} /></header>
    {error && <div className="server-message error">{error}</div>}
    <form className="server-statistics-filters" onSubmit={apply}>
      <label>Language<select value={draft.language ?? ""} onChange={(event) => setDraft({ ...draft, language: event.target.value || undefined })}><option value="">All languages</option>{options.languages.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Genre<select value={draft.genre ?? ""} onChange={(event) => setDraft({ ...draft, genre: event.target.value || undefined })}><option value="">All genres</option>{options.genres.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Publisher<select value={draft.publisher ?? ""} onChange={(event) => setDraft({ ...draft, publisher: event.target.value || undefined })}><option value="">All publishers</option>{options.publishers.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Finished in year<input type="number" min="1000" max="9999" value={draft.reading_year ?? ""} onChange={(event) => setDraft({ ...draft, reading_year: event.target.value ? Number(event.target.value) : undefined })} placeholder="All years" /></label>
      <button type="button" onClick={() => { setDraft({}); setFilters({}); void load({}); }}>Clear</button><button type="submit">Apply</button>
    </form>
    {statistics && <>
      <div className="server-statistics-cards">
        <article><BookCheck /><b>{statistics.unique_books_read}</b><span>Unique books read</span></article>
        <article><BookOpen /><b>{statistics.completed_readings}</b><span>Reading events <small>{statistics.dated_readings} dated</small></span></article>
        <article><Repeat2 /><b>{statistics.rereadings}</b><span>Rereadings</span></article>
        <article><Gauge /><b>{statistics.average_pages_per_day === null ? "—" : statistics.average_pages_per_day.toFixed(1)}</b><span>Average pages/day</span></article>
      </div>
      <div className="server-statistics-duration-grid">
        <DurationCard title="Time spent pending" value={statistics.pending_duration} />
        <DurationCard title="Reading duration" value={statistics.reading_duration} />
      </div>
      <section className="server-statistics-rate"><h3>Reading pace</h3><div>
        <span><b>{statistics.pages_read}</b> pages read</span>
        <span><b>{statistics.pages_per_week === null ? "—" : statistics.pages_per_week.toFixed(1)}</b> pages/week</span>
        <span><b>{statistics.pages_per_month === null ? "—" : statistics.pages_per_month.toFixed(1)}</b> pages/month</span>
        <span><b>{statistics.median_pages_per_day === null ? "—" : statistics.median_pages_per_day.toFixed(1)}</b> median pages/day per book</span>
      </div></section>
      <div className="server-statistics-tables">
        <section><h3>Reading by year</h3>{statistics.years.length ? <table><thead><tr><th>Year</th><th>Books</th><th>Readings</th><th>Pages</th></tr></thead><tbody>{statistics.years.map((item) => <tr key={item.year}><td>{item.year}</td><td>{item.books_read}</td><td>{item.reading_events}</td><td>{item.pages_read}</td></tr>)}</tbody></table> : <p>No dated readings match these filters.</p>}</section>
        <section className="server-statistics-book-list"><h3>Books in this result</h3>{statistics.books.length ? <table><thead><tr><th>Book</th><th>Readings</th><th>Pages</th><th>Pages/day</th></tr></thead><tbody>{statistics.books.map((item) => <tr key={item.book_id}><td><b>{item.title}</b><small>{item.author}</small></td><td>{item.reading_events}</td><td>{item.pages_read || "—"}</td><td>{item.average_pages_per_day === null ? "—" : item.average_pages_per_day.toFixed(1)}</td></tr>)}</tbody></table> : <p>No completed readings match these filters.</p>}</section>
      </div>
      <p className="server-statistics-note">Unknown-date historical readings count as personal history, but cannot be assigned to dated page or rate statistics. Missing page counts contribute no pages.</p>
    </>}
    {loanStatistics && <section className="server-loan-statistics">
      <header><div><p className="server-card-eyebrow">Shared physical custody</p><h3>Loan statistics</h3><p>These totals belong to the library and do not change with reading perspective.</p></div><Handshake size={34} /></header>
      <div className="server-statistics-cards">
        <article><Handshake /><b>{loanStatistics.active}</b><span>Currently on loan</span></article>
        <article><AlertTriangle /><b>{loanStatistics.overdue}</b><span>Overdue</span></article>
        <article><BookCheck /><b>{loanStatistics.completed}</b><span>Returned loans</span></article>
        <article><Clock3 /><b>{loanStatistics.unknown_loan_dates + loanStatistics.unknown_return_dates}</b><span>Unknown dates <small>{loanStatistics.unknown_loan_dates} loaned · {loanStatistics.unknown_return_dates} returned</small></span></article>
      </div>
      <div className="server-statistics-tables">
        <section><h3>Loans by year</h3>{loanStatistics.years.length ? <table><thead><tr><th>Year</th><th>Loaned</th><th>Returned</th></tr></thead><tbody>{loanStatistics.years.map((item) => <tr key={item.year}><td>{item.year}</td><td>{item.loans}</td><td>{item.returns}</td></tr>)}</tbody></table> : <p>No dated loans match these filters.</p>}</section>
        <section className="server-statistics-book-list"><h3>Most loaned books</h3>{loanStatistics.books.length ? <table><thead><tr><th>Book</th><th>Loans</th></tr></thead><tbody>{loanStatistics.books.map((item) => <tr key={item.book_id}><td><b>{item.title}</b><small>{item.author}</small></td><td>{item.loans}</td></tr>)}</tbody></table> : <p>No loans match these filters.</p>}</section>
      </div>
    </section>}
  </section>;
}
