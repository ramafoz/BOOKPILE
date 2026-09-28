import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, BarChart3, BookCheck, BookOpen, Clock3, Gauge, Handshake, Repeat2 } from "lucide-react";
import {
  serverApi,
  type CatalogueMetadataOptions,
  type ReadingPerspective,
  type ReadingStatistics,
  type LoanStatistics,
} from "./serverApi";
import type { AppLocale } from "./locale";
import { type StatisticsCopy, statisticsCopy } from "./statisticsCopy";

const EMPTY_OPTIONS: CatalogueMetadataOptions = {
  languages: [], original_languages: [], publishers: [], genres: [], series_names: [], contributor_roles: [],
};

function errorMessage(copy: StatisticsCopy): string {
  return copy("loadFailed");
}

function DurationCard({ title, value, copy }: { title: string; value: ReadingStatistics["pending_duration"]; copy: StatisticsCopy }) {
  return <article className="server-statistics-duration"><Clock3 /><div><span>{title}</span><b>{value.average_days === null ? "—" : copy("days", { count: value.average_days.toFixed(1) })}</b><small>{value.median_days === null ? copy("noUsableDates") : copy("durationSummary", { median: value.median_days.toFixed(1), measured: value.sample_size, excluded: value.excluded })}</small></div></article>;
}

