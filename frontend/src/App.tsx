import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRightLeft,
  BookOpen,
  BookPlus,
  Check,
  ExternalLink,
  LibraryBig,
  MapPin,
  Pencil,
  Plus,
  Search,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import { api } from "./api";
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
  const [showLibrary, setShowLibrary] = useState(false);
  const [showReorganize, setShowReorganize] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextBooks, nextStats, nextLibrary] = await Promise.all([
        api.books(filter, debouncedSearch),
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
  }, [filter, debouncedSearch]);

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
          <button className="ghost-button" onClick={() => setShowLibrary(true)}>
            <Settings2 size={17} /> Library layout
          </button>
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
        </div>

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
                <div className={`book-spine ${book.status.toLowerCase()}`}>
                  {book.title.slice(0, 1).toUpperCase()}
                </div>
                <div className="book-main">
                  <div>
                    <h3>{book.title}</h3>
                    <p>{book.author}</p>
                    <BookDates book={book} />
                  </div>
                  <span className={`status ${book.status.toLowerCase()}`}>
                    {statusLabel(book.status)}
                  </span>
                </div>
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
    </main>
  );
}

function statusLabel(status: "ALL" | BookStatus) {
  if (status === "ALL") return "All";
  if (status === "PENDING") return "Pending";
  if (status === "CURRENTLY_READING") return "Currently reading";
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
  onClose,
  onSaved,
}: {
  book: Book | null;
  library: Bookcase[];
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
      if (book) await api.updateBook(book.id, payload);
      else await api.createBook(payload);
      await onSaved();
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
          <div><p className="eyebrow dark">{book ? "Update catalogue" : "New arrival"}</p>
          <h2>{book ? "Edit book" : "Add a book"}</h2></div>
          <button className="icon-button" onClick={onClose}><X /></button>
        </div>
        <form onSubmit={(event) => void submit(event)}>
          <div className="form-grid">
            <label className="wide">Title
              <input required autoFocus value={form.title}
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
          <div className="dialog-actions">
            <button type="button" className="text-button" onClick={onClose}>Cancel</button>
            <button className="primary-button" disabled={saving}>
              {saving ? "Saving…" : book ? "Save changes" : "Add to BOOKPILE"}
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
      setAllBooks(await api.books("ALL", ""));
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

export default App;
