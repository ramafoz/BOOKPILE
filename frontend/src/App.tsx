import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRightLeft,
  BookOpen,
  BookPlus,
  Camera,
  Check,
  DatabaseBackup,
  Download,
  ExternalLink,
  FileSpreadsheet,
  LibraryBig,
  ListPlus,
  MapPin,
  Pencil,
  Plus,
  Search,
  Settings2,
  SlidersHorizontal,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { ApiError, api, type RestoreInspection } from "./api";
import type {
  Book,
  BookPayload,
  Bookcase,
  BookStatus,
  ContainerType,
  Layer,
  Stats,
} from "./types";

const emptyStats: Stats = {
  total: 0,
  pending: 0,
  currently_reading: 0,
  read: 0,
};
const emptyBook: BookPayload = {
  title: "",
  author: "",
  status: "PENDING",
  goodreads_url: null,
  notes: null,
  acquisition_date: null,
  reading_started_date: null,
  read_date: null,
  is_original_collection: false,
  container_id: null,
  position: null,
};

function App() {
  const [books, setBooks] = useState<Book[]>([]);
  const [stats, setStats] = useState(emptyStats);
  const [library, setLibrary] = useState<Bookcase[]>([]);
  const [filter, setFilter] = useState<"ALL" | BookStatus>("ALL");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [editing, setEditing] = useState<Book | null | undefined>(undefined);
  const [batchAdding, setBatchAdding] = useState(false);
  const [showLibrary, setShowLibrary] = useState(false);
  const [showReorganize, setShowReorganize] = useState(false);
  const [showData, setShowData] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [sortBy, setSortBy] = useState("title");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [bookcaseFilter, setBookcaseFilter] = useState("");
  const [shelfFilter, setShelfFilter] = useState("");
  const [containerFilter, setContainerFilter] = useState("");
  const [dateField, setDateField] = useState("acquisition_date");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextBooks, nextStats, nextLibrary] = await Promise.all([
        api.books({
          status: filter,
          search: debouncedSearch,
          sortBy,
          sortOrder,
          bookcaseId: bookcaseFilter,
          shelfId: shelfFilter,
          containerId: containerFilter,
          dateField,
          dateFrom,
          dateTo,
        }),
        api.stats(),
        api.library(),
      ]);
      setBooks(nextBooks);
      setStats(nextStats);
      setLibrary(nextLibrary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load BOOKPILE");
    } finally {
      setLoading(false);
    }
  }, [
    filter,
    debouncedSearch,
    sortBy,
    sortOrder,
    bookcaseFilter,
    shelfFilter,
    containerFilter,
    dateField,
    dateFrom,
    dateTo,
  ]);

  const filterShelves = useMemo(
    () =>
      library
        .filter((bookcase) => !bookcaseFilter || bookcase.id === Number(bookcaseFilter))
        .flatMap((bookcase) =>
          bookcase.shelves.map((shelf) => ({
            ...shelf,
            bookcaseName: bookcase.name,
          })),
        ),
    [library, bookcaseFilter],
  );
  const filterContainers = useMemo(
    () =>
      filterShelves
        .filter((shelf) => !shelfFilter || shelf.id === Number(shelfFilter))
        .flatMap((shelf) =>
          shelf.containers.map((container) => ({
            ...container,
            label: `${shelf.bookcaseName} · Shelf ${shelf.shelf_number} · ${
              container.layer === "BACKGROUND" ? "Background" : "Foreground"
            } ${container.container_type === "ROW" ? "Row" : "Pile"} ${
              container.container_number
            }`,
          })),
        ),
    [filterShelves, shelfFilter],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function removeBook(book: Book) {
    if (!window.confirm(`Remove “${book.title}” from your library?`)) return;
    try {
      await api.deleteBook(book.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete book");
    }
  }

  return (
    <main>
      <header className="hero">
        <nav>
          <a className="brand" href="#">
            <span className="brand-mark"><LibraryBig size={22} /></span>
            BOOKPILE
          </a>
          <div className="nav-actions">
            <button className="ghost-button" onClick={() => setShowData(true)}>
              <DatabaseBackup size={17} /> Data & backups
            </button>
            <button className="ghost-button" onClick={() => setShowLibrary(true)}>
              <Settings2 size={17} /> Library layout
            </button>
          </div>
        </nav>
        <div className="hero-copy">
          <p className="eyebrow">Your personal library, mapped</p>
          <h1>Every book has<br />its place.</h1>
          <p className="intro">
            Keep track of what you own, what you have read, and exactly where
            to find it.
          </p>
          <button className="primary-button" onClick={() => setEditing(null)}>
            <BookPlus size={18} /> Add a book
          </button>
        </div>
        <div className="shelf-art" aria-hidden="true">
          <span className="book b1" /><span className="book b2" />
          <span className="book b3" /><span className="book b4" />
          <span className="book b5" /><span className="book b6" />
          <span className="shelf-line" />
        </div>
      </header>

      <section className="content">
        <div className="stats-grid">
          <StatCard icon={<LibraryBig />} label="Total books" value={stats.total} tone="green" />
          <StatCard icon={<BookOpen />} label="Waiting to be read" value={stats.pending} tone="ochre" />
          <StatCard icon={<BookOpen />} label="Currently reading" value={stats.currently_reading} tone="blue" />
          <StatCard icon={<Check />} label="Books read" value={stats.read} tone="clay" />
        </div>

        <div className="catalogue-heading">
          <div>
            <p className="eyebrow dark">The catalogue</p>
            <h2>Your books</h2>
          </div>
          <div className="heading-actions">
            <button className="outline-button" onClick={() => setBatchAdding(true)}>
              <ListPlus size={17} /> Batch add
            </button>
            <button className="outline-button" onClick={() => setShowReorganize(true)}>
              <ArrowRightLeft size={17} /> Reorganize books
            </button>
            <button className="secondary-button" onClick={() => setEditing(null)}>
              <Plus size={17} /> Add book
            </button>
          </div>
        </div>

        <div className="toolbar">
          <div className="search-box">
            <Search size={18} />
            <input
              aria-label="Search books"
              placeholder="Search by title or author…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="filters" aria-label="Filter books">
            {(["ALL", "PENDING", "CURRENTLY_READING", "READ"] as const).map((item) => (
              <button
                className={filter === item ? "active" : ""}
                key={item}
                onClick={() => setFilter(item)}
              >
                {statusLabel(item)}
              </button>
            ))}
          </div>
          <button
            className={`advanced-toggle ${showAdvanced ? "active" : ""}`}
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            <SlidersHorizontal size={17} /> Sort & filter
          </button>
        </div>
        {showAdvanced && (
          <div className="advanced-filters">
            <label>Sort by
              <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
                <option value="title">Title</option>
                <option value="author">Author</option>
                <option value="physical">Physical position</option>
                <option value="acquisition_date">Acquisition date</option>
                <option value="reading_started_date">Reading started</option>
                <option value="read_date">Finished reading</option>
                <option value="created_at">Added to BOOKPILE</option>
              </select>
            </label>
            <label>Direction
              <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value as "asc" | "desc")}>
                <option value="asc">Ascending</option>
                <option value="desc">Descending</option>
              </select>
            </label>
            <label>Bookcase
              <select
                value={bookcaseFilter}
                onChange={(event) => {
                  setBookcaseFilter(event.target.value);
                  setShelfFilter("");
                  setContainerFilter("");
                }}
              >
                <option value="">All bookcases</option>
                {library.map((bookcase) => (
                  <option key={bookcase.id} value={bookcase.id}>{bookcase.name}</option>
                ))}
              </select>
            </label>
            <label>Shelf
              <select
                value={shelfFilter}
                onChange={(event) => {
                  setShelfFilter(event.target.value);
                  setContainerFilter("");
                }}
              >
                <option value="">All shelves</option>
                {filterShelves.map((shelf) => (
                  <option key={shelf.id} value={shelf.id}>
                    {shelf.bookcaseName} · Shelf {shelf.shelf_number}
                  </option>
                ))}
              </select>
            </label>
            <label className="wide-filter">Container
              <select value={containerFilter} onChange={(event) => setContainerFilter(event.target.value)}>
                <option value="">All containers</option>
                {filterContainers.map((container) => (
                  <option key={container.id} value={container.id}>{container.label}</option>
                ))}
              </select>
            </label>
            <label>Date type
              <select value={dateField} onChange={(event) => setDateField(event.target.value)}>
                <option value="acquisition_date">Acquisition</option>
                <option value="reading_started_date">Reading started</option>
                <option value="read_date">Finished reading</option>
              </select>
            </label>
            <label>From
              <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
            </label>
            <label>To
              <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            </label>
            <button
              className="clear-filters"
              onClick={() => {
                setSortBy("title");
                setSortOrder("asc");
                setBookcaseFilter("");
                setShelfFilter("");
                setContainerFilter("");
                setDateField("acquisition_date");
                setDateFrom("");
                setDateTo("");
              }}
            >
              Clear advanced filters
            </button>
          </div>
        )}

        {error && <div className="error-banner">{error}</div>}

        <div className="book-list">
          {loading ? (
            <div className="empty-state">Opening the catalogue…</div>
          ) : books.length === 0 ? (
            <div className="empty-state">
              <BookOpen size={32} />
              <h3>No books here yet</h3>
              <p>Add the first one, or change your search and filters.</p>
            </div>
          ) : (
            books.map((book) => (
              <article className="book-row" key={book.id}>
                <span className={`status ${book.status.toLowerCase()}`}>
                  {statusLabel(book.status)}
                </span>
                {book.cover_filename ? (
                  <img
                    className="book-cover-thumb"
                    src={api.coverUrl(book.cover_filename)}
                    alt={`Cover of ${book.title}`}
                  />
                ) : (
                  <div className={`book-spine ${book.status.toLowerCase()}`}>
                    {book.title.slice(0, 1).toUpperCase()}
                  </div>
                )}
                <div className="book-main">
                  <div>
                    <h3 title={book.title}>{book.title}</h3>
                    <p>{book.author}</p>
                    <BookDates book={book} />
                  </div>
                </div>
                <div className="book-side">
                  <div className="location">
                    <MapPin size={16} />
                    <span>
                      {book.status === "CURRENTLY_READING"
                        ? "Currently reading · outside library"
                        : book.location_label ?? "Location not assigned"}
                    </span>
                  </div>
                  <div className="row-actions">
                    {book.goodreads_url && (
                      <a
                        aria-label="Open Goodreads"
                        href={book.goodreads_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <ExternalLink size={17} />
                      </a>
                    )}
                    <button aria-label="Edit book" onClick={() => setEditing(book)}>
                      <Pencil size={17} />
                    </button>
                    <button aria-label="Delete book" onClick={() => void removeBook(book)}>
                      <Trash2 size={17} />
                    </button>
                  </div>
                </div>
              </article>
            ))
          )}
        </div>
      </section>

      {editing !== undefined && (
        <BookDialog
          book={editing}
          library={library}
          onClose={() => setEditing(undefined)}
          onSaved={async () => {
            setEditing(undefined);
            await refresh();
          }}
        />
      )}
      {batchAdding && (
        <BookDialog
          book={null}
          library={library}
          batchMode
          onClose={() => setBatchAdding(false)}
          onSaved={refresh}
        />
      )}
      {showLibrary && (
        <LibraryDialog
          library={library}
          onClose={() => setShowLibrary(false)}
          onChanged={refresh}
        />
      )}
      {showReorganize && (
        <ReorganizeDialog
          library={library}
          onClose={() => setShowReorganize(false)}
          onChanged={refresh}
        />
      )}
      {showData && <DataDialog onClose={() => setShowData(false)} />}
    </main>
  );
}

