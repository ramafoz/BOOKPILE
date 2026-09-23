import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Eye,
  ExternalLink,
  Layers3,
  LibraryBig,
  MapPin,
  Pencil,
  Plus,
  Search,
  BookMarked,
  Camera,
  Handshake,
  Sparkles,
  RefreshCw,
  LoaderCircle,
  ScanBarcode,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import {
  type CatalogueMetadataOptions,
  type CatalogueQuery,
  type LibraryMemberSummary,
  type LibrarySummary,
  type PhysicalLibrary,
  type ServerBook,
  type ServerBookSummary,
  type ServerBookWrite,
  type ReadingPerspective,
  type BookReading,
  type GoodreadsReview,
  type ReadingCatalogueOverview,
  type LoanOverview,
  type BookLoans,
  type LoanWrite,
  type BibliographicCandidate,
  type ISBNLookupResult,
  ServerApiError,
  serverApi,
} from "./serverApi";
import { decodeIsbnBarcodePhoto } from "../barcode";
import {
  hasActiveCatalogueFilters,
  type QuickCatalogueSort,
  type QuickReadingFilter,
  withDynamicSearch,
  withQuickCatalogueSort,
  withQuickReadingFilter,
} from "./workspacePresentation";
import TimedNoticeStack from "./TimedNoticeStack";
import { useTimedNotices } from "./timedNotices";
import {
  GoodreadsSummary,
  ReadingActionDialog,
  ReadingManager,
  ReadingStatusBadge,
  ReadingSummary,
} from "./ReadingExperience";
import LoanManager, { LoanSummary } from "./LoanExperience";
import type { AppLocale } from "./locale";
import { catalogueCopy, type CatalogueCopy } from "./catalogueCopy";


const PAGE_SIZE = 25;

const EMPTY_BOOK: ServerBookWrite = {
  title: "",
  author: "",
  isbn_10: null,
  isbn_13: null,
  subtitle: null,
  page_count: null,
  publisher: null,
  current_ed_year: null,
  original_publication_year: null,
  language: null,
  original_language: null,
  translation_status: "UNKNOWN",
  edition_number: null,
  fiction_category: null,
  binding: null,
  publication_type: null,
  genre_text: null,
  series_name: null,
  series_volume: null,
  notes: null,
  acquisition_date: null,
  is_original_collection: false,
  height_mm: null,
  width_mm: null,
  thickness_mm: null,
  contributors: [],
};

const EMPTY_OPTIONS: CatalogueMetadataOptions = {
  languages: [], original_languages: [], publishers: [], genres: [],
  series_names: [], contributor_roles: [],
};

function message(error: unknown, fallback = catalogueCopy("en")("serverUnavailable")): string {
  return error instanceof ServerApiError
    ? error.message
    : error instanceof Error
      ? error.message
      : fallback;
}
function numberValue(value: string): number | null {
  return value === "" ? null : Number(value);
}

function writeFromBook(book: ServerBook): ServerBookWrite {
  return {
    title: book.title,
    author: book.author,
    isbn_10: book.isbn_10,
    isbn_13: book.isbn_13,
    subtitle: book.subtitle,
    page_count: book.page_count,
    publisher: book.publisher,
    current_ed_year: book.current_ed_year,
    original_publication_year: book.original_publication_year,
    language: book.language,
    original_language: book.original_language,
    translation_status: book.translation_status,
    edition_number: book.edition_number,
    fiction_category: book.fiction_category,
    binding: book.binding,
    publication_type: book.publication_type,
    genre_text: book.genre_text,
    series_name: book.series_name,
    series_volume: book.series_volume,
    notes: book.notes,
    acquisition_date: book.acquisition_date,
    is_original_collection: book.is_original_collection,
    height_mm: book.height_mm,
    width_mm: book.width_mm,
    thickness_mm: book.thickness_mm,
    contributors: book.contributors.map(({ role_code, name }) => ({ role_code, name })),
  };
}

function MultiSelect({ label, values, selected, onChange, formatValue = (value) => value.replaceAll("_", " ") }: {
  label: string;
  values: string[];
  selected: string[];
  onChange: (values: string[]) => void;
  formatValue?: (value: string) => string;
}) {
  return <label>{label}<select multiple value={selected} onChange={(event) => onChange(
    Array.from(event.currentTarget.selectedOptions, (option) => option.value),
  )}>{values.map((value) => <option key={value} value={value}>{formatValue(value)}</option>)}</select></label>;
}

function CoverImage({ libraryId, book, copy = catalogueCopy("en") }: { libraryId: string; book: ServerBookSummary; copy?: CatalogueCopy }) {
  return book.cover
    ? <img className="server-book-cover" src={serverApi.coverUrl(libraryId, book.id, book.cover.updated_at)} alt={copy("coverOf", { title: book.title })} />
    : <span className="server-book-placeholder"><BookOpen size={20} /></span>;
}

function physicalLocations(data: PhysicalLibrary | null, copy = catalogueCopy("en")) {
  return data?.bookcases.flatMap((bookcase) => bookcase.shelves.flatMap((shelf) => shelf.containers.map((container) => ({
    bookcase,
    shelf,
    container,
    label: `${bookcase.name} · ${copy("shelf")} ${shelf.shelf_number} · ${container.layer === "BACKGROUND" ? copy("background") : copy("foreground")} ${container.container_type === "ROW" ? copy("row") : copy("pile")} ${container.container_number}`,
  })))) ?? [];
}

function locationLabel(data: PhysicalLibrary | null, bookId: string, copy = catalogueCopy("en")): string | null {
  const book = data?.books.find((item) => item.id === bookId);
  if (!book?.container_id || !book.position) return null;
  const location = physicalLocations(data, copy).find(({ container }) => container.id === book.container_id);
  return location ? `${location.label} · ${copy("position")} ${book.position}` : null;
}

export function BookDetails({ libraryId, book, location, reading, perspectiveName, reviews, loans, onClose, onEdit }: {
  libraryId: string;
  book: ServerBook;
  location?: string | null;
  reading?: BookReading | null;
  perspectiveName?: string;
  reviews?: GoodreadsReview[];
  loans?: BookLoans | null;
  onClose: () => void;
  onEdit: (() => void) | null;
}) {
  const rows: Array<[string, string | number | boolean | null]> = [
    ["Subtitle", book.subtitle], ["ISBN-10", book.isbn_10], ["ISBN-13", book.isbn_13],
    ["Pages", book.page_count], ["Publisher", book.publisher],
    ["Current edition year", book.current_ed_year], ["Original publication year", book.original_publication_year],
    ["Language", book.language], ["Original language", book.original_language],
    ["Translation", book.translation_status], ["Edition", book.edition_number],
    ["Category", book.fiction_category], ["Binding", book.binding],
    ["Publication type", book.publication_type], ["Genres", book.genre_text],
    ["Series", book.series_name], ["Series volume", book.series_volume],
    ["Acquired", book.is_original_collection ? "Original collection" : book.acquisition_date],
    ["Height", book.height_mm ? `${book.height_mm} mm` : null],
    ["Width", book.width_mm ? `${book.width_mm} mm` : null],
    ["Thickness", book.thickness_mm ? `${book.thickness_mm} mm` : null],
    ["Notes", book.notes],
    ["Physical location", location ?? null],
  ];
  return <div className="server-modal-backdrop"><section className="server-catalogue-dialog details" role="dialog" aria-modal="true">
    <button className="server-dialog-close" type="button" onClick={onClose} aria-label="Close"><X /></button>
    <p className="server-card-eyebrow">Read-only catalogue record</p>
    <div className="server-book-details-heading"><CoverImage libraryId={libraryId} book={book} /><div><h2>{book.title}</h2><p className="server-book-author">{book.display_author}</p></div></div>
    {!!book.contributors.length && <section><h3>Contributors</h3><div className="server-contributor-credits">{book.contributors.map((item) => <span key={item.id}><b>{item.role_label}</b>{item.name}</span>)}</div></section>}
    {reading && <ReadingSummary reading={reading} perspectiveName={perspectiveName ?? "Selected Owner"} />}
    <LoanSummary loans={loans ?? null} />
    <GoodreadsSummary reviews={reviews ?? []} />
    <dl className="server-book-metadata">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value === null || value === "" ? "Not recorded" : String(value).replaceAll("_", " ")}</dd></div>)}</dl>
    <div className="server-dialog-actions"><button type="button" onClick={onClose}>Close</button>{onEdit && <button className="confirm" type="button" onClick={onEdit}><Pencil size={16} /> Edit book</button>}</div>
  </section></div>;
}

interface PlacementWrite {
  containerId: string;
  position: string;
}