export default function StatisticsWorkspace({ libraryId, perspective, locale }: {
  libraryId: string;
  perspective: ReadingPerspective;
  locale: AppLocale;
}) {
  const copy = useMemo(() => statisticsCopy(locale), [locale]);
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
    catch { setError(errorMessage(copy)); }
    finally { setBusy(false); }
  }, [copy, filters, libraryId, perspective.user_id]);

  useEffect(() => {
    setFilters({}); setDraft({});
    void Promise.all([
      serverApi.readingStatistics(libraryId, perspective.user_id),
      serverApi.loanStatistics(libraryId),
      serverApi.catalogueOptions(libraryId),
    ]).then(([result, loans, metadata]) => { setStatistics(result); setLoanStatistics(loans); setOptions(metadata); setError(""); })
      .catch(() => setError(errorMessage(copy))).finally(() => setBusy(false));
  }, [copy, libraryId, perspective.user_id]);

  function apply(event: React.FormEvent) {
    event.preventDefault(); setFilters(draft); void load(draft);
  }

  return <section className={`server-statistics-workspace ${busy ? "loading" : ""}`}>
    <header><div><p className="server-card-eyebrow">{copy("personalPerspective")}</p><h2>{copy("usersStatistics", { username: perspective.username })}</h2><p>{copy("personalReadingHelp")}</p></div><BarChart3 size={42} /></header>
    {error && <div className="server-message error">{error}</div>}
    <form className="server-statistics-filters" onSubmit={apply}>
      <label>{copy("language")}<select value={draft.language ?? ""} onChange={(event) => setDraft({ ...draft, language: event.target.value || undefined })}><option value="">{copy("allLanguages")}</option>{options.languages.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>{copy("genre")}<select value={draft.genre ?? ""} onChange={(event) => setDraft({ ...draft, genre: event.target.value || undefined })}><option value="">{copy("allGenres")}</option>{options.genres.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>{copy("publisher")}<select value={draft.publisher ?? ""} onChange={(event) => setDraft({ ...draft, publisher: event.target.value || undefined })}><option value="">{copy("allPublishers")}</option>{options.publishers.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>{copy("finishedYear")}<input type="number" min="1000" max="9999" value={draft.reading_year ?? ""} onChange={(event) => setDraft({ ...draft, reading_year: event.target.value ? Number(event.target.value) : undefined })} placeholder={copy("allYears")} /></label>
      <button type="button" onClick={() => { setDraft({}); setFilters({}); void load({}); }}>{copy("clear")}</button><button type="submit">{copy("apply")}</button>
    </form>
    {statistics && <>
      <div className="server-statistics-cards">
        <article><BookCheck /><b>{statistics.unique_books_read}</b><span>{copy("uniqueBooks")}</span></article>
        <article><BookOpen /><b>{statistics.completed_readings}</b><span>{copy("readingEvents")} <small>{copy("dated", { count: statistics.dated_readings })}</small></span></article>
        <article><Repeat2 /><b>{statistics.rereadings}</b><span>{copy("rereadings")}</span></article>
        <article><Gauge /><b>{statistics.average_pages_per_day === null ? "—" : statistics.average_pages_per_day.toFixed(1)}</b><span>{copy("averagePagesDay")}</span></article>
      </div>
      <div className="server-statistics-duration-grid">
        <DurationCard title={copy("pendingTime")} value={statistics.pending_duration} copy={copy} />
        <DurationCard title={copy("readingDuration")} value={statistics.reading_duration} copy={copy} />
      </div>
      <section className="server-statistics-rate"><h3>{copy("readingPace")}</h3><div>
        <span><b>{statistics.pages_read}</b> {copy("pagesRead")}</span>
        <span><b>{statistics.pages_per_week === null ? "—" : statistics.pages_per_week.toFixed(1)}</b> {copy("pagesWeek")}</span>
        <span><b>{statistics.pages_per_month === null ? "—" : statistics.pages_per_month.toFixed(1)}</b> {copy("pagesMonth")}</span>
        <span><b>{statistics.median_pages_per_day === null ? "—" : statistics.median_pages_per_day.toFixed(1)}</b> {copy("medianPagesDay")}</span>
      </div></section>
      <div className="server-statistics-tables">
        <section><h3>{copy("readingByYear")}</h3>{statistics.years.length ? <table><thead><tr><th>{copy("year")}</th><th>{copy("books")}</th><th>{copy("readings")}</th><th>{copy("pages")}</th></tr></thead><tbody>{statistics.years.map((item) => <tr key={item.year}><td>{item.year}</td><td>{item.books_read}</td><td>{item.reading_events}</td><td>{item.pages_read}</td></tr>)}</tbody></table> : <p>{copy("noDatedReadings")}</p>}</section>
        <section className="server-statistics-book-list"><h3>{copy("booksResult")}</h3>{statistics.books.length ? <div className="server-statistics-book-scroll"><table><thead><tr><th>{copy("book")}</th><th>{copy("readings")}</th><th>{copy("daysReading")}</th><th>{copy("pagesDay")}</th></tr></thead><tbody>{statistics.books.map((item) => <tr key={item.book_id}><td><b>{item.title}</b><small>{item.author}</small></td><td>{item.reading_events}</td><td>{item.reading_days || "—"}</td><td>{item.average_pages_per_day === null ? "—" : item.average_pages_per_day.toFixed(1)}</td></tr>)}</tbody></table></div> : <p>{copy("noCompletedReadings")}</p>}</section>
      </div>
      <p className="server-statistics-note">{copy("statisticsNote")}</p>
    </>}
    {loanStatistics && <section className="server-loan-statistics">
      <header><div><p className="server-card-eyebrow">{copy("sharedCustody")}</p><h3>{copy("loanStatistics")}</h3><p>{copy("loanHelp")}</p></div><Handshake size={34} /></header>
      <div className="server-statistics-cards">
        <article><Handshake /><b>{loanStatistics.active}</b><span>{copy("currentlyLoaned")}</span></article>
        <article><AlertTriangle /><b>{loanStatistics.overdue}</b><span>{copy("overdue")}</span></article>
        <article><BookCheck /><b>{loanStatistics.completed}</b><span>{copy("returnedLoans")}</span></article>
        <article><Clock3 /><b>{loanStatistics.unknown_loan_dates + loanStatistics.unknown_return_dates}</b><span>{copy("unknownDates")} <small>{copy("unknownDateSummary", { loaned: loanStatistics.unknown_loan_dates, returned: loanStatistics.unknown_return_dates })}</small></span></article>
      </div>
      <div className="server-statistics-tables">
        <section><h3>{copy("loansByYear")}</h3>{loanStatistics.years.length ? <table><thead><tr><th>{copy("year")}</th><th>{copy("loaned")}</th><th>{copy("returned")}</th></tr></thead><tbody>{loanStatistics.years.map((item) => <tr key={item.year}><td>{item.year}</td><td>{item.loans}</td><td>{item.returns}</td></tr>)}</tbody></table> : <p>{copy("noDatedLoans")}</p>}</section>
        <section className="server-statistics-book-list"><h3>{copy("mostLoaned")}</h3>{loanStatistics.books.length ? <div className="server-statistics-book-scroll"><table><thead><tr><th>{copy("book")}</th><th>{copy("loans")}</th></tr></thead><tbody>{loanStatistics.books.map((item) => <tr key={item.book_id}><td><b>{item.title}</b><small>{item.author}</small></td><td>{item.loans}</td></tr>)}</tbody></table></div> : <p>{copy("noLoans")}</p>}</section>
      </div>
    </section>}
  </section>;
}