function statusLabel(status: "ALL" | BookStatus) {
  if (status === "ALL") return "All";
  if (status === "PENDING") return "Pending";
  if (status === "CURRENTLY_READING") return "Reading…";
  return "Read";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function BookDates({ book }: { book: Book }) {
  const dates = [
    book.acquisition_date
      ? `Acquired ${formatDate(book.acquisition_date)}`
      : book.is_original_collection
        ? "Original collection"
        : null,
    book.reading_started_date
      ? `Started ${formatDate(book.reading_started_date)}`
      : null,
    book.read_date ? `Read ${formatDate(book.read_date)}` : null,
  ].filter(Boolean);

  return dates.length ? <small className="book-dates">{dates.join(" · ")}</small> : null;
}

function StatCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: string;
}) {
  return (
    <article className={`stat-card ${tone}`}>
      <div className="stat-icon">{icon}</div>
      <div><strong>{value}</strong><span>{label}</span></div>
    </article>
  );
}

function BookDialog({
  book,
  library,
  batchMode = false,
  onClose,
  onSaved,
}: {
  book: Book | null;
  library: Bookcase[];
  batchMode?: boolean;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [form, setForm] = useState<BookPayload>(
    book
      ? {
          title: book.title,
          author: book.author,
          status: book.status,
          goodreads_url: book.goodreads_url,
          notes: book.notes,
          acquisition_date: book.acquisition_date,
          reading_started_date: book.reading_started_date,
          read_date: book.read_date,
          is_original_collection: book.is_original_collection,
          container_id: book.container_id,
          position: book.position,
        }
      : emptyBook,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [removeCover, setRemoveCover] = useState(false);
  const [coverPreview, setCoverPreview] = useState<string | null>(
    book?.cover_filename ? api.coverUrl(book.cover_filename) : null,
  );
  const [batchMessage, setBatchMessage] = useState("");
  const titleInput = useRef<HTMLInputElement>(null);
  const containers = useMemo(
    () =>
      library.flatMap((bookcase) =>
        bookcase.shelves.flatMap((shelf) =>
          shelf.containers.map((container) => ({
            ...container,
            label: `${bookcase.name} · Shelf ${shelf.shelf_number} · ${
              container.layer === "BACKGROUND" ? "Background" : "Foreground"
            } ${container.container_type === "ROW" ? "Row" : "Pile"} ${
              container.container_number
            }`,
          })),
        ),
      ),
    [library],
  );

  useEffect(() => {
    if (!coverFile) return;
    const preview = URL.createObjectURL(coverFile);
    setCoverPreview(preview);
    return () => URL.revokeObjectURL(preview);
  }, [coverFile]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = {
        ...form,
        goodreads_url: form.goodreads_url || null,
        notes: form.notes || null,
      };
      let savedBook: Book;
      if (book) {
        savedBook = await api.updateBook(book.id, payload);
      } else {
        try {
          savedBook = await api.createBook(payload);
        } catch (err) {
          if (err instanceof ApiError && err.code === "POSITION_OCCUPIED") {
            const detail = err.detail ?? {};
            const occupant = detail.occupant as
              | { title?: string; author?: string }
              | undefined;
            const shiftCount =
              typeof detail.shift_count === "number" ? detail.shift_count : 1;
            const position =
              typeof detail.position === "number" ? detail.position : form.position;
            const lastPosition =
              typeof detail.last_position === "number"
                ? detail.last_position
                : position;
            const approved = window.confirm(
              `Position ${position} is occupied by “${
                occupant?.title ?? "another book"
              }”${occupant?.author ? ` — ${occupant.author}` : ""}.\n\n` +
              `Make room by moving ${shiftCount} ${
                shiftCount === 1 ? "book" : "books"
              } one position (${position}–${lastPosition} → ${
                Number(lastPosition) + 1
              })?`,
            );
            if (!approved) {
              setError("The book was not added. Choose another position.");
              return;
            }
            savedBook = await api.createBook(payload, true);
          } else {
            throw err;
          }
        }
      }
      if (coverFile) {
        await api.uploadCover(savedBook.id, coverFile);
      } else if (removeCover && savedBook.cover_filename) {
        await api.deleteCover(savedBook.id);
      }
      await onSaved();
      if (batchMode && !book) {
        setForm((current) => ({
          ...current,
          title: "",
          author: "",
          goodreads_url: null,
          notes: null,
          reading_started_date: null,
          read_date: null,
          position: current.position === null ? null : current.position + 1,
        }));
        setCoverFile(null);
        setCoverPreview(null);
        setRemoveCover(false);
        setBatchMessage(
          `Added “${savedBook.title}”. Container retained${
            savedBook.position === null
              ? "."
              : `; next position is ${savedBook.position + 1}.`
          }`,
        );
        window.setTimeout(() => titleInput.current?.focus(), 0);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save book");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div className="dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          <div><p className="eyebrow dark">{book ? "Update catalogue" : batchMode ? "Rapid cataloguing" : "New arrival"}</p>
          <h2>{book ? "Edit book" : batchMode ? "Batch add" : "Add a book"}</h2></div>
          <button className="icon-button" onClick={onClose}><X /></button>
        </div>
        <form onSubmit={(event) => void submit(event)}>
          {batchMode && (
            <div className="batch-banner">
              Container, position sequence, status, acquisition date, and
              original-collection setting stay ready for the next book.
            </div>
          )}
          <div className="form-grid">
            <fieldset className="wide cover-field">
              <legend>Cover image</legend>
              <div className="cover-editor">
                {coverPreview && !removeCover ? (
                  <img src={coverPreview} alt="Selected cover preview" />
                ) : (
                  <div className="cover-placeholder"><BookOpen size={28} /></div>
                )}
                <div className="cover-actions">
                  <label className="file-button">
                    <Camera size={17} />
                    {coverPreview && !removeCover ? "Replace cover" : "Take or choose photo"}
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
                      onChange={(event) => {
                        const file = event.target.files?.[0] ?? null;
                        setCoverFile(file);
                        setRemoveCover(false);
                      }}
                    />
                  </label>
                  {coverPreview && !removeCover && (
                    <button
                      type="button"
                      className="remove-cover-button"
                      onClick={() => {
                        setCoverFile(null);
                        setCoverPreview(null);
                        setRemoveCover(true);
                      }}
                    >
                      <Trash2 size={16} /> Remove cover
                    </button>
                  )}
                  <small>JPEG, PNG, WebP or iPhone HEIC · maximum 12 MB. Images are optimized automatically.</small>
                </div>
              </div>
            </fieldset>
            <label className="wide">Title
              <input ref={titleInput} required autoFocus value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </label>
            <label className="wide">Author
              <input required value={form.author}
                onChange={(e) => setForm({ ...form, author: e.target.value })} />
            </label>
            <label>Status
              <select value={form.status}
                onChange={(e) => {
                  const status = e.target.value as BookStatus;
                  const today = new Date().toISOString().slice(0, 10);
                  setForm({
                    ...form,
                    status,
                    ...(status === "CURRENTLY_READING" && !form.reading_started_date
                      ? { reading_started_date: today }
                      : {}),
                    ...(status === "READ" && !form.read_date
                      ? { read_date: today }
                      : {}),
                    ...(status === "CURRENTLY_READING"
                      ? { container_id: null, position: null }
                      : {}),
                  });
                }}>
                <option value="PENDING">Pending</option>
                <option value="CURRENTLY_READING">Currently reading</option>
                <option value="READ">Read</option>
              </select>
            </label>
            <label>Position
              <input type="number" min="1" value={form.position ?? ""}
                disabled={form.status === "CURRENTLY_READING"}
                onChange={(e) => setForm({ ...form, position: e.target.value ? Number(e.target.value) : null })} />
            </label>
            <label className="wide">Physical container
              <select value={form.container_id ?? ""}
                disabled={form.status === "CURRENTLY_READING"}
                onChange={(e) => setForm({ ...form, container_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Not assigned</option>
                {containers.map((container) => (
                  <option key={container.id} value={container.id}>{container.label}</option>
                ))}
              </select>
              {form.status === "CURRENTLY_READING" && (
                <small>Currently-reading books stay outside the physical library map.</small>
              )}
              {containers.length === 0 && <small>Create your library layout first to assign a location.</small>}
            </label>
            <fieldset className="wide date-fields">
              <legend>Book history</legend>
              <label>Acquired
                <input
                  type="date"
                  value={form.acquisition_date ?? ""}
                  onChange={(e) => setForm({
                    ...form,
                    acquisition_date: e.target.value || null,
                  })}
                />
              </label>
              <label>Reading started
                <input
                  type="date"
                  value={form.reading_started_date ?? ""}
                  onChange={(e) => setForm({
                    ...form,
                    reading_started_date: e.target.value || null,
                  })}
                />
              </label>
              <label>Finished reading
                <input
                  type="date"
                  value={form.read_date ?? ""}
                  onChange={(e) => setForm({
                    ...form,
                    read_date: e.target.value || null,
                  })}
                />
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={form.is_original_collection}
                  onChange={(e) => setForm({
                    ...form,
                    is_original_collection: e.target.checked,
                  })}
                />
                Original collection / acquisition date unknown
              </label>
            </fieldset>
            <label className="wide">Goodreads link
              <input type="url" placeholder="https://www.goodreads.com/…"
                value={form.goodreads_url ?? ""}
                onChange={(e) => setForm({ ...form, goodreads_url: e.target.value || null })} />
            </label>
            <label className="wide">Notes
              <textarea rows={3} value={form.notes ?? ""}
                onChange={(e) => setForm({ ...form, notes: e.target.value || null })} />
            </label>
          </div>
          {error && <div className="form-error">{error}</div>}
          {batchMessage && <div className="batch-success">{batchMessage}</div>}
          <div className="dialog-actions">
            <button type="button" className="text-button" onClick={onClose}>
              {batchMode ? "Finish batch" : "Cancel"}
            </button>
            <button className="primary-button" disabled={saving}>
              {saving
                ? "Saving…"
                : book
                  ? "Save changes"
                  : batchMode
                    ? "Add & continue"
                    : "Add to BOOKPILE"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function LibraryDialog({
  library,
  onClose,
  onChanged,
}: {
  library: Bookcase[];
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [bookcaseName, setBookcaseName] = useState("");
  const [selectedBookcase, setSelectedBookcase] = useState("");
  const [shelfNumber, setShelfNumber] = useState(1);
  const shelves = library.flatMap((bookcase) =>
    bookcase.shelves.map((shelf) => ({ ...shelf, bookcaseName: bookcase.name })),
  );
  const [selectedShelf, setSelectedShelf] = useState("");
  const [containerType, setContainerType] = useState<ContainerType>("ROW");
  const [layer, setLayer] = useState<Layer>("BACKGROUND");
  const [containerNumber, setContainerNumber] = useState(1);
  const [error, setError] = useState("");

  async function act(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update layout");
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div className="dialog library-dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          <div><p className="eyebrow dark">Physical map</p><h2>Library layout</h2></div>
          <button className="icon-button" onClick={onClose}><X /></button>
        </div>
        <p className="dialog-intro">Build the physical hierarchy before assigning books: bookcase, shelf, then row or pile.</p>
        <div className="layout-forms">
          <section>
            <span className="step">1</span><h3>Add a bookcase</h3>
            <input placeholder="e.g. Office bookcase" value={bookcaseName}
              onChange={(e) => setBookcaseName(e.target.value)} />
            <button disabled={!bookcaseName.trim()} onClick={() => void act(async () => {
              await api.createBookcase(bookcaseName, "");
              setBookcaseName("");
            })}><Plus size={16} /> Add bookcase</button>
          </section>
          <section>
            <span className="step">2</span><h3>Add a shelf</h3>
            <select value={selectedBookcase} onChange={(e) => setSelectedBookcase(e.target.value)}>
              <option value="">Choose bookcase</option>
              {library.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            <input type="number" min="1" value={shelfNumber}
              onChange={(e) => setShelfNumber(Number(e.target.value))} />
            <button disabled={!selectedBookcase} onClick={() => void act(() =>
              api.createShelf(Number(selectedBookcase), shelfNumber)
            )}><Plus size={16} /> Add shelf</button>
          </section>
          <section>
            <span className="step">3</span><h3>Add a container</h3>
            <select value={selectedShelf} onChange={(e) => setSelectedShelf(e.target.value)}>
              <option value="">Choose shelf</option>
              {shelves.map((item) => <option key={item.id} value={item.id}>
                {item.bookcaseName} · Shelf {item.shelf_number}
              </option>)}
            </select>
            <div className="split">
              <select value={containerType} onChange={(e) => setContainerType(e.target.value as ContainerType)}>
                <option value="ROW">Row</option><option value="PILE">Pile</option>
              </select>
              <select value={layer} onChange={(e) => setLayer(e.target.value as Layer)}>
                <option value="BACKGROUND">Background</option><option value="FOREGROUND">Foreground</option>
              </select>
            </div>
            <input type="number" min="1" value={containerNumber}
              onChange={(e) => setContainerNumber(Number(e.target.value))} />
            <button disabled={!selectedShelf} onClick={() => void act(() =>
              api.createContainer(Number(selectedShelf), containerType, layer, containerNumber)
            )}><Plus size={16} /> Add container</button>
          </section>
        </div>
        {error && <div className="form-error">{error}</div>}
        <div className="layout-tree">
          {library.length === 0 ? <p>No bookcases yet.</p> : library.map((bookcase) => (
            <section className="bookcase-block" key={bookcase.id}>
              <div className="bookcase-heading">
                <div>
                  <strong>{bookcase.name}</strong>
                  <span>
                    {bookcase.shelves.length} shelves ·{" "}
                    {bookcase.shelves.reduce((n, shelf) => n + shelf.containers.length, 0)} containers
                  </span>
                </div>
              </div>
              {bookcase.shelves.length === 0 ? (
                <p className="muted">No shelves in this bookcase.</p>
              ) : bookcase.shelves.map((shelf) => (
                <div className="shelf-block" key={shelf.id}>
                  <div className="shelf-heading">
                    <strong>Shelf {shelf.shelf_number}</strong>
                    <span>{shelf.containers.length} containers</span>
                    <button
                      className="danger-icon"
                      title="Delete shelf"
                      onClick={() => {
                        const bookCount = shelf.containers.reduce(
                          (total, container) => total + container.book_count,
                          0,
                        );
                        if (!window.confirm(
                          `Delete Shelf ${shelf.shelf_number}? ${
                            bookCount
                              ? `${bookCount} books will become unassigned.`
                              : "It contains no assigned books."
                          }`,
                        )) return;
                        void act(() => api.deleteShelf(shelf.id));
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                  <div className="container-list">
                    {shelf.containers.length === 0 ? (
                      <span className="muted">No containers.</span>
                    ) : shelf.containers.map((container) => (
                      <div className="container-chip" key={container.id}>
                        <span>
                          {container.layer === "BACKGROUND" ? "Background" : "Foreground"}{" "}
                          {container.container_type === "ROW" ? "Row" : "Pile"}{" "}
                          {container.container_number}
                        </span>
                        <small>{container.book_count} books</small>
                        <button
                          title="Delete container"
                          onClick={() => {
                            if (!window.confirm(
                              `Delete this container? ${
                                container.book_count
                                  ? `${container.book_count} books will become unassigned.`
                                  : "It contains no assigned books."
                              }`,
                            )) return;
                            void act(() => api.deleteContainer(container.id));
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}

function ReorganizeDialog({
  library,
  onClose,
  onChanged,
}: {
  library: Bookcase[];
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [allBooks, setAllBooks] = useState<Book[]>([]);
  const [selectedBook, setSelectedBook] = useState("");
  const [selectedContainer, setSelectedContainer] = useState("");
  const [position, setPosition] = useState(1);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const containers = useMemo(
    () =>
      library.flatMap((bookcase) =>
        bookcase.shelves.flatMap((shelf) =>
          shelf.containers.map((container) => ({
            ...container,
            label: `${bookcase.name} · Shelf ${shelf.shelf_number} · ${
              container.layer === "BACKGROUND" ? "Background" : "Foreground"
            } ${container.container_type === "ROW" ? "Row" : "Pile"} ${
              container.container_number
            }`,
          })),
        ),
      ),
    [library],
  );

  const loadBooks = useCallback(async () => {
    try {
      setAllBooks(await api.books({
        status: "ALL",
        search: "",
        sortBy: "title",
        sortOrder: "asc",
        bookcaseId: "",
        shelfId: "",
        containerId: "",
        dateField: "acquisition_date",
        dateFrom: "",
        dateTo: "",
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load books");
    }
  }, []);

  useEffect(() => {
    void loadBooks();
  }, [loadBooks]);

  const movableBooks = allBooks.filter(
    (book) => book.status !== "CURRENTLY_READING",
  );
  const chosenBook = movableBooks.find(
    (book) => book.id === Number(selectedBook),
  );

  async function move(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.moveBook(
        Number(selectedBook),
        Number(selectedContainer),
        position,
      );
      await Promise.all([loadBooks(), onChanged()]);
      setSelectedBook("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to move book");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div className="dialog reorganize-dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          <div>
            <p className="eyebrow dark">Change of place</p>
            <h2>Reorganize books</h2>
          </div>
          <button className="icon-button" onClick={onClose}><X /></button>
        </div>
        <p className="dialog-intro">
          Choose a book and its destination. If another book occupies that
          position, BOOKPILE swaps their places automatically.
        </p>
        <form onSubmit={(event) => void move(event)}>
          <div className="move-grid">
            <label>Book
              <select required value={selectedBook} onChange={(event) => setSelectedBook(event.target.value)}>
                <option value="">Choose book</option>
                {movableBooks.map((book) => (
                  <option key={book.id} value={book.id}>
                    {book.title} — {book.author}
                  </option>
                ))}
              </select>
            </label>
            <div className="current-location">
              <MapPin size={17} />
              <span>{chosenBook?.location_label ?? "Current location not assigned"}</span>
            </div>
            <label>Destination container
              <select required value={selectedContainer} onChange={(event) => setSelectedContainer(event.target.value)}>
                <option value="">Choose container</option>
                {containers.map((container) => (
                  <option key={container.id} value={container.id}>
                    {container.label}
                  </option>
                ))}
              </select>
            </label>
            <label>Destination position
              <input
                required
                type="number"
                min="1"
                value={position}
                onChange={(event) => setPosition(Number(event.target.value))}
              />
            </label>
          </div>
          {error && <div className="form-error">{error}</div>}
          <div className="dialog-actions">
            <button type="button" className="text-button" onClick={onClose}>Close</button>
            <button
              className="primary-button"
              disabled={saving || !selectedBook || !selectedContainer}
            >
              <ArrowRightLeft size={17} />
              {saving ? "Moving…" : "Move book"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DataDialog({ onClose }: { onClose: () => void }) {
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [inspection, setInspection] = useState<RestoreInspection | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [restored, setRestored] = useState<{
    safety_backup: string;
    counts: RestoreInspection["counts"];
  } | null>(null);

  async function inspectBackup() {
    if (!restoreFile) return;
    setWorking(true);
    setError("");
    setInspection(null);
    setRestored(null);
    setConfirmed(false);
    try {
      setInspection(await api.inspectRestore(restoreFile));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to inspect backup");
    } finally {
      setWorking(false);
    }
  }

  async function restoreBackup() {
    if (!inspection || !confirmed) return;
    setWorking(true);
    setError("");
    try {
      const result = await api.confirmRestore(inspection.token);
      setRestored({
        safety_backup: result.safety_backup,
        counts: result.counts,
      });
      setInspection(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to restore backup");
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div className="dialog data-dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          <div>
            <p className="eyebrow dark">Catalogue safety</p>
            <h2>Data & backups</h2>
          </div>
          <button className="icon-button" onClick={onClose}><X /></button>
        </div>
        <p className="dialog-intro">
          Download a complete, verified copy before adding more books. Full
          backups include the SQLite catalogue and every cover image.
        </p>
        <div className="data-options">
          <article>
            <div className="data-option-icon"><DatabaseBackup /></div>
            <div>
              <h3>Full BOOKPILE backup</h3>
              <p>
                A ZIP containing the database, covers, integrity metadata, and
                SHA-256 checksums. This is the format intended for restoration.
              </p>
              <a
                className="primary-button"
                href={api.downloadUrl("/exports/full-backup")}
                download
              >
                <Download size={17} /> Download full backup
              </a>
            </div>
          </article>
          <article>
            <div className="data-option-icon csv"><FileSpreadsheet /></div>
            <div>
              <h3>Books as CSV</h3>
              <p>
                A spreadsheet-friendly export with dates, status, Goodreads,
                physical location, and cover references. It does not include images.
              </p>
              <a
                className="outline-button"
                href={api.downloadUrl("/exports/books.csv")}
                download
              >
                <Download size={17} /> Export CSV
              </a>
            </div>
          </article>
          <article className="restore-option">
            <div className="data-option-icon restore"><Upload /></div>
            <div>
              <h3>Restore a full backup</h3>
              <p>
                Select a BOOKPILE ZIP. It will be fully validated before you
                are offered the option to replace the current catalogue.
              </p>
              <div className="restore-picker">
                <label className="file-button restore-file-button">
                  <Upload size={17} />
                  Choose backup ZIP
                  <input
                    type="file"
                    accept=".zip,application/zip"
                    onChange={(event) => {
                      setRestoreFile(event.target.files?.[0] ?? null);
                      setInspection(null);
                      setRestored(null);
                      setConfirmed(false);
                      setError("");
                    }}
                  />
                </label>
                <span>{restoreFile?.name ?? "No backup selected"}</span>
              </div>
              <button
                type="button"
                className="outline-button"
                disabled={!restoreFile || working}
                onClick={() => void inspectBackup()}
              >
                {working && !inspection ? "Validating…" : "Inspect backup"}
              </button>
            </div>
          </article>
        </div>
        {error && <div className="form-error">{error}</div>}
        {inspection && (
          <section className="restore-confirmation">
            <p className="eyebrow dark">Validated backup</p>
            <h3>{new Date(inspection.created_at).toLocaleString()}</h3>
            <div className="restore-counts">
              <span><strong>{inspection.counts.books}</strong> books</span>
              <span><strong>{inspection.counts.covers}</strong> covers</span>
              <span><strong>{inspection.counts.bookcases}</strong> bookcases</span>
              <span><strong>{inspection.counts.shelves}</strong> shelves</span>
              <span><strong>{inspection.counts.containers}</strong> containers</span>
            </div>
            <p>
              Checksums, SQLite integrity, foreign keys, record counts, and
              cover files are valid.
            </p>
            <label className="restore-check">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              Replace the current catalogue with this validated backup.
              BOOKPILE will first create an automatic safety backup.
            </label>
            <button
              type="button"
              className="danger-button"
              disabled={!confirmed || working}
              onClick={() => void restoreBackup()}
            >
              {working ? "Restoring…" : "Restore this backup"}
            </button>
          </section>
        )}
        {restored && (
          <section className="restore-success">
            <Check size={25} />
            <div>
              <h3>Restore completed</h3>
              <p>
                Restored {restored.counts.books} books and{" "}
                {restored.counts.covers} covers. The catalogue that was
                replaced is preserved as <strong>{restored.safety_backup}</strong>.
              </p>
              <button
                type="button"
                className="primary-button"
                onClick={() => window.location.reload()}
              >
                Reload BOOKPILE
              </button>
            </div>
          </section>
        )}
        <div className="data-note">
          Restore never changes the catalogue during inspection. Replacement
          only happens after validation and explicit confirmation.
        </div>
      </div>
    </div>
  );
}

export default App;