interface InitialPersonalReadingWrite {
  readingMode: "NONE" | "HISTORICAL" | "ACTIVE";
  datesUnknown: boolean;
  startedDate: string;
  finishedDate: string;
  goodreadsUrl: string;
}

interface InitialLoanWrite extends LoanWrite {
  enabled: boolean;
}

const EMPTY_INITIAL_PERSONAL_READING: InitialPersonalReadingWrite = {
  readingMode: "NONE",
  datesUnknown: false,
  startedDate: "",
  finishedDate: "",
  goodreadsUrl: "",
};

const EMPTY_INITIAL_LOAN: InitialLoanWrite = {
  enabled: false,
  loaned_to: "",
  notes: null,
  loaned_date: null,
  expected_return_date: null,
};

type CandidateMetadataKey = "title" | "author" | "isbn_10" | "isbn_13" |
  "subtitle" | "page_count" | "publisher" | "current_ed_year" |
  "original_publication_year" | "language" | "edition_number" |
  "fiction_category" | "binding" | "publication_type" | "genre_text" |
  "series_name" | "series_volume";

function CandidateReview({ candidate, onApply }: {
  candidate: BibliographicCandidate;
  onApply: (selected: Set<CandidateMetadataKey>) => void;
}) {
  const allValues: Array<[CandidateMetadataKey, string, string | number | null]> = [
    ["title", "Title", candidate.title],
    ["author", "Authors", candidate.authors.join(" · ")],
    ["isbn_10", "ISBN-10", candidate.identifiers.isbn_10],
    ["isbn_13", "ISBN-13", candidate.identifiers.isbn_13],
    ["subtitle", "Subtitle", candidate.subtitle],
    ["page_count", "Pages", candidate.page_count],
    ["publisher", "Publisher", candidate.publisher],
    ["current_ed_year", "Edition year", candidate.current_ed_year],
    ["original_publication_year", "Original year", candidate.original_publication_year],
    ["language", "Language", candidate.language],
    ["edition_number", "Edition", candidate.edition_number],
    ["fiction_category", "Category", candidate.fiction_category],
    ["binding", "Binding", candidate.binding],
    ["publication_type", "Publication type", candidate.publication_type],
    ["genre_text", "Genres / categories", candidate.genre_text],
    ["series_name", "Series", candidate.series_name],
    ["series_volume", "Series volume", candidate.series_volume],
  ];
  const values = allValues.filter((entry) => entry[2] !== null && entry[2] !== "");
  const [selected, setSelected] = useState<Set<CandidateMetadataKey>>(new Set());
  return <div className="server-candidate-review">
    <p><b>Choose the values to transfer</b><small>Nothing is selected or saved automatically.</small></p>
    <div>{values.map(([key, label, value]) => <label key={key}>
      <input type="checkbox" checked={selected.has(key)} onChange={(event) => setSelected((current) => {
        const next = new Set(current); if (event.target.checked) next.add(key); else next.delete(key); return next;
      })} />
      <span><b>{label}</b>{String(value).replaceAll("_", " ")}</span>
    </label>)}</div>
    <button type="button" disabled={!selected.size} onClick={() => onApply(selected)}>Apply selected metadata</button>
  </div>;
}

