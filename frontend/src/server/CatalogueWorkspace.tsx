import { type FormEvent, useCallback, useEffect, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Eye,
  Pencil,
  Plus,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import {
  type CatalogueMetadataOptions,
  type CatalogueQuery,
  type LibrarySummary,
  type ServerBook,
  type ServerBookSummary,
  type ServerBookWrite,
  ServerApiError,
  serverApi,
} from "./serverApi";


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

function message(error: unknown): string {
  return error instanceof ServerApiError
    ? error.message
    : error instanceof Error
      ? error.message
      : "BOOKPILE could not reach the server. Please try again.";
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

function MultiSelect({ label, values, selected, onChange }: {
  label: string;
  values: string[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  return <label>{label}<select multiple value={selected} onChange={(event) => onChange(
    Array.from(event.currentTarget.selectedOptions, (option) => option.value),
  )}>{values.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>;
}

function CoverImage({ libraryId, book }: { libraryId: string; book: ServerBookSummary }) {
  return book.cover
    ? <img className="server-book-cover" src={serverApi.coverUrl(libraryId, book.id, book.cover.updated_at)} alt={`Cover of ${book.title}`} />
    : <span className="server-book-placeholder"><BookOpen size={20} /></span>;
}

export function BookDetails({ libraryId, book, onClose, onEdit }: {
  libraryId: string;
  book: ServerBook;
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
  ];
  return <div className="server-modal-backdrop"><section className="server-catalogue-dialog details" role="dialog" aria-modal="true">
    <button className="server-dialog-close" type="button" onClick={onClose} aria-label="Close"><X /></button>
    <p className="server-card-eyebrow">Read-only catalogue record</p>
    <div className="server-book-details-heading"><CoverImage libraryId={libraryId} book={book} /><div><h2>{book.title}</h2><p className="server-book-author">{book.display_author}</p></div></div>
    {!!book.contributors.length && <section><h3>Contributors</h3><div className="server-contributor-credits">{book.contributors.map((item) => <span key={item.id}><b>{item.role_label}</b>{item.name}</span>)}</div></section>}
    <dl className="server-book-metadata">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value === null || value === "" ? "Not recorded" : String(value).replaceAll("_", " ")}</dd></div>)}</dl>
    <div className="server-dialog-actions"><button type="button" onClick={onClose}>Close</button>{onEdit && <button className="confirm" type="button" onClick={onEdit}><Pencil size={16} /> Edit book</button>}</div>
  </section></div>;
}

function BookEditor({ initial, initialCover, roles, options, onClose, onSave }: {
  initial: ServerBookWrite;
  initialCover: ServerBook["cover"];
  roles: CatalogueMetadataOptions["contributor_roles"];
  options: CatalogueMetadataOptions;
  onClose: () => void;
  onSave: (book: ServerBookWrite, cover: File | null, removeCover: boolean, reportProgress: (message: string) => void) => Promise<void>;
}) {
  const [draft, setDraft] = useState<ServerBookWrite>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [removeCover, setRemoveCover] = useState(false);
  const [coverPreview, setCoverPreview] = useState<string | null>(null);
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
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setProgress("Saving book…");
    try { await onSave(draft, coverFile, removeCover, setProgress); } catch (caught) { setError(message(caught)); setBusy(false); setProgress(""); }
  }
  return <div className="server-modal-backdrop"><section className="server-catalogue-dialog editor" role="dialog" aria-modal="true">
    <button className="server-dialog-close" type="button" onClick={onClose} aria-label="Close" disabled={busy}><X /></button>
    <p className="server-card-eyebrow">Shared catalogue record</p><h2>{initial.title ? "Edit book" : "Add a book"}</h2>
    {error && <div className="server-message error">{error}</div>}
    <form onSubmit={submit} className="server-book-form">
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
      <fieldset><legend>Library notes</legend><div className="server-form-grid">
        <label className="wide">Notes<textarea rows={4} maxLength={4000} value={draft.notes ?? ""} onChange={(e) => text("notes", e.target.value)} /></label>
      </div></fieldset>
      <datalist id="server-publishers">{options.publishers.map((v) => <option key={v} value={v} />)}</datalist><datalist id="server-genres">{options.genres.map((v) => <option key={v} value={v} />)}</datalist><datalist id="server-series">{options.series_names.map((v) => <option key={v} value={v} />)}</datalist><datalist id="server-languages">{options.languages.map((v) => <option key={v} value={v} />)}</datalist><datalist id="server-original-languages">{options.original_languages.map((v) => <option key={v} value={v} />)}</datalist>
      {progress && <div className="server-save-progress" role="status">{progress}<small>{progress.startsWith("Processing") ? "Large phone photos can take several seconds. Please keep this window open." : ""}</small></div>}
      <div className="server-dialog-actions"><button type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="confirm" disabled={busy} type="submit">{busy ? "Please wait…" : "Save book"}</button></div>
    </form>
  </section></div>;
}

export default function CatalogueWorkspace({ library }: { library: LibrarySummary }) {
  const [books, setBooks] = useState<ServerBookSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState<CatalogueQuery>({ limit: PAGE_SIZE, offset: 0, sort_by: "title", sort_order: "asc" });
  const [draftQuery, setDraftQuery] = useState<CatalogueQuery>(query);
  const [options, setOptions] = useState(EMPTY_OPTIONS);
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [details, setDetails] = useState<ServerBook | null>(null);
  const [editing, setEditing] = useState<{ id: string | null; book: ServerBookWrite; cover: ServerBook["cover"] } | null>(null);

  const load = useCallback(async (next: CatalogueQuery) => {
    setBusy(true); setError("");
    try { const page = await serverApi.catalogue(library.library_id, next); setBooks(page.books); setTotal(page.total); }
    catch (caught) { setError(message(caught)); }
    finally { setBusy(false); }
  }, [library.library_id]);

  useEffect(() => {
    const initial = { limit: PAGE_SIZE, offset: 0, sort_by: "title", sort_order: "asc" as const };
    setQuery(initial); setDraftQuery(initial); setDetails(null); setEditing(null);
    void load(initial);
    void serverApi.catalogueOptions(library.library_id).then(setOptions).catch((caught) => setError(message(caught)));
  }, [library.library_id, load]);

  async function requireOptions(): Promise<CatalogueMetadataOptions> {
    if (options.contributor_roles.length) return options;
    const loaded = await serverApi.catalogueOptions(library.library_id);
    if (!loaded.contributor_roles.length) {
      throw new Error("Contributor roles are unavailable. Please reload and try again.");
    }
    setOptions(loaded);
    return loaded;
  }
  async function add() {
    setError("");
    try { await requireOptions(); setEditing({ id: null, book: { ...EMPTY_BOOK, contributors: [] }, cover: null }); }
    catch (caught) { setError(message(caught)); }
  }
  function apply(event?: FormEvent) { event?.preventDefault(); const next = { ...draftQuery, limit: PAGE_SIZE, offset: 0 }; setQuery(next); void load(next); }
  function page(offset: number) { const next = { ...query, offset }; setQuery(next); setDraftQuery(next); void load(next); }
  async function openDetails(bookId: string) { setBusy(true); try { setDetails(await serverApi.book(library.library_id, bookId)); } catch (caught) { setError(message(caught)); } finally { setBusy(false); } }
  async function edit(bookId: string) { setBusy(true); try { const [book] = await Promise.all([serverApi.book(library.library_id, bookId), requireOptions()]); setDetails(null); setEditing({ id: book.id, book: writeFromBook(book), cover: book.cover }); } catch (caught) { setError(message(caught)); } finally { setBusy(false); } }
  async function save(book: ServerBookWrite, coverFile: File | null, removeCover: boolean, reportProgress: (message: string) => void) {
    const wasNew = !editing?.id;
    const saved = editing?.id
      ? await serverApi.updateBook(library.library_id, editing.id, book)
      : await serverApi.createBook(library.library_id, book);
    if (wasNew) setEditing({ id: saved.id, book: writeFromBook(saved), cover: saved.cover });
    try {
      if (coverFile) {
        reportProgress("Processing private cover…");
        await serverApi.uploadCover(library.library_id, saved.id, coverFile);
      } else if (removeCover && saved.cover) {
        reportProgress("Removing private cover…");
        await serverApi.deleteCover(library.library_id, saved.id);
      }
    } catch (caught) {
      if (wasNew) throw new Error(`Book added, but its cover was not saved. ${message(caught)} You can retry without creating the book again.`);
      throw caught;
    }
    setEditing(null);
    setNotice(wasNew ? "Book and private cover saved." : "Book updated.");
    await Promise.all([load(query), serverApi.catalogueOptions(library.library_id).then(setOptions)]);
  }
  async function remove(book: ServerBookSummary) { if (!window.confirm(`Permanently delete “${book.title}”? This cannot be undone.`)) return; try { await serverApi.deleteBook(library.library_id, book.id, book.title); setNotice("Book permanently deleted."); await load(query); } catch (caught) { setError(message(caught)); } }

  return <section className="server-catalogue-workspace">
    <header><div><p className="server-card-eyebrow">Shared catalogue</p><h3>Your books</h3><small>{total} {total === 1 ? "book" : "books"} match</small></div>{library.role === "OWNER" && <button className="server-primary-action" type="button" onClick={() => void add()}><Plus size={17} /> Add book</button>}</header>
    {error && <div className="server-message error">{error}</div>}{notice && <div className="server-message success">{notice}</div>}
    <form className="server-catalogue-search" onSubmit={apply}><label><Search size={18} /><input value={draftQuery.search ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, search: e.target.value })} placeholder="Search title, author, contributor or series" /></label><button type="submit">Search</button><button type="button" className={advanced ? "active" : ""} onClick={() => setAdvanced(!advanced)}><SlidersHorizontal size={17} /> Advanced</button></form>
    {advanced && <form className="server-advanced-search" onSubmit={apply}>
      <label>ISBN<input value={draftQuery.isbn ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, isbn: e.target.value })} /></label>
      <MultiSelect label="Languages" values={options.languages} selected={draftQuery.language ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, language: value })} /><MultiSelect label="Original languages" values={options.original_languages} selected={draftQuery.original_language ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, original_language: value })} /><MultiSelect label="Genres" values={options.genres} selected={draftQuery.genre ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, genre: value })} /><MultiSelect label="Publishers" values={options.publishers} selected={draftQuery.publisher ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, publisher: value })} /><MultiSelect label="Series" values={options.series_names} selected={draftQuery.series_name ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, series_name: value })} />
      <MultiSelect label="Translation" values={["UNKNOWN", "ORIGINAL", "TRANSLATED"]} selected={draftQuery.translation_status ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, translation_status: value })} /><MultiSelect label="Category" values={["FICTION", "NON_FICTION"]} selected={draftQuery.fiction_category ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, fiction_category: value })} /><MultiSelect label="Binding" values={["HARDCOVER", "PAPERBACK", "FLEXIBOUND", "SPIRAL", "STAPLED", "OTHER"]} selected={draftQuery.binding ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, binding: value })} /><MultiSelect label="Publication type" values={["CONVENTIONAL_BOOK", "COMIC_GRAPHIC_NOVEL", "ATLAS", "REFERENCE", "ART_PHOTOGRAPHY_ILLUSTRATED", "MAGAZINE_PERIODICAL", "OTHER"]} selected={draftQuery.publication_type ?? []} onChange={(value) => setDraftQuery({ ...draftQuery, publication_type: value })} />
      <label>Series membership<select value={draftQuery.series_state ?? "ANY"} onChange={(e) => setDraftQuery({ ...draftQuery, series_state: e.target.value as CatalogueQuery["series_state"] })}><option value="ANY">Any</option><option value="YES">In a series</option><option value="NO">Not in a series</option></select></label><label>Authors<select value={draftQuery.author_structure ?? "ANY"} onChange={(e) => setDraftQuery({ ...draftQuery, author_structure: e.target.value as CatalogueQuery["author_structure"] })}><option value="ANY">Any</option><option value="SINGLE">Single author</option><option value="MULTIPLE">Multiple authors</option></select></label>
      <label>Minimum pages<input type="number" min="1" value={draftQuery.page_min ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, page_min: numberValue(e.target.value) ?? undefined })} /></label><label>Maximum pages<input type="number" min="1" value={draftQuery.page_max ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, page_max: numberValue(e.target.value) ?? undefined })} /></label>
      <label>Year field<select value={draftQuery.year_field ?? "current_ed_year"} onChange={(e) => setDraftQuery({ ...draftQuery, year_field: e.target.value as CatalogueQuery["year_field"] })}><option value="current_ed_year">Current edition</option><option value="original_publication_year">Original publication</option></select></label><label>Minimum year<input type="number" min="1000" max="9999" value={draftQuery.year_min ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, year_min: numberValue(e.target.value) ?? undefined })} /></label><label>Maximum year<input type="number" min="1000" max="9999" value={draftQuery.year_max ?? ""} onChange={(e) => setDraftQuery({ ...draftQuery, year_max: numberValue(e.target.value) ?? undefined })} /></label>
      <label>Sort by<select value={draftQuery.sort_by ?? "title"} onChange={(e) => setDraftQuery({ ...draftQuery, sort_by: e.target.value })}>{[["title", "Title"], ["author", "Author"], ["created_at", "Date added"], ["updated_at", "Last updated"], ["page_count", "Pages"], ["publisher", "Publisher"], ["current_ed_year", "Edition year"], ["original_publication_year", "Original year"], ["acquisition_date", "Acquisition date"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Direction<select value={draftQuery.sort_order ?? "asc"} onChange={(e) => setDraftQuery({ ...draftQuery, sort_order: e.target.value as "asc" | "desc" })}><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
      <div className="server-advanced-actions"><button type="button" onClick={() => { const clear = { limit: PAGE_SIZE, offset: 0, sort_by: "title", sort_order: "asc" as const }; setDraftQuery(clear); setQuery(clear); void load(clear); }}>Clear</button><button className="confirm" type="submit">Apply filters</button></div>
    </form>}
    <div className={`server-book-list ${busy ? "loading" : ""}`}>{books.map((book) => <article key={book.id}><CoverImage libraryId={library.library_id} book={book} /><div><h4>{book.title}</h4><p>{book.display_author}</p><small>{[book.publisher, book.current_ed_year, book.language, book.page_count ? `${book.page_count} pages` : null].filter(Boolean).join(" · ") || "No optional metadata recorded"}</small></div><div className="server-book-row-actions"><button type="button" onClick={() => void openDetails(book.id)} title="Complete information"><Eye size={17} /></button>{library.role === "OWNER" && <><button type="button" onClick={() => void edit(book.id)} title="Edit"><Pencil size={17} /></button><button type="button" onClick={() => void remove(book)} title="Delete"><Trash2 size={17} /></button></>}</div></article>)}{!busy && !books.length && <div className="server-empty-catalogue"><BookOpen size={38} /><h4>No books match</h4><p>{total ? "Try another page or filter." : library.role === "OWNER" ? "Add the first book to this library." : "This library has no catalogue records yet."}</p></div>}</div>
    {total > PAGE_SIZE && <nav className="server-pagination" aria-label="Catalogue pages"><button disabled={(query.offset ?? 0) === 0} onClick={() => page(Math.max(0, (query.offset ?? 0) - PAGE_SIZE))}><ChevronLeft size={17} /> Previous</button><span>{Math.floor((query.offset ?? 0) / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}</span><button disabled={(query.offset ?? 0) + PAGE_SIZE >= total} onClick={() => page((query.offset ?? 0) + PAGE_SIZE)}>Next <ChevronRight size={17} /></button></nav>}
    {details && <BookDetails libraryId={library.library_id} book={details} onClose={() => setDetails(null)} onEdit={library.role === "OWNER" ? () => void edit(details.id) : null} />}{editing && <BookEditor initial={editing.book} initialCover={editing.cover} roles={options.contributor_roles} options={options} onClose={() => setEditing(null)} onSave={save} />}
  </section>;
}