function BookEditor({ libraryId, initial, initialCover, roles, options, physical, bookId, initialPlacement, batchMode, scanFlow, batchAddedCount = 0, onClose, onOpenExisting, onSave }: {
  libraryId: string;
  initial: ServerBookWrite;
  initialCover: ServerBook["cover"];
  roles: CatalogueMetadataOptions["contributor_roles"];
  options: CatalogueMetadataOptions;
  physical: PhysicalLibrary | null;
  bookId: string | null;
  initialPlacement?: PlacementWrite | null;
  batchMode?: boolean;
  scanFlow?: boolean;
  batchAddedCount?: number;
  onClose: () => void;
  onOpenExisting: (bookId: string) => void;
  onSave: (book: ServerBookWrite, cover: File | null, removeCover: boolean, placement: PlacementWrite | null, personal: InitialPersonalReadingWrite | null, loan: InitialLoanWrite | null, reportProgress: (message: string) => void) => Promise<void>;
}) {
  const [draft, setDraft] = useState<ServerBookWrite>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [removeCover, setRemoveCover] = useState(false);
  const [coverPreview, setCoverPreview] = useState<string | null>(null);
  const [personal, setPersonal] = useState<InitialPersonalReadingWrite>(EMPTY_INITIAL_PERSONAL_READING);
  const [loan, setLoan] = useState<InitialLoanWrite>(EMPTY_INITIAL_LOAN);
  const [isbnInput, setIsbnInput] = useState(initial.isbn_13 ?? initial.isbn_10 ?? "");
  const [isbnLookup, setIsbnLookup] = useState<ISBNLookupResult | null>(null);
  const [isbnBusy, setIsbnBusy] = useState(false);
  const [isbnError, setIsbnError] = useState("");
  const [barcodeBusy, setBarcodeBusy] = useState(false);
  const barcodeInput = useRef<HTMLInputElement>(null);
  const [creatingAtOpen] = useState(!bookId);
  const placed = physical?.books.find((item) => item.id === bookId);
  const initialContainerId = initialPlacement?.containerId ?? placed?.container_id ?? "";
  const currentLocation = physicalLocations(physical).find(({ container }) => container.id === initialContainerId);
  const [bookcaseId, setBookcaseId] = useState(currentLocation?.bookcase.id ?? "");
  const [shelfId, setShelfId] = useState(currentLocation?.shelf.id ?? "");
  const [containerId, setContainerId] = useState(initialContainerId);
  const [position, setPosition] = useState(initialPlacement?.position ?? placed?.position?.toString() ?? "");
  const shelves = physical?.bookcases.find((item) => item.id === bookcaseId)?.shelves ?? [];
  const containers = shelves.find((item) => item.id === shelfId)?.containers ?? [];
  useEffect(() => {
    if (!coverFile) { setCoverPreview(null); return; }
    const url = URL.createObjectURL(coverFile);
    setCoverPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [coverFile]);
  const text = (field: keyof ServerBookWrite, value: string) => setDraft({ ...draft, [field]: value || null });
  function setContributors(contributors: Array<{ role_code: string; name: string }>) {
    const authors = contributors.filter((item) => item.role_code === "AUTHOR");
    let author = draft.author;
    if (authors.length >= 2) author = "Multiple authors";
    else if (authors.length === 1) author = authors[0].name;
    else if (author === "Multiple authors") author = "";
    setDraft({ ...draft, contributors, author });
  }
  async function lookUpIsbn(value = isbnInput) {
    if (!value.trim()) { setIsbnError("Enter or scan an ISBN first."); return; }
    setIsbnBusy(true); setIsbnError(""); setIsbnLookup(null);
    try {
      const result = await serverApi.lookupIsbn(libraryId, value);
      setIsbnInput(result.isbn); setIsbnLookup(result);
    } catch (caught) { setIsbnError(message(caught)); }
    finally { setIsbnBusy(false); }
  }
  async function decodeBarcode(file: File | null) {
    if (!file) return;
    setBarcodeBusy(true); setIsbnError(""); setIsbnLookup(null);
    try {
      const isbn = await decodeIsbnBarcodePhoto(file);
      setIsbnInput(isbn);
      await lookUpIsbn(isbn);
    } catch (caught) { setIsbnError(message(caught)); }
    finally { setBarcodeBusy(false); if (barcodeInput.current) barcodeInput.current.value = ""; }
  }
  function applyCandidate(candidate: BibliographicCandidate, selected: Set<CandidateMetadataKey>) {
    const authors = candidate.authors.map((value) => value.trim()).filter(Boolean);
    const contributorAuthors = authors.map((name) => ({ role_code: "AUTHOR", name }));
    const author = authors.length > 1 ? "Multiple authors" : authors[0] ?? draft.author;
    const transferable: Partial<ServerBookWrite> = {
      subtitle: candidate.subtitle, page_count: candidate.page_count,
      publisher: candidate.publisher, current_ed_year: candidate.current_ed_year,
      original_publication_year: candidate.original_publication_year,
      language: candidate.language, edition_number: candidate.edition_number,
      fiction_category: candidate.fiction_category, binding: candidate.binding,
      publication_type: candidate.publication_type, genre_text: candidate.genre_text,
      series_name: candidate.series_name, series_volume: candidate.series_volume,
    };
    const optional = Object.fromEntries(
      (Object.keys(transferable) as CandidateMetadataKey[])
        .filter((key) => selected.has(key)).map((key) => [key, transferable[key as keyof ServerBookWrite]]),
    ) as Partial<ServerBookWrite>;
    setDraft((current) => ({
      ...current,
      ...(selected.has("title") ? { title: candidate.title } : {}),
      ...(selected.has("author") ? { author, contributors: [
        ...current.contributors.filter((item) => item.role_code !== "AUTHOR"), ...contributorAuthors,
      ] } : {}),
      ...(selected.has("isbn_10") ? { isbn_10: candidate.identifiers.isbn_10 } : {}),
      ...(selected.has("isbn_13") ? { isbn_13: candidate.identifiers.isbn_13 } : {}),
      ...optional,
    }));
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setProgress("Saving book…");
    try {
      if (creatingAtOpen && loan.enabled && personal.readingMode === "ACTIVE") throw new Error("A copy cannot be on loan and actively read at the same time.");
      await onSave(draft, coverFile, removeCover, physical ? { containerId, position } : null, creatingAtOpen ? personal : null, creatingAtOpen ? loan : null, setProgress);
    } catch (caught) { setError(message(caught)); setBusy(false); setProgress(""); }
  }
  return <div className="server-modal-backdrop"><section className="server-catalogue-dialog editor" role="dialog" aria-modal="true">
    <button className="server-dialog-close" type="button" onClick={onClose} aria-label="Close" disabled={busy}><X /></button>
    <p className="server-card-eyebrow">{batchMode ? "Batch cataloguing" : "Shared catalogue record"}</p><h2>{initial.title ? "Edit book" : batchMode ? "Add the next book" : "Add a book"}</h2>
    {batchMode && <p className="server-field-help"><b>{batchAddedCount} {batchAddedCount === 1 ? "book" : "books"} added in this batch.</b> After saving, BOOKPILE clears the book data but retains this container and suggests the next position.</p>}
    {error && <div className="server-message error">{error}</div>}
    <form onSubmit={submit} className="server-book-form">
      <fieldset className={`server-isbn-identify${scanFlow ? " scan-flow" : ""}`}><legend>Identify by ISBN or barcode</legend>
        <p className="server-field-help">The barcode photograph is decoded on this device and immediately discarded. Review provider values before transferring them.</p>
        <div className="server-isbn-actions"><label>ISBN-10 or ISBN-13<input value={isbnInput} maxLength={40} inputMode="text" placeholder="978-…" onChange={(event) => { setIsbnInput(event.target.value); setIsbnLookup(null); setIsbnError(""); }} /></label>
          <button type="button" disabled={isbnBusy || barcodeBusy} onClick={() => void lookUpIsbn()}><ScanBarcode size={17} /> {isbnBusy ? "Looking up…" : "Look up ISBN"}</button>
          <label className={`server-barcode-photo${barcodeBusy ? " busy" : ""}`}><Camera size={17} /> {barcodeBusy ? "Reading photo…" : "Take barcode photo"}<input ref={barcodeInput} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" disabled={isbnBusy || barcodeBusy} onChange={(event) => void decodeBarcode(event.target.files?.[0] ?? null)} /></label>
        </div>
        {(isbnBusy || barcodeBusy) && <div className="server-isbn-progress" role="status"><LoaderCircle size={18} /> {barcodeBusy ? "Reading the barcode locally…" : "Checking bibliographic sources and this library…"}</div>}
        {isbnError && <div className="server-message error">{isbnError}</div>}
        {isbnLookup?.catalogue_matches.length ? <div className="server-isbn-matches"><b>This ISBN is already in this library</b>{isbnLookup.catalogue_matches.map((match) => <button type="button" key={match.book_id} onClick={() => onOpenExisting(match.book_id)}>{match.title} · {match.author}</button>)}</div> : null}
        {isbnLookup && !isbnLookup.candidates.length && !isbnLookup.catalogue_matches.length ? <div className="server-message">No bibliographic record was found. You can continue manually.</div> : null}
        {isbnLookup?.candidates.map((candidate, index) => <article className="server-isbn-candidate" key={`${candidate.source}-${candidate.source_record_id ?? index}`}><header><small>{candidate.source.replaceAll("_", " ")}</small><b>{candidate.title}</b><span>{candidate.authors.join(" · ")}</span></header><CandidateReview candidate={candidate} onApply={(selected) => applyCandidate(candidate, selected)} /></article>)}
      </fieldset>
      <fieldset><legend>Required information</legend><div className="server-form-grid">
        <label>Title *<input required maxLength={500} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
        <label>Author display *<input required maxLength={500} value={draft.author} onChange={(event) => setDraft({ ...draft, author: event.target.value })} readOnly={draft.contributors.filter((item) => item.role_code === "AUTHOR").length >= 2} /></label>
      </div></fieldset>
      <fieldset><legend>Private cover image</legend>
        <p className="server-field-help">Visible only to signed-in members of this library. BOOKPILE discards the original after removing metadata and creating a private WebP copy.</p>
        <div className="server-cover-editor">
          {coverPreview && !removeCover
            ? <img src={coverPreview} alt="Selected cover preview" />
            : initialCover && !removeCover
              ? <span className="server-cover-existing"><BookOpen size={28} /> Stored private cover</span>
              : <span className="server-cover-empty"><BookOpen size={28} /> No cover selected</span>}
          <div><label className="server-cover-picker">Take or choose cover<input type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif" onChange={(event) => { setCoverFile(event.target.files?.[0] ?? null); setRemoveCover(false); }} /></label>
          {(initialCover || coverFile) && !removeCover && <button type="button" className="server-cover-remove" onClick={() => { setCoverFile(null); setRemoveCover(true); }}>Remove cover</button>}
          {removeCover && initialCover && <button type="button" onClick={() => setRemoveCover(false)}>Keep existing cover</button>}</div>
        </div>
      </fieldset>
      <fieldset><legend>Contributors</legend><p className="server-field-help">Add authors, translators, illustrators and other credited roles in display order.</p>
        <div className="server-contributor-editor">{draft.contributors.map((item, index) => <div key={`${index}-${item.role_code}`}>
          <select value={item.role_code} onChange={(event) => setContributors(draft.contributors.map((entry, position) => position === index ? { ...entry, role_code: event.target.value } : entry))}>{roles.map((role) => <option key={role.code} value={role.code}>{role.label}</option>)}</select>
          <input required maxLength={300} value={item.name} onChange={(event) => setContributors(draft.contributors.map((entry, position) => position === index ? { ...entry, name: event.target.value } : entry))} placeholder="Contributor name" />
          <button type="button" aria-label="Move up" disabled={index === 0} onClick={() => { const next = [...draft.contributors]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; setContributors(next); }}><ArrowUp size={15} /></button>
          <button type="button" aria-label="Move down" disabled={index === draft.contributors.length - 1} onClick={() => { const next = [...draft.contributors]; [next[index], next[index + 1]] = [next[index + 1], next[index]]; setContributors(next); }}><ArrowDown size={15} /></button>
          <button type="button" aria-label="Remove contributor" onClick={() => setContributors(draft.contributors.filter((_, position) => position !== index))}><Trash2 size={15} /></button>
        </div>)}</div>
        <button type="button" onClick={() => setContributors([...draft.contributors, { role_code: roles[0]?.code ?? "AUTHOR", name: "" }])}><Plus size={15} /> Add contributor</button>
      </fieldset>
      <fieldset><legend>Edition and classification</legend><div className="server-form-grid">
        <label>Subtitle<input value={draft.subtitle ?? ""} onChange={(e) => text("subtitle", e.target.value)} /></label>
        <label>Pages<input type="number" min="1" value={draft.page_count ?? ""} onChange={(e) => setDraft({ ...draft, page_count: numberValue(e.target.value) })} /></label>
        <label>Publisher<input list="server-publishers" value={draft.publisher ?? ""} onChange={(e) => text("publisher", e.target.value)} /></label>
        <label>Current edition year<input type="number" min="1000" max="9999" value={draft.current_ed_year ?? ""} onChange={(e) => setDraft({ ...draft, current_ed_year: numberValue(e.target.value) })} /></label>
        <label>Original publication year<input type="number" min="1000" max="9999" value={draft.original_publication_year ?? ""} onChange={(e) => setDraft({ ...draft, original_publication_year: numberValue(e.target.value) })} /></label>
        <label>Edition number<input type="number" min="1" value={draft.edition_number ?? ""} onChange={(e) => setDraft({ ...draft, edition_number: numberValue(e.target.value) })} /></label>
        <label>Category<select value={draft.fiction_category ?? ""} onChange={(e) => setDraft({ ...draft, fiction_category: e.target.value || null })}><option value="">Not recorded</option><option value="FICTION">Fiction</option><option value="NON_FICTION">Non-fiction</option></select></label>
        <label>Genres<input list="server-genres" value={draft.genre_text ?? ""} onChange={(e) => text("genre_text", e.target.value)} placeholder="Comma-separated" /></label>
        <label>Series<input list="server-series" value={draft.series_name ?? ""} onChange={(e) => text("series_name", e.target.value)} /></label>
        <label>Series volume<input value={draft.series_volume ?? ""} onChange={(e) => text("series_volume", e.target.value)} /></label>
      </div></fieldset>
      <fieldset><legend>Language and translation</legend><div className="server-form-grid">
        <label>Language<input list="server-languages" value={draft.language ?? ""} onChange={(e) => text("language", e.target.value)} /></label>
        <label>Original language<input list="server-original-languages" value={draft.original_language ?? ""} onChange={(e) => text("original_language", e.target.value)} /></label>
        <label>Translation status<select value={draft.translation_status} onChange={(e) => setDraft({ ...draft, translation_status: e.target.value as ServerBookWrite["translation_status"] })}><option value="UNKNOWN">Unknown</option><option value="ORIGINAL">Original language</option><option value="TRANSLATED">Translated</option></select></label>
      </div></fieldset>
      <fieldset><legend>Identifiers</legend><div className="server-form-grid">
        <label>ISBN-10<input value={draft.isbn_10 ?? ""} onChange={(e) => text("isbn_10", e.target.value)} /></label><label>ISBN-13<input value={draft.isbn_13 ?? ""} onChange={(e) => text("isbn_13", e.target.value)} /></label>
      </div></fieldset>
      <fieldset><legend>Copy details</legend><div className="server-form-grid">
        <label>Binding<select value={draft.binding ?? ""} onChange={(e) => setDraft({ ...draft, binding: e.target.value || null })}><option value="">Not recorded</option>{["HARDCOVER", "PAPERBACK", "FLEXIBOUND", "SPIRAL", "STAPLED", "OTHER"].map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>Publication type<select value={draft.publication_type ?? ""} onChange={(e) => setDraft({ ...draft, publication_type: e.target.value || null })}><option value="">Not recorded</option>{["CONVENTIONAL_BOOK", "COMIC_GRAPHIC_NOVEL", "ATLAS", "REFERENCE", "ART_PHOTOGRAPHY_ILLUSTRATED", "MAGAZINE_PERIODICAL", "OTHER"].map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>
        <label>Acquisition date<input type="date" value={draft.acquisition_date ?? ""} disabled={draft.is_original_collection} onChange={(e) => text("acquisition_date", e.target.value)} /></label>
        <label className="server-inline-check"><input type="checkbox" checked={draft.is_original_collection} onChange={(e) => setDraft({ ...draft, is_original_collection: e.target.checked, acquisition_date: e.target.checked ? null : draft.acquisition_date })} /> Original collection</label>
        <label>Height (mm)<input type="number" min="1" max="10000" value={draft.height_mm ?? ""} onChange={(e) => setDraft({ ...draft, height_mm: numberValue(e.target.value) })} /></label><label>Width (mm)<input type="number" min="1" max="10000" value={draft.width_mm ?? ""} onChange={(e) => setDraft({ ...draft, width_mm: numberValue(e.target.value) })} /></label><label>Thickness (mm)<input type="number" min="1" max="10000" value={draft.thickness_mm ?? ""} onChange={(e) => setDraft({ ...draft, thickness_mm: numberValue(e.target.value) })} /></label>
      </div></fieldset>
      {physical && <fieldset><legend>Physical location</legend><p className="server-field-help">Optional. An occupied position makes room automatically; moving a book compacts its previous container.</p><div className="server-form-grid">
        <label>Bookcase<select value={bookcaseId} onChange={(event) => { const value = event.target.value; setBookcaseId(value); const firstShelf = physical.bookcases.find((item) => item.id === value)?.shelves[0]; const firstContainer = firstShelf?.containers[0]; setShelfId(firstShelf?.id ?? ""); setContainerId(firstContainer?.id ?? ""); setPosition(firstContainer ? String(firstContainer.book_count + 1) : ""); }}><option value="">No physical location</option>{physical.bookcases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>Shelf<select disabled={!bookcaseId} value={shelfId} onChange={(event) => { const value = event.target.value; setShelfId(value); const first = shelves.find((item) => item.id === value)?.containers[0]; setContainerId(first?.id ?? ""); setPosition(first ? String(first.book_count + 1) : ""); }}><option value="">Choose shelf</option>{shelves.map((item) => <option key={item.id} value={item.id}>Shelf {item.shelf_number}</option>)}</select></label>
        <label>Container<select disabled={!shelfId} value={containerId} onChange={(event) => { const value = event.target.value; setContainerId(value); const selectedContainer = containers.find((item) => item.id === value); setPosition(selectedContainer ? String(selectedContainer.book_count + (selectedContainer.id === placed?.container_id ? 0 : 1)) : ""); }}><option value="">Choose container</option>{containers.map((item) => <option key={item.id} value={item.id}>{item.layer === "BACKGROUND" ? "Background" : "Foreground"} {item.container_type === "ROW" ? "Row" : "Pile"} {item.container_number}</option>)}</select></label>
        <label>Position<input type="number" min="1" required={Boolean(containerId)} disabled={!containerId} value={position} onChange={(event) => setPosition(event.target.value)} /></label>
      </div></fieldset>}
      <fieldset><legend>Library notes</legend><div className="server-form-grid">
        <label className="wide">Notes<textarea rows={4} maxLength={4000} value={draft.notes ?? ""} onChange={(e) => text("notes", e.target.value)} /></label>
      </div></fieldset>
      {creatingAtOpen && <fieldset className="server-initial-reading"><legend>My reading <small>optional</small></legend>
        <p className="server-field-help">Add your own reading record and Goodreads review while creating this shared catalogue record. These values are personal and are cleared before the next Batch Add book.</p>
        <div className="server-form-grid"><label className="wide">Reading record<select value={personal.readingMode} onChange={(event) => setPersonal({ ...personal, readingMode: event.target.value as InitialPersonalReadingWrite["readingMode"], datesUnknown: false, startedDate: "", finishedDate: "" })}><option value="NONE">No reading record</option><option value="HISTORICAL">Historical reading — completed</option><option value="ACTIVE">Currently reading — started</option></select></label></div>
        {personal.readingMode !== "NONE" && <div className="server-form-grid server-initial-reading-dates">
          {personal.readingMode === "HISTORICAL" && <label className="server-compact-check wide"><input type="checkbox" checked={personal.datesUnknown} onChange={(event) => setPersonal({ ...personal, datesUnknown: event.target.checked, startedDate: event.target.checked ? "" : personal.startedDate, finishedDate: event.target.checked ? "" : personal.finishedDate })} /> Reading dates unknown</label>}
          {!personal.datesUnknown && <><label>Started<input type="date" required value={personal.startedDate} onChange={(event) => setPersonal({ ...personal, startedDate: event.target.value })} /></label>{personal.readingMode === "HISTORICAL" && <label>Finished<input type="date" required value={personal.finishedDate} onChange={(event) => setPersonal({ ...personal, finishedDate: event.target.value })} /></label>}</>}
        </div>}
        <div className="server-form-grid"><label className="wide">My Goodreads review URL<input type="url" placeholder="https://www.goodreads.com/review/show/..." value={personal.goodreadsUrl} onChange={(event) => setPersonal({ ...personal, goodreadsUrl: event.target.value })} /></label></div>
      </fieldset>}
      {creatingAtOpen && <fieldset className="server-initial-loan"><legend>Current loan <small>optional</small></legend>
        <label className="server-compact-check"><input type="checkbox" checked={loan.enabled} onChange={(event) => setLoan({ ...EMPTY_INITIAL_LOAN, enabled: event.target.checked })} /> This physical copy is currently on loan</label>
        {loan.enabled && <><p className="server-field-help">The retained shelf position is preserved while the copy appears in the shared On loan area.</p><div className="server-form-grid">
          <label>Loaned to *<input required maxLength={300} value={loan.loaned_to} onChange={(event) => setLoan({ ...loan, loaned_to: event.target.value })} /></label>
          <label>Loan date <small>optional / unknown</small><input type="date" value={loan.loaned_date ?? ""} onChange={(event) => setLoan({ ...loan, loaned_date: event.target.value || null })} /></label>
          <label>Expected return <small>optional</small><input type="date" value={loan.expected_return_date ?? ""} onChange={(event) => setLoan({ ...loan, expected_return_date: event.target.value || null })} /></label>
          <label className="wide">Private Owner notes<textarea rows={2} maxLength={4000} value={loan.notes ?? ""} onChange={(event) => setLoan({ ...loan, notes: event.target.value || null })} /></label>
        </div></>}
      </fieldset>}
      <datalist id="server-publishers">{options.publishers.map((v) => <option key={v} value={v} />)}</datalist><datalist id="server-genres">{options.genres.map((v) => <option key={v} value={v} />)}</datalist><datalist id="server-series">{options.series_names.map((v) => <option key={v} value={v} />)}</datalist><datalist id="server-languages">{options.languages.map((v) => <option key={v} value={v} />)}</datalist><datalist id="server-original-languages">{options.original_languages.map((v) => <option key={v} value={v} />)}</datalist>
      {progress && <div className="server-save-progress" role="status">{progress}<small>{progress.startsWith("Processing") ? "Large phone photos can take several seconds. Please keep this window open." : ""}</small></div>}
      <div className="server-dialog-actions"><button type="button" onClick={onClose} disabled={busy}>{batchMode ? "Finish batch" : "Cancel"}</button><button className="confirm" disabled={busy} type="submit">{busy ? "Please wait…" : batchMode ? scanFlow ? "Save and scan next" : "Save and add next" : "Save book"}</button></div>
    </form>
  </section></div>;
}

export default function CatalogueWorkspace({ library, memberSummary, signedInUserId, perspectives, locale, onOpenProfile, onSetUpMap }: {
  library: LibrarySummary;
  memberSummary: LibraryMemberSummary[];
  signedInUserId: string;
  perspectives: ReadingPerspective[];
  locale: AppLocale;
  onOpenProfile: (userId: string) => void;
  onSetUpMap: () => void;
}) {
  const copy = useMemo(() => catalogueCopy(locale), [locale]);
  const enumLabels: Record<string, string> = {
    UNKNOWN: copy("unknown"), ORIGINAL: copy("original"), TRANSLATED: copy("translated"),
    FICTION: copy("fiction"), NON_FICTION: copy("nonFiction"),
    HARDCOVER: copy("hardcover"), PAPERBACK: copy("paperback"), FLEXIBOUND: copy("flexibound"),
    SPIRAL: copy("spiral"), STAPLED: copy("stapled"), OTHER: copy("other"),
    CONVENTIONAL_BOOK: copy("conventionalBook"), COMIC_GRAPHIC_NOVEL: copy("comicGraphicNovel"),
    ATLAS: copy("atlas"), REFERENCE: copy("reference"),
    ART_PHOTOGRAPHY_ILLUSTRATED: copy("artPhotographyIllustrated"),
    MAGAZINE_PERIODICAL: copy("magazinePeriodical"),
  };
  const enumLabel = (value: string) => enumLabels[value] ?? value.replaceAll("_", " ");
  const [books, setBooks] = useState<ServerBookSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState<CatalogueQuery>({ limit: PAGE_SIZE, offset: 0, sort_by: "title", sort_order: "asc" });
  const [draftQuery, setDraftQuery] = useState<CatalogueQuery>(query);
  const [options, setOptions] = useState(EMPTY_OPTIONS);
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const { notices, pushNotice, dismissNotice } = useTimedNotices();
  const [details, setDetails] = useState<ServerBook | null>(null);
  const [editing, setEditing] = useState<{ id: string | null; book: ServerBookWrite; cover: ServerBook["cover"] } | null>(null);
  const [physical, setPhysical] = useState<PhysicalLibrary | null>(null);
  const [addMenu, setAddMenu] = useState(false);
  const [batchMode, setBatchMode] = useState(false);
  const [scanFlow, setScanFlow] = useState(false);
  const [batchPlacement, setBatchPlacement] = useState<PlacementWrite | null>(null);
  const [editorSequence, setEditorSequence] = useState(0);
  const [batchAddedCount, setBatchAddedCount] = useState(0);
  const [readings, setReadings] = useState<Record<string, BookReading>>({});
  const [bookReviews, setBookReviews] = useState<Record<string, GoodreadsReview[]>>({});
  const [readingOverview, setReadingOverview] = useState<ReadingCatalogueOverview | null>(null);
  const [detailsReading, setDetailsReading] = useState<BookReading | null>(null);
  const [detailsReviews, setDetailsReviews] = useState<GoodreadsReview[]>([]);
  const [detailsLoans, setDetailsLoans] = useState<BookLoans | null>(null);
  const [loanOverview, setLoanOverview] = useState<LoanOverview | null>(null);
  const [loanManager, setLoanManager] = useState<ServerBookSummary | null>(null);
  const [readingAction, setReadingAction] = useState<{ book: ServerBookSummary; reading: BookReading } | null>(null);
  const [readingManager, setReadingManager] = useState<ServerBookSummary | null>(null);
  const [suggestion, setSuggestion] = useState<ServerBookSummary | null>(null);
  const loadSequence = useRef(0);
  const queryRef = useRef(query);
  const selectedPerspective = perspectives.find((item) => item.selected);
  const perspectiveUserId = selectedPerspective?.user_id ?? signedInUserId;

  const loadPersonalRows = useCallback(async (
    items: ServerBookSummary[],
    sequence = loadSequence.current,
  ) => {
    const overview = await serverApi.readingOverview(library.library_id, perspectiveUserId);
    if (sequence !== loadSequence.current) return;
    setReadingOverview(overview);
    const overviewByBook = Object.fromEntries(overview.items.map((item) => [item.book_id, item]));
    setReadings(Object.fromEntries(items.map((book) => {
      const item = overviewByBook[book.id];
      return [book.id, {
        library_id: library.library_id, book_id: book.id,
        perspective_user_id: overview.perspective_user_id,
        state: item?.state ?? "PENDING",
        active_reader_present: item?.active_reader_present ?? false,
        writable: overview.writable, total_sessions: 0, limit: 0, offset: 0, sessions: [],
      } satisfies BookReading];
    })));
    setBookReviews(Object.fromEntries(items.map((book) => {
      const url = overviewByBook[book.id]?.goodreads_url;
      return [book.id, url ? [{ user_id: overview.perspective_user_id, username: selectedPerspective?.username ?? "Owner", url }] : []];
    })));
  }, [library.library_id, perspectiveUserId, selectedPerspective?.username]);

  const load = useCallback(async (next: CatalogueQuery) => {
    const sequence = ++loadSequence.current;
    setBusy(true); setError("");
    try {
      const [page, loans] = await Promise.all([
        serverApi.catalogue(library.library_id, { ...next, perspective_user_id: perspectiveUserId }),
        serverApi.loanOverview(library.library_id),
      ]);
      if (sequence !== loadSequence.current) return;
      setBooks(page.books); setTotal(page.total); setLoanOverview(loans);
      await loadPersonalRows(page.books, sequence);
    }
    catch (caught) { if (sequence === loadSequence.current) setError(message(caught, copy("serverUnavailable"))); }
    finally { if (sequence === loadSequence.current) setBusy(false); }
  }, [copy, library.library_id, loadPersonalRows, perspectiveUserId]);

  useEffect(() => { queryRef.current = query; }, [query]);

  useEffect(() => {
    const initial = { limit: PAGE_SIZE, offset: 0, sort_by: "title", sort_order: "asc" as const };
    queryRef.current = initial;
    setQuery(initial); setDraftQuery(initial); setDetails(null); setEditing(null); setReadingAction(null); setReadingManager(null); setLoanManager(null);
    void load(initial);
    if (library.can_view_map) void serverApi.physicalLibrary(library.library_id).then(setPhysical).catch((caught) => setError(message(caught, copy("serverUnavailable"))));
    else setPhysical(null);
    void serverApi.catalogueOptions(library.library_id).then(setOptions).catch((caught) => setError(message(caught, copy("serverUnavailable"))));
  }, [library.library_id, library.can_view_map, load, copy]);

  useEffect(() => {
    const value = draftQuery.search ?? "";
    if ((queryRef.current.search ?? "") === value.trim()) return;
    const timer = window.setTimeout(() => {
      const next = withDynamicSearch(queryRef.current, value);
      queryRef.current = next;
      setQuery(next);
      void load(next);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [draftQuery.search, load]);

  async function requireOptions(): Promise<CatalogueMetadataOptions> {
    if (options.contributor_roles.length) return options;
    const loaded = await serverApi.catalogueOptions(library.library_id);
    if (!loaded.contributor_roles.length) {
      throw new Error(copy("contributorRolesUnavailable"));
    }
    setOptions(loaded);
    return loaded;
  }
  async function add(asBatch = false, asScan = false) {
    setError("");
    try {
      await requireOptions();
      setBatchMode(asBatch);
      setScanFlow(asScan);
      setBatchAddedCount(0);
      setBatchPlacement(null);
      setEditorSequence((value) => value + 1);
      setAddMenu(false);
      setEditing({ id: null, book: { ...EMPTY_BOOK, contributors: [] }, cover: null });
    }
    catch (caught) { setError(message(caught)); }
  }
  function apply(event?: FormEvent) { event?.preventDefault(); const next = { ...draftQuery, limit: PAGE_SIZE, offset: 0 }; queryRef.current = next; setQuery(next); void load(next); }
  function page(offset: number) { const next = { ...query, offset }; queryRef.current = next; setQuery(next); setDraftQuery(next); void load(next); }
  function applyQuickReadingFilter(readingState: QuickReadingFilter) {
    const next = withQuickReadingFilter(queryRef.current, readingState);
    queryRef.current = next;
    setQuery(next);
    setDraftQuery((current) => ({ ...current, reading_state: readingState, offset: 0 }));
    void load(next);
  }
  function applyQuickSort(sortBy: QuickCatalogueSort) {
    const next = withQuickCatalogueSort(queryRef.current, sortBy);
    queryRef.current = next;
    setQuery(next);
    setDraftQuery((current) => ({ ...current, sort_by: sortBy, offset: 0 }));
    void load(next);
  }
  async function openDetails(bookId: string) { setBusy(true); try { const [book, reading, reviews, loans] = await Promise.all([serverApi.book(library.library_id, bookId), serverApi.bookReading(library.library_id, bookId, perspectiveUserId), serverApi.goodreadsReviews(library.library_id, bookId), serverApi.bookLoans(library.library_id, bookId)]); setDetails(book); setDetailsReading(reading); setDetailsReviews(reviews); setDetailsLoans(loans); } catch (caught) { setError(message(caught)); } finally { setBusy(false); } }
  async function openReadingAction(book: ServerBookSummary) {
    setBusy(true); setError("");
    try {
      const reading = await serverApi.bookReading(library.library_id, book.id, perspectiveUserId);
      if (reading.writable) setReadingAction({ book, reading });
    } catch (caught) { setError(message(caught)); }
    finally { setBusy(false); }
  }
  async function suggestNewRead() {
    setBusy(true); setError("");
    try {
      const activeFilters = { ...query };
      delete activeFilters.offset;
      delete activeFilters.limit;
      delete activeFilters.sort_by;
      delete activeFilters.sort_order;
      const page = await serverApi.catalogue(library.library_id, {
        ...activeFilters,
        perspective_user_id: perspectiveUserId,
        reading_state: "PENDING",
        available_only: true,
        sort_by: "random",
        limit: 1,
        offset: 0,
      });
      if (!page.books.length) throw new Error(copy("noSuggestedBooks"));
      setSuggestion(page.books[0]);
      setAddMenu(false);
    } catch (caught) { setError(message(caught)); }
    finally { setBusy(false); }
  }
  async function edit(bookId: string) { setBusy(true); setBatchMode(false); setScanFlow(false); setBatchPlacement(null); try { const [book] = await Promise.all([serverApi.book(library.library_id, bookId), requireOptions()]); setDetails(null); setEditing({ id: book.id, book: writeFromBook(book), cover: book.cover }); } catch (caught) { setError(message(caught)); } finally { setBusy(false); } }
  async function save(book: ServerBookWrite, coverFile: File | null, removeCover: boolean, placement: PlacementWrite | null, personal: InitialPersonalReadingWrite | null, loan: InitialLoanWrite | null, reportProgress: (message: string) => void) {
    const wasNew = !editing?.id;
    const placementPosition = placement?.containerId
      ? Number.parseInt(placement.position, 10)
      : null;
    const saved = editing?.id
      ? placement
        ? await serverApi.updateBookWithPlacement(library.library_id, editing.id, book, placement.containerId || null, placementPosition)
        : await serverApi.updateBook(library.library_id, editing.id, book)
      : loan?.enabled
        ? await serverApi.createBookWithPlacementAndLoan(library.library_id, book, placement?.containerId || null, placementPosition, {
          loaned_to: loan.loaned_to,
          notes: loan.notes,
          loaned_date: loan.loaned_date,
          expected_return_date: loan.expected_return_date,
        })
      : placement
        ? await serverApi.createBookWithPlacement(library.library_id, book, placement.containerId || null, placementPosition)
        : await serverApi.createBook(library.library_id, book);
    if (wasNew) setEditing({ id: saved.id, book: writeFromBook(saved), cover: saved.cover });
    try {
      if (placement) {
        setPhysical(await serverApi.physicalLibrary(library.library_id));
      }
      if (coverFile) {
        reportProgress("Processing private cover…");
        await serverApi.uploadCover(library.library_id, saved.id, coverFile);
      } else if (removeCover && saved.cover) {
        reportProgress("Removing private cover…");
        await serverApi.deleteCover(library.library_id, saved.id);
      }
      if (personal?.goodreadsUrl.trim()) {
        reportProgress("Saving your Goodreads review…");
        await serverApi.setMyGoodreadsReview(library.library_id, saved.id, personal.goodreadsUrl.trim());
      }
      if (personal?.readingMode === "HISTORICAL") {
        reportProgress("Saving your reading history…");
        await serverApi.addHistoricalReading(library.library_id, saved.id, {
          started_date: personal.datesUnknown ? null : personal.startedDate,
          finished_date: personal.datesUnknown ? null : personal.finishedDate,
          dates_unknown: personal.datesUnknown,
        });
      } else if (personal?.readingMode === "ACTIVE") {
        reportProgress("Starting your reading…");
        await serverApi.startReading(library.library_id, saved.id, personal.startedDate);
      }
    } catch (caught) {
      if (wasNew) throw new Error(`The shared book and location were saved, but some private cover or personal reading data was not. ${message(caught)} Correct it and retry: BOOKPILE will update this book rather than create a duplicate.`);
      throw caught;
    }
    if (batchMode) {
      const nextPosition = placement?.containerId && placement.position
        ? String(Number.parseInt(placement.position, 10) + 1)
        : "";
      setBatchPlacement(placement ? { ...placement, position: nextPosition } : null);
      setEditorSequence((value) => value + 1);
      setBatchAddedCount((value) => value + 1);
      setEditing({ id: null, book: { ...EMPTY_BOOK, contributors: [] }, cover: null });
      pushNotice(`“${saved.title}” saved. Ready for the next book.`);
    } else {
      setEditing(null);
      setBatchMode(false);
      setBatchPlacement(null);
      pushNotice(wasNew ? "Book and private cover saved." : "Book updated.");
    }
    await Promise.all([load(query), serverApi.catalogueOptions(library.library_id).then(setOptions)]);
  }
  async function remove(book: ServerBookSummary) { if (!window.confirm(`Permanently delete “${book.title}”? This cannot be undone.`)) return; try { await serverApi.deleteBook(library.library_id, book.id, book.title); pushNotice("Book permanently deleted."); await load(query); if (library.can_view_map) setPhysical(await serverApi.physicalLibrary(library.library_id)); } catch (caught) { setError(message(caught)); } }

  async function refreshPersonalData() {
    await loadPersonalRows(books);
    if (details) {
      const [reading, reviews] = await Promise.all([serverApi.bookReading(library.library_id, details.id, perspectiveUserId), serverApi.goodreadsReviews(library.library_id, details.id)]);
      setDetailsReading(reading); setDetailsReviews(reviews);
    }
    pushNotice("Personal reading data updated.");
  }

  async function refreshLoanData() {
    await load(query);
    if (details) setDetailsLoans(await serverApi.bookLoans(library.library_id, details.id));
    pushNotice("Shared loan data updated.");
  }

  const filtered = hasActiveCatalogueFilters(query);
  const activeLoans = Object.fromEntries((loanOverview?.loans ?? []).filter((item) => item.state === "ACTIVE").map((item) => [item.book_id, item]));
  const readingState = query.reading_state ?? "ANY";
  const quickSort = ["title", "author", "physical"].includes(query.sort_by ?? "title") ? query.sort_by ?? "title" : "";
  const catalogueTotal = readingOverview
    ? readingOverview.pending + readingOverview.reading + readingOverview.rereading + readingOverview.read
    : total;
  const cataloguePrivacy = memberSummary.length > 1 ? copy("sharedCatalogue") : copy("privateCatalogue");
  const catalogueHeading = !selectedPerspective || selectedPerspective.user_id === signedInUserId
    ? copy("yourBooks")
    : copy("usersBooks", { username: selectedPerspective.username });
  return <section className="server-catalogue-workspace">
    <header><div className="server-catalogue-identity"><span className="server-catalogue-icon"><BookOpen size={25} /></span><span><span className="server-catalogue-sharing"><p className="server-card-eyebrow">{cataloguePrivacy}</p>{memberSummary.length > 1 && <details><summary>{copy("memberCount", { count: memberSummary.length })}</summary><span>{memberSummary.map((member) => <span key={member.user_id}><button className="server-username-link" type="button" onClick={() => onOpenProfile(member.user_id)}>@{member.username}</button><small>{member.role === "OWNER" ? copy("owner") : copy("viewer")}</small></span>)}</span></details>}</span><h3>{catalogueHeading}</h3><small>{total} {total === 1 ? copy("book") : copy("books")}{filtered ? ` ${copy("match")}` : ""}</small></span></div>{library.role === "OWNER" && <div className="server-catalogue-actions">{readingOverview?.writable && <button className="server-secondary-action" type="button" onClick={() => void suggestNewRead()}><Sparkles size={17} /> {copy("newRead")}</button>}<button className="server-primary-action" type="button" onClick={() => setAddMenu(!addMenu)}><Plus size={17} /> {copy("add")} <ChevronDown size={15} /></button>{addMenu && <div className="server-add-menu"><button type="button" onClick={() => void add(false)}><BookOpen size={16} /> {copy("addSingleBook")}</button><button type="button" onClick={() => void add(true)}><Layers3 size={16} /> {copy("batchAdd")}</button><button className="server-mobile-add" type="button" onClick={() => void add(false, true)}><ScanBarcode size={16} /> {copy("scanSingleBarcode")}</button><button className="server-mobile-add" type="button" onClick={() => void add(true, true)}><Camera size={16} /> {copy("batchScan")}</button></div>}{suggestion && <div className="server-reading-suggestion"><p className="server-card-eyebrow">{copy("readingSuggestion")}</p><b>{suggestion.title}</b><span>{suggestion.display_author}</span><div><button type="button" onClick={() => void suggestNewRead()}><RefreshCw size={15} /> {copy("another")}</button><button type="button" className="confirm" onClick={() => { const chosen = suggestion; setSuggestion(null); void openReadingAction(chosen); }}>{copy("startReading")}</button></div><button className="close" type="button" onClick={() => setSuggestion(null)} aria-label={copy("closeSuggestion")}><X size={15} /></button></div>}</div>}</header>
    {error && <div className="server-message error">{error}</div>}<TimedNoticeStack notices={notices} onDismiss={dismissNotice} />
    {readingOverview && <div className="server-catalogue-summary" aria-label={copy("readingSummary")}>
      <button className="total" type="button" aria-pressed={readingState === "ANY"} onClick={() => applyQuickReadingFilter("ANY")}><span><LibraryBig /></span><strong>{catalogueTotal}</strong><small>{copy("totalBooks")}</small></button>
      <button className="pending" type="button" aria-pressed={readingState === "PENDING"} onClick={() => applyQuickReadingFilter("PENDING")}><span><BookOpen /></span><strong>{readingOverview.pending}</strong><small>{copy("waitingToRead")}</small></button>
      <button className="reading" type="button" aria-pressed={["ACTIVE", "READING", "REREADING"].includes(readingState)} onClick={() => applyQuickReadingFilter("ACTIVE")}><span><BookOpen /></span><strong>{readingOverview.active_display}</strong><small>{copy("currentlyReading")}</small></button>
      <button className="read" type="button" aria-pressed={readingState === "READ"} onClick={() => applyQuickReadingFilter("READ")}><span><Check /></span><strong>{readingOverview.read}</strong><small>{copy("read")}</small></button>
    </div>}
    <div className="server-catalogue-search" role="search"><label className="server-catalogue-search-field"><Search size={18} /><input value={draftQuery.search ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, search: e.target.value })} placeholder={copy("searchPlaceholder")} aria-label={copy("searchCatalogue")} /></label><label className="server-catalogue-quick-sort"><span>{copy("sort")}</span><select value={quickSort} onChange={(event) => applyQuickSort(event.target.value as QuickCatalogueSort)} aria-label={copy("sortCatalogue")}><option value="" disabled>{copy("advancedSort")}</option><option value="title">{copy("title")}</option><option value="author">{copy("author")}</option><option value="physical">{copy("physicalLocation")}</option></select></label><button type="button" className={advanced ? "active" : ""} onClick={() => setAdvanced(!advanced)}><SlidersHorizontal size={17} /> {copy("advanced")}</button></div>
    {advanced && <form className="server-advanced-search" onSubmit={apply}>
      <label>ISBN<input value={draftQuery.isbn ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, isbn: e.target.value })} /></label>
      <MultiSelect label={copy("languages")} values={options.languages} selected={draftQuery.language ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, language: value })} /><MultiSelect label={copy("originalLanguages")} values={options.original_languages} selected={draftQuery.original_language ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, original_language: value })} /><MultiSelect label={copy("genres")} values={options.genres} selected={draftQuery.genre ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, genre: value })} /><MultiSelect label={copy("publishers")} values={options.publishers} selected={draftQuery.publisher ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, publisher: value })} /><MultiSelect label={copy("series")} values={options.series_names} selected={draftQuery.series_name ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, series_name: value })} />
      <MultiSelect label={copy("translation")} values={["UNKNOWN", "ORIGINAL", "TRANSLATED"]} selected={draftQuery.translation_status ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, translation_status: value })} formatValue={enumLabel} /><MultiSelect label={copy("category")} values={["FICTION", "NON_FICTION"]} selected={draftQuery.fiction_category ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, fiction_category: value })} formatValue={enumLabel} /><MultiSelect label={copy("binding")} values={["HARDCOVER", "PAPERBACK", "FLEXIBOUND", "SPIRAL", "STAPLED", "OTHER"]} selected={draftQuery.binding ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, binding: value })} formatValue={enumLabel} /><MultiSelect label={copy("publicationType")} values={["CONVENTIONAL_BOOK", "COMIC_GRAPHIC_NOVEL", "ATLAS", "REFERENCE", "ART_PHOTOGRAPHY_ILLUSTRATED", "MAGAZINE_PERIODICAL", "OTHER"]} selected={draftQuery.publication_type ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, publication_type: value })} formatValue={enumLabel} />
      <label>{copy("seriesMembership")}<select value={draftQuery.series_state ?? "ANY"} onChange={(e) => setDraftQuery({ ...draftQuery, series_state: e.target.value as CatalogueQuery["series_state"] })}><option value="ANY">{copy("any")}</option><option value="YES">{copy("inSeries")}</option><option value="NO">{copy("notInSeries")}</option></select></label><label>{copy("authors")}<select value={draftQuery.author_structure ?? "ANY"} onChange={(e) => setDraftQuery({ ...draftQuery, author_structure: e.target.value as CatalogueQuery["author_structure"] })}><option value="ANY">{copy("any")}</option><option value="SINGLE">{copy("singleAuthor")}</option><option value="MULTIPLE">{copy("multipleAuthors")}</option></select></label>
      <label>{copy("minimumPages")}<input type="number" min="1" value={draftQuery.page_min ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, page_min: numberValue(e.target.value) ?? undefined })} /></label><label>{copy("maximumPages")}<input type="number" min="1" value={draftQuery.page_max ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, page_max: numberValue(e.target.value) ?? undefined })} /></label>
      <label>{copy("yearField")}<select value={draftQuery.year_field ?? "current_ed_year"} onChange={(e) => setDraftQuery({ ...draftQuery, year_field: e.target.value as CatalogueQuery["year_field"] })}><option value="current_ed_year">{copy("currentEdition")}</option><option value="original_publication_year">{copy("originalPublication")}</option></select></label><label>{copy("minimumYear")}<input type="number" min="1000" max="9999" value={draftQuery.year_min ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, year_min: numberValue(e.target.value) ?? undefined })} /></label><label>{copy("maximumYear")}<input type="number" min="1000" max="9999" value={draftQuery.year_max ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, year_max: numberValue(e.target.value) ?? undefined })} /></label>
      <label>{copy("personalReadingState")}<select value={draftQuery.reading_state ?? "ANY"} onChange={(e) => setDraftQuery({ ...draftQuery, reading_state: e.target.value as CatalogueQuery["reading_state"] })}><option value="ANY">{copy("any")}</option><option value="PENDING">{copy("pending")}</option><option value="ACTIVE">{copy("activeReading")}</option><option value="READING">{copy("firstReading")}</option><option value="REREADING">{copy("rereadingNow")}</option><option value="READ">{copy("readInactive")}</option></select></label>
      <label>{copy("rereadingHistory")}<select value={draftQuery.rereading_state ?? "ANY"} onChange={(e) => setDraftQuery({ ...draftQuery, rereading_state: e.target.value as CatalogueQuery["rereading_state"] })}><option value="ANY">{copy("any")}</option><option value="YES">{copy("hasBeenReread")}</option><option value="NO">{copy("hasNotBeenReread")}</option></select></label>
      <label>{copy("readingDate")}<select value={draftQuery.reading_date_field ?? "FINISHED"} onChange={(e) => setDraftQuery({ ...draftQuery, reading_date_field: e.target.value as CatalogueQuery["reading_date_field"] })}><option value="STARTED">{copy("readingStarted")}</option><option value="FINISHED">{copy("finishedReading")}</option></select></label>
      <label>{copy("readingDateFrom")}<input type="date" value={draftQuery.reading_date_from ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, reading_date_from: e.target.value || undefined })} /></label><label>{copy("readingDateTo")}<input type="date" value={draftQuery.reading_date_to ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, reading_date_to: e.target.value || undefined })} /></label>
      <label>{copy("loanHistory")}<select value={draftQuery.loan_scope ?? "ANY"} onChange={(e) => setDraftQuery({ ...draftQuery, loan_scope: e.target.value as CatalogueQuery["loan_scope"] })}><option value="ANY">{copy("any")}</option><option value="ACTIVE">{copy("currentlyOnLoan")}</option><option value="OVERDUE">{copy("overdue")}</option><option value="EVER">{copy("everLoaned")}</option><option value="NEVER">{copy("neverLoaned")}</option></select></label>
      {library.role === "OWNER" && <label>{copy("borrowerContains")}<input maxLength={300} value={draftQuery.loaned_to ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, loaned_to: e.target.value || undefined })} /></label>}
      <label>{copy("loanDate")}<select value={draftQuery.loan_date_field ?? "LOANED"} onChange={(e) => setDraftQuery({ ...draftQuery, loan_date_field: e.target.value as CatalogueQuery["loan_date_field"] })}><option value="LOANED">{copy("loaned")}</option><option value="EXPECTED">{copy("expectedReturn")}</option><option value="RETURNED">{copy("returned")}</option></select></label>
      <label>{copy("loanDateFrom")}<input type="date" value={draftQuery.loan_date_from ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, loan_date_from: e.target.value || undefined })} /></label><label>{copy("loanDateTo")}<input type="date" value={draftQuery.loan_date_to ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, loan_date_to: e.target.value || undefined })} /></label>
      <label>{copy("sortBy")}<select value={draftQuery.sort_by ?? "title"} onChange={(e) => setDraftQuery({ ...draftQuery, sort_by: e.target.value })}>{[["title", copy("title")], ["author", copy("author")], ["physical", copy("physicalLocation")], ["created_at", copy("dateAdded")], ["updated_at", copy("lastUpdated")], ["page_count", copy("pages")], ["publisher", copy("publisher")], ["current_ed_year", copy("editionYear")], ["original_publication_year", copy("originalYear")], ["acquisition_date", copy("acquisitionDate")], ["loaned_date", copy("loanedDate")], ["expected_return_date", copy("expectedReturn")], ["returned_date", copy("returned")]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>{copy("direction")}<select value={draftQuery.sort_order ?? "asc"} onChange={(e) => setDraftQuery({ ...draftQuery, sort_order: e.target.value as "asc" | "desc" })}><option value="asc">{copy("ascending")}</option><option value="desc">{copy("descending")}</option></select></label>
      <div className="server-advanced-actions"><button type="button" onClick={() => { const clear = { limit: PAGE_SIZE, offset: 0, sort_by: "title", sort_order: "asc" as const }; queryRef.current = clear; setDraftQuery(clear); setQuery(clear); void load(clear); }}>{copy("clear")}</button><button className="confirm" type="submit">{copy("applyFilters")}</button></div>
    </form>}
    <div className={`server-book-list ${busy ? "loading" : ""}`}>{books.map((book) => { const location = locationLabel(physical, book.id, copy); const reading = readings[book.id]; const activeLoan = activeLoans[book.id]; const returnLocation = location ? ` · ${copy("returnsTo", { location })}` : ""; const custody = activeLoan ? `${activeLoan.loaned_to ? copy("onLoanTo", { borrower: activeLoan.loaned_to }) : copy("onLoan")}${returnLocation}` : reading?.active_reader_present ? `${copy("beingRead")}${returnLocation}` : (location ?? copy("noPhysicalLocation")); const perspectiveReview = bookReviews[book.id]?.find((review) => review.user_id === perspectiveUserId); return <article key={book.id}><ReadingStatusBadge reading={reading} onClick={() => void openReadingAction(book)} /><CoverImage libraryId={library.library_id} book={book} copy={copy} /><div><h4>{book.title}</h4><p>{book.display_author}</p><small>{[book.publisher, book.current_ed_year, book.language, book.page_count ? copy("pageCount", { count: book.page_count }) : null].filter(Boolean).join(" · ") || copy("noOptionalMetadata")}</small></div>{library.can_view_map ? <div className={`server-book-location ${activeLoan ? activeLoan.overdue ? "on-loan overdue" : "on-loan" : reading?.active_reader_present ? "being-read" : ""}`}><MapPin size={16} /><span>{custody}</span></div> : <div className="server-book-location unavailable" aria-hidden="true" />}<div className="server-book-row-actions"><button type="button" onClick={() => void openDetails(book.id)} title={copy("completeInformation")}><Eye size={17} /></button>{perspectiveReview && <a className="server-icon-link" href={perspectiveReview.url} target="_blank" rel="noreferrer" title={copy("goodreadsReview", { username: selectedPerspective?.username ?? copy("owner") })}><ExternalLink size={17} /></a>}{reading?.writable && <button type="button" onClick={() => setReadingManager(book)} title={copy("myReading")}><BookMarked size={17} /></button>}{library.role === "OWNER" && <><button type="button" onClick={() => setLoanManager(book)} title={activeLoan ? copy("manageLoan") : copy("loanBook")}><Handshake size={17} /></button><button type="button" onClick={() => void edit(book.id)} title={copy("editBookLocation")}><Pencil size={17} /></button><button type="button" onClick={() => void remove(book)} title={copy("delete")}><Trash2 size={17} /></button></>}</div></article>; })}{!busy && !books.length && (!filtered && total === 0 && library.role === "OWNER" ? <div className="server-empty-catalogue server-map-onboarding"><span><Layers3 size={34} /></span><p className="server-card-eyebrow">{copy("everyBookPlace")}</p><h4>{copy("buildPhysicalLibrary")}</h4><p>{copy("mapOnboarding")}</p><button type="button" onClick={onSetUpMap}><Layers3 size={17} /> {copy("setUpMap")}</button><small>{copy("skipMap")}</small></div> : <div className="server-empty-catalogue"><BookOpen size={38} /><h4>{copy("noBooksMatch")}</h4><p>{filtered ? copy("tryAnotherFilter") : copy("noCatalogueRecords")}</p></div>)}</div>
    {total > PAGE_SIZE && <nav className="server-pagination" aria-label={copy("cataloguePages")}><button disabled={(query.offset ?? 0) === 0} onClick={() => page(Math.max(0, (query.offset ?? 0) - PAGE_SIZE))}><ChevronLeft size={17} /> {copy("previous")}</button><span>{Math.floor((query.offset ?? 0) / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}</span><button disabled={(query.offset ?? 0) + PAGE_SIZE >= total} onClick={() => page((query.offset ?? 0) + PAGE_SIZE)}>{copy("next")} <ChevronRight size={17} /></button></nav>}
    {details && <BookDetails libraryId={library.library_id} book={details} location={locationLabel(physical, details.id)} reading={detailsReading} perspectiveName={selectedPerspective?.username} reviews={detailsReviews} loans={detailsLoans} onClose={() => setDetails(null)} onEdit={library.role === "OWNER" ? () => void edit(details.id) : null} />}{editing && <BookEditor key={editorSequence} libraryId={library.library_id} initial={editing.book} initialCover={editing.cover} roles={options.contributor_roles} options={options} physical={physical} bookId={editing.id} initialPlacement={batchMode ? batchPlacement : null} batchMode={batchMode} scanFlow={scanFlow} batchAddedCount={batchAddedCount} onOpenExisting={(bookId) => { setEditing(null); setBatchMode(false); setScanFlow(false); void openDetails(bookId); }} onClose={() => { setEditing(null); setBatchMode(false); setScanFlow(false); setBatchPlacement(null); setBatchAddedCount(0); }} onSave={save} />}
    {readingAction && <ReadingActionDialog libraryId={library.library_id} book={readingAction.book} reading={readingAction.reading} onClose={() => setReadingAction(null)} onChanged={refreshPersonalData} />}
    {readingManager && <ReadingManager libraryId={library.library_id} book={readingManager} onClose={() => setReadingManager(null)} onChanged={refreshPersonalData} />}
    {loanManager && <LoanManager libraryId={library.library_id} book={loanManager} onClose={() => setLoanManager(null)} onChanged={refreshLoanData} />}
  </section>;
}
