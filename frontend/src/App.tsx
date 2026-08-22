import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowRightLeft,
  ArrowUp,
  BarChart3,
  BookOpen,
  BookDown,
  BookUp,
  BookPlus,
  Camera,
  Check,
  ChevronDown,
  ChevronUp,
  Clock3,
  DatabaseBackup,
  Download,
  ExternalLink,
  FileSpreadsheet,
  Focus,
  GalleryVerticalEnd,
  Info,
  LibraryBig,
  ListPlus,
  LoaderCircle,
  MapPin,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  ScanBarcode,
  Search,
  Settings2,
  Shuffle,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Upload,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { ApiError, api, type RestoreInspection } from "./api";
import { decodeIsbnBarcodePhoto } from "./barcode";
import { readCoverText, type CoverOcrProgress } from "./ocr";
import { MetadataFilterFields } from "./MetadataFilterFields";
import {
  boundsForMapRects,
  fitMapBounds,
  fitMapVerticalBounds,
  LEGACY_MAP_ASPECT_RATIO,
  LEGACY_MAP_CAMERA,
  mapCameraTransform,
  mapViewportPointToWorld,
  panMapCamera,
  panMapCameraByPixels,
  zoomMapCamera,
  type MapCamera,
  type MapViewportSize,
  type MapWorldBounds,
} from "./mapCamera";
import {
  containerRectWithoutAbsentBooks,
  effectiveCataloguePageMean,
  proportionalBookSegments,
  proportionalOutsideBookGroups,
  readingIconGrid,
} from "./mapBookGeometry";
import { nextInspectionId } from "./mapInspection";
import type {
  Book,
  BookPayload,
  Bookcase,
  BookStatus,
  Binding,
  CatalogueStatistics,
  BibliographicCandidate,
  CatalogueMatch,
  ContainerType,
  FictionCategory,
  Layer,
  Loan,
  LibraryMapData,
  MapBook,
  MapBookcase,
  MapContainer,
  MapShelf,
  MetadataFilters,
  MetadataOptions,
  ReadingSuggestion,
  NewPositionMode,
  OldPositionMode,
  PublicationType,
  RearrangementOperation,
  RearrangementResult,
  RearrangementStep,
  ISBNLookupResult,
  Stats,
  VisualLayout,
  VisualRect,
} from "./types";

type SuggestionMode = "random" | "oldest" | "waiting";
type AppMenu = "settings" | "add" | "suggestions";
type MapCameraAction =
  | "up" | "down" | "left" | "right"
  | "zoom-in" | "zoom-out";
type MapInspectionMode = "book" | "container" | null;
type CandidateMetadataKey =
  | "title" | "author" | "isbn_10" | "isbn_13" | "subtitle"
  | "page_count" | "publisher" | "current_ed_year"
  | "original_publication_year" | "language" | "edition_number"
  | "fiction_category" | "binding" | "publication_type" | "genre_text"
  | "series_name" | "series_volume";

const emptyStats: Stats = {
  total: 0,
  pending: 0,
  currently_reading: 0,
  currently_rereading: 0,
  read: 0,
};
const emptyMetadataOptions: MetadataOptions = {
  languages: [],
  genres: [],
  publishers: [],
  series_names: [],
  fiction_categories: [],
  bindings: [],
  publication_types: [],
};
function emptyMetadataFilters(): MetadataFilters {
  return {
    isbn: "",
    languages: [],
    genres: [],
    publishers: [],
    fictionCategories: [],
    bindings: [],
    publicationTypes: [],
    seriesNames: [],
    seriesState: "ANY",
    authorStructure: "ANY",
    readingActivity: "ANY",
    pageMin: "",
    pageMax: "",
    publicationYearField: "current_ed_year",
    publicationYearMin: "",
    publicationYearMax: "",
  };
}
const emptyBook: BookPayload = {
  title: "",
  author: "",
  has_multiple_authors: false,
  structured_authors: [],
  isbn_10: null,
  isbn_13: null,
  subtitle: null,
  page_count: null,
  publisher: null,
  current_ed_year: null,
  original_publication_year: null,
  language: null,
  edition_number: null,
  fiction_category: null,
  binding: null,
  publication_type: null,
  genre_text: null,
  series_name: null,
  series_volume: null,
  status: "PENDING",
  goodreads_url: null,
  notes: null,
  acquisition_date: null,
  reading_started_date: null,
  read_date: null,
  is_read_date_unknown: false,
  is_original_collection: false,
  container_id: null,
  position: null,
  current_loan: null,
};

function App() {
  const [books, setBooks] = useState<Book[]>([]);
  const [stats, setStats] = useState(emptyStats);
  const [library, setLibrary] = useState<Bookcase[]>([]);
  const [metadataOptions, setMetadataOptions] = useState(emptyMetadataOptions);
  const [metadataFilters, setMetadataFilters] = useState<MetadataFilters>(
    emptyMetadataFilters,
  );
  const [filter, setFilter] = useState<"ALL" | BookStatus>("ALL");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [editing, setEditing] = useState<Book | null | undefined>(undefined);
  const [detailsBook, setDetailsBook] = useState<Book | null>(null);
  const [authorsBook, setAuthorsBook] = useState<Book | null>(null);
  const [batchAdding, setBatchAdding] = useState(false);
  const [showLibrary, setShowLibrary] = useState(false);
  const [showData, setShowData] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const [showStatistics, setShowStatistics] = useState(false);
  const [activeMenu, setActiveMenu] = useState<AppMenu | null>(null);
  const [suggestionMode, setSuggestionMode] = useState<SuggestionMode | null>(null);
  const [statusActionBook, setStatusActionBook] = useState<Book | null>(null);
  const [loanActionBook, setLoanActionBook] = useState<Book | null>(null);
  const [focusedMapBook, setFocusedMapBook] = useState<Book | null>(null);
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
  const [exactBookFilter, setExactBookFilter] = useState<number | null>(null);
  const [quickView, setQuickView] = useState("");
  const [catalogueCheck, setCatalogueCheck] = useState("");
  const [showCatalogueChecks, setShowCatalogueChecks] = useState(false);
  const [includeUnknownSelectedDates, setIncludeUnknownSelectedDates] =
    useState(false);
  const [includeUnknownSortDates, setIncludeUnknownSortDates] = useState(false);
  const [loanStatus, setLoanStatus] = useState("ANY");
  const [loanedTo, setLoanedTo] = useState("");
  const [loanRecordScope, setLoanRecordScope] = useState<"ACTIVE" | "ANY">("ACTIVE");
  const [loanDateField, setLoanDateField] = useState("loaned_date");
  const [loanDateFrom, setLoanDateFrom] = useState("");
  const [loanDateTo, setLoanDateTo] = useState("");
  const [includeUnknownLoanDates, setIncludeUnknownLoanDates] = useState(false);
  const mapHistoryActive = useRef(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextBooks, nextStats, nextLibrary, nextMetadataOptions] = await Promise.all([
        api.books({
          bookId: exactBookFilter === null ? "" : String(exactBookFilter),
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
          quickView,
          catalogueCheck,
          loanStatus,
          loanedTo,
          loanRecordScope,
          loanDateField,
          loanDateFrom,
          loanDateTo,
          includeUnknownLoanDates,
          includeUnknownSelectedDates,
          includeUnknownSortDates,
          metadata: metadataFilters,
        }),
        api.stats(),
        api.library(),
        api.metadataOptions(),
      ]);
      setBooks(nextBooks);
      setStats(nextStats);
      setLibrary(nextLibrary);
      setMetadataOptions(nextMetadataOptions);
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
    exactBookFilter,
    quickView,
    catalogueCheck,
    includeUnknownSelectedDates,
    includeUnknownSortDates,
    metadataFilters,
    loanStatus,
    loanedTo,
    loanRecordScope,
    loanDateField,
    loanDateFrom,
    loanDateTo,
    includeUnknownLoanDates,
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
    if (!activeMenu) return;
    function closeMenu(event: MouseEvent) {
      if (!(event.target as Element).closest("[data-app-menu]")) {
        setActiveMenu(null);
      }
    }
    function closeMenuWithKeyboard(event: KeyboardEvent) {
      if (event.key === "Escape") setActiveMenu(null);
    }
    document.addEventListener("mousedown", closeMenu);
    document.addEventListener("keydown", closeMenuWithKeyboard);
    return () => {
      document.removeEventListener("mousedown", closeMenu);
      document.removeEventListener("keydown", closeMenuWithKeyboard);
    };
  }, [activeMenu]);

  useEffect(() => {
    if (!showMap) return;
    const marker = "bookpile-library-map";
    if (window.history.state?.bookpileView !== marker) {
      window.history.pushState(
        { ...(window.history.state ?? {}), bookpileView: marker },
        "",
      );
    }
    mapHistoryActive.current = true;
    function closeMapFromBrowserHistory() {
      if (!mapHistoryActive.current) return;
      mapHistoryActive.current = false;
      setShowMap(false);
      setFocusedMapBook(null);
    }
    window.addEventListener("popstate", closeMapFromBrowserHistory);
    return () => window.removeEventListener("popstate", closeMapFromBrowserHistory);
  }, [showMap]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function removeBook(book: Book) {
    const related = [
      book.reading_session_count
        ? `${book.reading_session_count} reading ${book.reading_session_count === 1 ? "session" : "sessions"}`
        : "",
      book.loan_count
        ? `${book.loan_count} loan ${book.loan_count === 1 ? "record" : "records"}`
        : "",
    ].filter(Boolean).join(" and ");
    if (!window.confirm(
      `Permanently remove “${book.title}” from BOOKPILE?` +
      (related ? ` This also deletes ${related}.` : "") +
      " This cannot be undone except by restoring a backup.",
    )) return;
    try {
      await api.deleteBook(book.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete book");
    }
  }

  function closeLibraryMap() {
    if (
      mapHistoryActive.current &&
      window.history.state?.bookpileView === "bookpile-library-map"
    ) {
      mapHistoryActive.current = false;
      window.history.back();
    }
    setShowMap(false);
    setFocusedMapBook(null);
  }

  function openCatalogueAt(
    bookcaseId: number,
    shelfId: number | "" = "",
    containerId: number | "" = "",
  ) {
    setExactBookFilter(null);
    setQuickView("");
    setCatalogueCheck("");
    setShowCatalogueChecks(false);
    setBookcaseFilter(String(bookcaseId));
    setShelfFilter(shelfId ? String(shelfId) : "");
    setContainerFilter(containerId ? String(containerId) : "");
    setMetadataFilters(emptyMetadataFilters());
    setSortBy("physical");
    setSortOrder("asc");
    setShowAdvanced(false);
    closeLibraryMap();
    window.setTimeout(
      () => document.querySelector(".catalogue-heading")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      }),
      0,
    );
  }

  function openReadingCatalogue() {
    setExactBookFilter(null);
    setQuickView("");
    setCatalogueCheck("");
    setShowCatalogueChecks(false);
    setFilter("CURRENTLY_READING");
    setBookcaseFilter("");
    setShelfFilter("");
    setContainerFilter("");
    setMetadataFilters(emptyMetadataFilters());
    setSortBy("title");
    setSortOrder("asc");
    setShowAdvanced(true);
    closeLibraryMap();
    window.setTimeout(
      () => document.querySelector(".catalogue-heading")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      }),
      0,
    );
  }

  function openLoanCatalogue() {
    setExactBookFilter(null);
    setFilter("ALL");
    setQuickView("currently_on_loan");
    setCatalogueCheck("");
    setBookcaseFilter("");
    setShelfFilter("");
    setContainerFilter("");
    setLoanStatus("ON_LOAN");
    setSortBy("loaned_date");
    setSortOrder("asc");
    setShowAdvanced(true);
    closeLibraryMap();
  }

  function openExactBookCatalogue(book: { id: number; title: string }) {
    setExactBookFilter(book.id);
    setFilter("ALL");
    setSearch(book.title);
    setDebouncedSearch(book.title);
    setBookcaseFilter("");
    setShelfFilter("");
    setContainerFilter("");
    setDateFrom("");
    setDateTo("");
    setQuickView("");
    setCatalogueCheck("");
    setShowCatalogueChecks(false);
    setIncludeUnknownSelectedDates(false);
    setIncludeUnknownSortDates(false);
    setMetadataFilters(emptyMetadataFilters());
    setSortBy("title");
    setSortOrder("asc");
    setShowAdvanced(false);
    closeLibraryMap();
    window.setTimeout(
      () => document.querySelector(".catalogue-heading")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      }),
      0,
    );
  }

  function openBookOnMap(book: Book) {
    if (!book.container_id && book.status !== "CURRENTLY_READING" && !book.is_on_loan) return;
    setFocusedMapBook(book);
    setShowMap(true);
  }

  return (
    <main>
      <header className={`hero ${
        activeMenu === "add" || activeMenu === "suggestions"
          ? "hero-menu-open"
          : ""
      }`}>
        <nav>
          <a className="brand" href="#">
            <span className="brand-mark"><LibraryBig size={22} /></span>
            BOOKPILE
          </a>
          <div className="nav-actions">
            <button
              className="ghost-button"
              onClick={() => {
                setFocusedMapBook(null);
                setShowMap(true);
              }}
            >
              <GalleryVerticalEnd size={17} /> Library map
            </button>
            <button className="ghost-button" onClick={() => setShowStatistics(true)}>
              <BarChart3 size={17} /> Statistics
            </button>
            <div className="app-menu" data-app-menu>
              <button
                className="ghost-button menu-trigger"
                aria-haspopup="menu"
                aria-expanded={activeMenu === "settings"}
                onClick={() => setActiveMenu(
                  activeMenu === "settings" ? null : "settings",
                )}
              >
                <Settings2 size={17} /> Settings <ChevronDown size={15} />
              </button>
              {activeMenu === "settings" && (
                <div className="menu-popover nav-menu" role="menu">
                  <button role="menuitem" onClick={() => {
                    setActiveMenu(null);
                    setShowLibrary(true);
                  }}>
                    <Settings2 size={16} /> Customize library layout
                  </button>
                  <button role="menuitem" onClick={() => {
                    setActiveMenu(null);
                    setShowData(true);
                  }}>
                    <DatabaseBackup size={16} /> Data & backups
                  </button>
                </div>
              )}
            </div>
          </div>
        </nav>
        <div className="hero-copy">
          <p className="eyebrow">Your personal library, mapped</p>
          <h1>Every book has<br />its place.</h1>
          <p className="intro">
            Keep track of what you own, what you have read, and exactly where
            to find it.
          </p>
          <div className="hero-actions">
            <div className="app-menu" data-app-menu>
              <button
                className="primary-button menu-trigger"
                aria-haspopup="menu"
                aria-expanded={activeMenu === "add"}
                onClick={() => setActiveMenu(activeMenu === "add" ? null : "add")}
              >
                <BookPlus size={18} /> Add <ChevronDown size={16} />
              </button>
              {activeMenu === "add" && (
                <div className="menu-popover hero-menu" role="menu">
                  <button role="menuitem" onClick={() => {
                    setActiveMenu(null);
                    setEditing(null);
                  }}><Plus size={16} /> Add single book</button>
                  <button role="menuitem" onClick={() => {
                    setActiveMenu(null);
                    setBatchAdding(true);
                  }}><ListPlus size={16} /> Add Batch</button>
                </div>
              )}
            </div>
            <div className="app-menu" data-app-menu>
              <button
                className="hero-secondary-button menu-trigger"
                aria-haspopup="menu"
                aria-expanded={activeMenu === "suggestions"}
                onClick={() => setActiveMenu(
                  activeMenu === "suggestions" ? null : "suggestions",
                )}
              >
                <Sparkles size={18} /> New read <ChevronDown size={16} />
              </button>
              {activeMenu === "suggestions" && (
                <div className="menu-popover hero-menu" role="menu">
                  <button role="menuitem" onClick={() => {
                    setActiveMenu(null);
                    setSuggestionMode("random");
                  }}><Shuffle size={16} /> Random pending book</button>
                  <button role="menuitem" onClick={() => {
                    setActiveMenu(null);
                    setSuggestionMode("oldest");
                  }}><Clock3 size={16} /> Oldest pending book</button>
                  <button role="menuitem" onClick={() => {
                    setActiveMenu(null);
                    setSuggestionMode("waiting");
                  }}><BarChart3 size={16} /> By time spent pending</button>
                </div>
              )}
            </div>
          </div>
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
          <StatCard
            icon={<BookOpen />}
            label="Currently reading"
            value={`${stats.currently_reading || ""}${stats.currently_rereading ? `+${stats.currently_rereading}` : stats.currently_reading ? "" : "0"}`}
            tone="blue"
          />
          <StatCard icon={<Check />} label="Books read" value={stats.read} tone="clay" />
        </div>

        <div className="catalogue-heading">
          <div>
            <p className="eyebrow dark">The catalogue</p>
            <h2>Your books</h2>
            <p className="catalogue-count">
              {loading
                ? "Counting books…"
                : books.length === stats.total
                  ? `${books.length} books shown`
                  : `${books.length} of ${stats.total} books shown`}
            </p>
          </div>
        </div>

        <div className="toolbar">
          <div className="search-box">
            <Search size={18} />
            <input
              aria-label="Search books"
              placeholder="Search by title, author or series…"
              value={search}
              onChange={(event) => {
                setExactBookFilter(null);
                setSearch(event.target.value);
              }}
            />
          </div>
          <div className="filters" aria-label="Filter books">
            {(["ALL", "PENDING", "CURRENTLY_READING", "READ"] as const).map((item) => (
              <button
                className={filter === item ? "active" : ""}
                key={item}
                onClick={() => {
                  setExactBookFilter(null);
                  setFilter(item);
                }}
              >
                {statusLabel(item)}
              </button>
            ))}
          </div>
          <button
            className={`advanced-toggle ${showAdvanced ? "active" : ""}`}
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            <SlidersHorizontal size={17} /> Sort & Advanced Search
          </button>
        </div>
        {showAdvanced && (
          <div className="advanced-filters">
            <label>Sort by
              <select
                value={sortBy}
                onChange={(event) => {
                  const value = event.target.value;
                  setSortBy(value);
                  if (
                    (
                      value === "acquisition_date"
                      && quickView === "original_collection"
                    )
                    || (
                      value === "reading_started_date"
                      && catalogueCheck === "missing_started"
                    )
                    || (
                      value === "read_date"
                      && (
                        quickView === "missing_finished"
                        || catalogueCheck === "missing_end"
                      )
                    )
                  ) {
                    setIncludeUnknownSortDates(true);
                  }
                }}
              >
                <option value="title">Title</option>
                <option value="author">Author</option>
                <option value="physical">Physical position</option>
                <option value="acquisition_date">Acquisition date</option>
                <option value="reading_started_date">Reading started</option>
                <option value="read_date">Finished reading</option>
                <option value="loaned_date">Loan date</option>
                <option value="expected_return_date">Expected return date</option>
                <option value="returned_date">Returned date</option>
                <option value="created_at">Added to BOOKPILE</option>
              </select>
            </label>
            <label>Direction
              <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value as "asc" | "desc")}>
                <option value="asc">Ascending</option>
                <option value="desc">Descending</option>
              </select>
            </label>
            <label>Quick view
              <select
                value={quickView}
                onChange={(event) => {
                  const value = event.target.value;
                  setExactBookFilter(null);
                  setQuickView(value);
                  setCatalogueCheck("");
                  setShowCatalogueChecks(false);
                  setFilter(value === "missing_finished" ? "READ" : "ALL");
                  setLoanStatus(
                    value === "currently_on_loan" ? "ON_LOAN"
                      : value === "overdue_loans" ? "OVERDUE" : "ANY",
                  );
                  if (
                    (
                      value === "original_collection"
                      && sortBy === "acquisition_date"
                    )
                    || (
                      value === "missing_finished"
                      && sortBy === "read_date"
                    )
                  ) {
                    setIncludeUnknownSortDates(true);
                  }
                }}
              >
                <option value="">All catalogue data</option>
                <option value="missing_finished">Read · finished date unknown</option>
                <option value="original_collection">Original Collection</option>
                <option value="currently_on_loan">Currently on loan</option>
                <option value="overdue_loans">Overdue loans</option>
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
            <label>Container
              <select value={containerFilter} onChange={(event) => setContainerFilter(event.target.value)}>
                <option value="">All containers</option>
                {filterContainers.map((container) => (
                  <option key={container.id} value={container.id}>{container.label}</option>
                ))}
              </select>
            </label>
            <div className="date-type-filter">
              <label>Date type
                <select value={dateField} onChange={(event) => setDateField(event.target.value)}>
                  <option value="acquisition_date">Acquisition</option>
                  <option value="reading_started_date">Reading started</option>
                  <option value="read_date">Finished reading</option>
                </select>
              </label>
              <label className="advanced-check">
                <input
                  type="checkbox"
                  checked={includeUnknownSortDates}
                  onChange={(event) => setIncludeUnknownSortDates(event.target.checked)}
                />
                Include books whose sorted date is unknown
              </label>
              <label className="advanced-check">
                <input
                  type="checkbox"
                  checked={includeUnknownSelectedDates}
                  onChange={(event) => setIncludeUnknownSelectedDates(event.target.checked)}
                />
                Include books whose selected date is unknown
              </label>
            </div>
            <label>From
              <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
            </label>
            <label>To
              <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            </label>
            <MetadataFilterFields
              filters={metadataFilters}
              options={metadataOptions}
              onChange={(next) => {
                setExactBookFilter(null);
                setMetadataFilters(next);
              }}
            />
            <fieldset className="wide loan-filter-fields">
              <legend>Loans</legend>
              <div className="loan-filter-grid">
                <label>Loan status
                  <select value={loanStatus} onChange={(event) => setLoanStatus(event.target.value)}>
                    <option value="ANY">Any</option>
                    <option value="AVAILABLE">Available</option>
                    <option value="ON_LOAN">On loan</option>
                    <option value="OVERDUE">Overdue</option>
                    <option value="EVER">Ever loaned</option>
                    <option value="NEVER">Never loaned</option>
                  </select>
                </label>
                <label>Loaned to
                  <input value={loanedTo} maxLength={300} onChange={(event) => setLoanedTo(event.target.value)} />
                </label>
                <label>Search loan records
                  <select value={loanRecordScope} onChange={(event) => setLoanRecordScope(event.target.value as "ACTIVE" | "ANY")}>
                    <option value="ACTIVE">Active loan only</option>
                    <option value="ANY">Entire loan history</option>
                  </select>
                </label>
                <label>Loan date type
                  <select value={loanDateField} onChange={(event) => setLoanDateField(event.target.value)}>
                    <option value="loaned_date">Loaned</option>
                    <option value="expected_return_date">Expected return</option>
                    <option value="returned_date">Returned</option>
                  </select>
                </label>
                <label>From<input type="date" value={loanDateFrom} onChange={(event) => setLoanDateFrom(event.target.value)} /></label>
                <label>To<input type="date" value={loanDateTo} onChange={(event) => setLoanDateTo(event.target.value)} /></label>
                <label className="advanced-check wide">
                  <input type="checkbox" checked={includeUnknownLoanDates} onChange={(event) => setIncludeUnknownLoanDates(event.target.checked)} />
                  Include loan records whose selected date is unknown
                </label>
              </div>
            </fieldset>
            <div className="catalogue-check-control">
              <button
                type="button"
                className={`catalogue-check-toggle ${showCatalogueChecks ? "active" : ""}`}
                onClick={() => {
                  const next = !showCatalogueChecks;
                  setShowCatalogueChecks(next);
                  if (!next) setCatalogueCheck("");
                }}
              >
                Catalogue check
              </button>
              {showCatalogueChecks && (
                <select
                  aria-label="Catalogue check"
                  value={catalogueCheck}
                  onChange={(event) => {
                    const value = event.target.value;
                    setExactBookFilter(null);
                    setCatalogueCheck(value);
                    setQuickView("");
                    setFilter("ALL");
                    if (
                      (
                        value === "missing_started"
                        && sortBy === "reading_started_date"
                      )
                      || (
                        value === "missing_end"
                        && sortBy === "read_date"
                      )
                    ) {
                      setIncludeUnknownSortDates(true);
                    }
                  }}
                >
                  <option value="">Choose a catalogue check…</option>
                  <option value="missing_started">Reading Started Date Unknown</option>
                  <option value="missing_end">Reading End Date Unknown</option>
                  <option value="no_location">Without a physical location</option>
                  <option value="no_cover">Without a cover</option>
                  <optgroup label="Incomplete bibliographic metadata">
                    <option value="missing_metadata">Missing any core metadata</option>
                    <option value="missing_isbn">Without ISBN</option>
                    <option value="missing_page_count">Without page count</option>
                    <option value="missing_publisher">Without publisher</option>
                    <option value="missing_current_ed_year">Without current edition year</option>
                    <option value="missing_original_publication_year">Without original publication year</option>
                    <option value="missing_language">Without language</option>
                    <option value="missing_fiction_category">Without fiction/non-fiction category</option>
                    <option value="missing_binding">Without binding</option>
                    <option value="missing_publication_type">Without publication type</option>
                    <option value="missing_genre">Without genre</option>
                  </optgroup>
                </select>
              )}
            </div>
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
                setQuickView("");
                setCatalogueCheck("");
                setShowCatalogueChecks(false);
                setIncludeUnknownSelectedDates(false);
                setIncludeUnknownSortDates(false);
                setMetadataFilters(emptyMetadataFilters());
                setFilter("ALL");
                setLoanStatus("ANY");
                setLoanedTo("");
                setLoanRecordScope("ACTIVE");
                setLoanDateField("loaned_date");
                setLoanDateFrom("");
                setLoanDateTo("");
                setIncludeUnknownLoanDates(false);
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
                <button
                  className={`status status-action ${book.status.toLowerCase()}`}
                  title={book.status === "PENDING"
                    ? "Start reading this book"
                    : book.status === "READ"
                      ? "Re-read this book"
                      : "Finish or cancel this reading"}
                  onClick={() => setStatusActionBook(book)}
                >
                  {bookStatusLabel(book)}
                </button>
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
                    <BookAuthorDisplay
                      book={book}
                      onShowAll={() => setAuthorsBook(book)}
                    />
                    <BookDates book={book} />
                  </div>
                </div>
                <div className="book-side">
                  <button
                    className="location location-link"
                    type="button"
                    disabled={!book.container_id && book.status !== "CURRENTLY_READING" && !book.is_on_loan}
                    aria-label={
                      book.container_id || book.status === "CURRENTLY_READING" || book.is_on_loan
                        ? `Find ${book.title} on the library map`
                        : "This book has no location to show on the library map"
                    }
                    onClick={() => openBookOnMap(book)}
                  >
                    {book.is_on_loan ? <BookUp size={16} /> : <MapPin size={16} />}
                    {book.is_on_loan && book.active_loan ? (
                      <div className="location-copy">
                        <strong>On loan: {book.active_loan.loaned_to}</strong>
                        <span title={book.return_location_label ?? undefined}>
                          {book.return_location_label ? "Saved position" : "No saved position"}
                        </span>
                      </div>
                    ) : book.status === "CURRENTLY_READING" ? (
                      <div className="location-copy">
                        <strong>{book.is_rereading ? "Currently re-reading" : "Currently reading"}</strong>
                        <span>
                          {book.container_id
                            ? `Saved at ${book.bookcase_name} · Shelf ${book.shelf_number} · ${
                              book.layer === "BACKGROUND" ? "Background" : "Foreground"
                            } ${book.container_type === "ROW" ? "Row" : "Pile"} ${
                              book.container_number
                            } · Position ${book.position}`
                            : "No return location assigned"}
                        </span>
                      </div>
                    ) : book.container_id ? (
                      <div className="location-copy">
                        <strong>{book.bookcase_name}</strong>
                        <span>
                          Shelf {book.shelf_number} ·{" "}
                          {book.layer === "BACKGROUND" ? "Background" : "Foreground"}{" "}
                          {book.container_type === "ROW" ? "Row" : "Pile"}{" "}
                          {book.container_number} · Position {book.position}
                        </span>
                      </div>
                    ) : (
                      <div className="location-copy">
                        <strong>Location not assigned</strong>
                        <span>No shelf or container selected</span>
                      </div>
                    )}
                  </button>
                  <div className="row-actions">
                    <button
                      aria-label="Show complete book information"
                      title="Show complete book information"
                      onClick={() => setDetailsBook(book)}
                    >
                      <Info size={17} />
                    </button>
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
                    <button
                      aria-label={book.is_on_loan ? "Return book" : "Loan book"}
                      title={book.is_on_loan ? "Return book" : "Loan book"}
                      onClick={() => setLoanActionBook(book)}
                    >
                      {book.is_on_loan ? <BookDown size={17} /> : <BookUp size={17} />}
                    </button>
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

      {detailsBook && (
        <BookDetailsDialog
          book={detailsBook}
          onClose={() => setDetailsBook(null)}
        />
      )}
      {authorsBook && (
        <AuthorsDialog book={authorsBook} onClose={() => setAuthorsBook(null)} />
      )}
      {editing !== undefined && (
        <BookDialog
          book={editing}
          library={library}
          metadataOptions={metadataOptions}
          onClose={() => setEditing(undefined)}
          onSaved={async () => {
            setEditing(undefined);
            await refresh();
          }}
          onHistoryChanged={refresh}
          onOpenExisting={(bookId, title) => {
            setEditing(undefined);
            openExactBookCatalogue({ id: bookId, title });
          }}
        />
      )}
      {batchAdding && (
        <BookDialog
          book={null}
          library={library}
          metadataOptions={metadataOptions}
          batchMode
          onClose={() => setBatchAdding(false)}
          onSaved={refresh}
          onOpenExisting={(bookId, title) => {
            setBatchAdding(false);
            openExactBookCatalogue({ id: bookId, title });
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
      {showData && <DataDialog onClose={() => setShowData(false)} />}
      {showStatistics && (
        <StatisticsDialog onClose={() => setShowStatistics(false)} />
      )}
      {suggestionMode && (
        <SuggestionsDialog
          initialMode={suggestionMode}
          onClose={() => setSuggestionMode(null)}
          onOpenBook={(book) => {
            setSuggestionMode(null);
            openExactBookCatalogue(book);
          }}
          onStartReading={(book) => {
            setSuggestionMode(null);
            setStatusActionBook(book);
          }}
        />
      )}
      {statusActionBook && (
        <StatusActionDialog
          book={statusActionBook}
          onClose={() => setStatusActionBook(null)}
          onConfirmed={async () => {
            setStatusActionBook(null);
            await refresh();
          }}
        />
      )}
      {loanActionBook && (
        <LoanActionDialog
          book={loanActionBook}
          onClose={() => setLoanActionBook(null)}
          onConfirmed={async () => {
            setLoanActionBook(null);
            await refresh();
          }}
        />
      )}
      {showMap && (
        <LibraryMapDialog
          focusedBook={focusedMapBook}
          onClose={closeLibraryMap}
          onFilter={openCatalogueAt}
          onReadingFilter={openReadingCatalogue}
          onLoanFilter={openLoanCatalogue}
          onBookFilter={openExactBookCatalogue}
          onChanged={refresh}
        />
      )}
    </main>
  );
}

function statusLabel(status: "ALL" | BookStatus) {
  if (status === "ALL") return "All";
  if (status === "PENDING") return "Pending";
  if (status === "CURRENTLY_READING") return "Reading…";
  return "Read";
}

function bookStatusLabel(book: Pick<Book, "status" | "is_rereading">) {
  return book.status === "CURRENTLY_READING" && book.is_rereading
    ? "Re-Reading…"
    : statusLabel(book.status);
}

function displayedAuthor(book: Pick<Book, "author" | "has_multiple_authors" | "structured_authors">) {
  if (!book.has_multiple_authors) return book.author;
  if (book.structured_authors.length === 2) {
    return book.structured_authors.join(" & ");
  }
  return "Multiple authors";
}

function BookAuthorDisplay({
  book,
  onShowAll,
}: {
  book: Pick<Book, "author" | "has_multiple_authors" | "structured_authors">;
  onShowAll: () => void;
}) {
  if (book.has_multiple_authors && book.structured_authors.length > 2) {
    return (
      <button type="button" className="author-list-link" onClick={onShowAll}>
        Multiple authors
      </button>
    );
  }
  return <p>{displayedAuthor(book)}</p>;
}

function AuthorsDialog({ book, onClose }: { book: Book; onClose: () => void }) {
  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div
        className="dialog authors-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="authors-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="dialog-header">
          <div>
            <p className="eyebrow dark">Contributors</p>
            <h2 id="authors-dialog-title">Authors</h2>
          </div>
          <button className="icon-button" aria-label="Close" onClick={onClose}><X /></button>
        </div>
        <h3>{book.title}</h3>
        <ol className="structured-author-list">
          {book.structured_authors.map((author) => <li key={author}>{author}</li>)}
        </ol>
        <div className="dialog-actions">
          <button type="button" className="primary-button" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function latestDate(...values: Array<string | null>) {
  return values.filter((value): value is string => Boolean(value)).sort().at(-1) ?? "";
}

function earliestDate(...values: Array<string | null>) {
  return values.filter((value): value is string => Boolean(value)).sort().at(0);
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
    book.read_date
      ? `Read ${formatDate(book.read_date)}`
      : book.status === "READ" && book.is_read_date_unknown
        ? "Read · date unknown"
        : null,
  ].filter(Boolean);

  return dates.length ? <small className="book-dates">{dates.join(" · ")}</small> : null;
}

function metadataLabel(value: string) {
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function normalizeGenreText(value: string) {
  const uniqueGenres = new Map<string, string>();
  value.split(/[,;\n\r]+/).forEach((item) => {
    const genre = item.replace(/\s+/g, " ").trim();
    if (genre) uniqueGenres.set(genre.toLocaleLowerCase(), genre);
  });
  return Array.from(uniqueGenres.values())
    .sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base" }))
    .join(", ");
}

function CandidateMetadataReview({
  candidate,
  onApply,
}: {
  candidate: BibliographicCandidate;
  onApply: (selected: Set<CandidateMetadataKey>) => void;
}) {
  const entries = useMemo(() => {
    const values: Array<{
      key: CandidateMetadataKey;
      label: string;
      value: string | number | null;
      inferred?: boolean;
    }> = [
      { key: "title", label: "Title", value: candidate.title },
      { key: "author", label: "Author", value: candidate.authors.join(" & ") },
      { key: "isbn_10", label: "ISBN-10", value: candidate.identifiers.isbn_10 },
      { key: "isbn_13", label: "ISBN-13", value: candidate.identifiers.isbn_13 },
      { key: "subtitle", label: "Subtitle", value: candidate.subtitle },
      { key: "page_count", label: "Pages", value: candidate.page_count },
      { key: "publisher", label: "Publisher", value: candidate.publisher },
      { key: "current_ed_year", label: "Current edition year", value: candidate.current_ed_year },
      { key: "original_publication_year", label: "Original publication year", value: candidate.original_publication_year },
      { key: "language", label: "Language", value: candidate.language },
      { key: "edition_number", label: "Edition number", value: candidate.edition_number },
      { key: "binding", label: "Binding", value: candidate.binding ? metadataLabel(candidate.binding) : null },
      { key: "series_name", label: "Series", value: candidate.series_name },
      { key: "series_volume", label: "Series volume", value: candidate.series_volume },
      { key: "fiction_category", label: "Category", value: candidate.fiction_category ? metadataLabel(candidate.fiction_category) : null, inferred: true },
      { key: "publication_type", label: "Publication type", value: candidate.publication_type ? metadataLabel(candidate.publication_type) : null, inferred: true },
      { key: "genre_text", label: "Genres / provider categories", value: candidate.genre_text, inferred: true },
    ];
    return values.filter((entry) => entry.value !== null && entry.value !== "");
  }, [candidate]);
  const [selected, setSelected] = useState<Set<CandidateMetadataKey>>(
    () => new Set(entries.filter((entry) => !entry.inferred).map((entry) => entry.key)),
  );

  return (
    <div className="candidate-metadata-review">
      <div className="candidate-review-heading">
        <strong>Choose metadata to apply</strong>
        <small>Inferred classifications start unchecked. All values remain editable before saving.</small>
      </div>
      <div className="candidate-review-grid">
        {entries.map((entry) => (
          <label key={entry.key} className={entry.inferred ? "inferred" : ""}>
            <input
              type="checkbox"
              checked={selected.has(entry.key)}
              onChange={(event) => {
                setSelected((current) => {
                  const next = new Set(current);
                  if (event.target.checked) next.add(entry.key);
                  else next.delete(entry.key);
                  return next;
                });
              }}
            />
            <span><b>{entry.label}</b>{entry.value}{entry.inferred && <em>Suggested</em>}</span>
          </label>
        ))}
      </div>
      <button
        type="button"
        className="secondary-button"
        disabled={selected.size === 0}
        onClick={() => onApply(selected)}
      >
        Apply selected metadata
      </button>
    </div>
  );
}

function formatTimestamp(value: string) {
  const normalized = value.includes("T") ? value : `${value.replace(" ", "T")}Z`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function readingDuration(started: string, finished: string) {
  return Math.round((Date.parse(`${finished}T00:00:00Z`) - Date.parse(`${started}T00:00:00Z`)) / 86400000) + 1;
}

function ReadingHistorySummary({ book }: { book: Book }) {
  if (book.reading_sessions.length === 0) return <p className="book-details-note">No reading history.</p>;
  return (
    <ol className="reading-history-summary">
      {book.reading_sessions.map((session) => {
        const duration = session.started_date && session.finished_date
          ? readingDuration(session.started_date, session.finished_date)
          : null;
        const rate = duration && book.page_count ? book.page_count / duration : null;
        return (
          <li key={session.id}>
            <strong>Reading {session.session_number}</strong>
            <span>{session.dates_unknown
              ? "Reading dates unknown"
              : session.state === "ACTIVE"
                ? `${session.session_number > 1 ? "Re-reading" : "Reading"} since ${formatDate(session.started_date!)}`
                : `${formatDate(session.started_date!)} – ${formatDate(session.finished_date!)}`}
            </span>
            {duration !== null && (
              <small>{duration} {duration === 1 ? "day" : "days"}{rate !== null ? ` · ${rate.toFixed(1)} pages/day` : ""}</small>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function ReadingHistoryDialog({
  book,
  onClose,
  onChanged,
  onCatalogueChanged,
}: {
  book: Book;
  onClose: () => void;
  onChanged: (book: Book) => void;
  onCatalogueChanged?: () => Promise<void>;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [started, setStarted] = useState("");
  const [finished, setFinished] = useState("");
  const [unknown, setUnknown] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function resetForm() {
    setEditingId(null); setStarted(""); setFinished(""); setUnknown(false); setError("");
  }
  function edit(session: Book["reading_sessions"][number]) {
    setEditingId(session.id);
    setStarted(session.started_date ?? "");
    setFinished(session.finished_date ?? "");
    setUnknown(session.dates_unknown);
    setError("");
  }
  async function save() {
    setSaving(true); setError("");
    const payload = {
      started_date: unknown ? null : started || null,
      finished_date: unknown ? null : finished || null,
      dates_unknown: unknown,
    };
    try {
      const updated = editingId
        ? await api.updateReadingHistory(book.id, editingId, payload)
        : await api.addReadingHistory(book.id, payload);
      onChanged(updated); resetForm(); await onCatalogueChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save reading history");
    } finally { setSaving(false); }
  }
  async function remove(session: Book["reading_sessions"][number]) {
    const dates = session.dates_unknown
      ? "unknown dates"
      : `${session.started_date} – ${session.finished_date ?? "active"}`;
    const consequence = book.reading_sessions.length === 1
      ? " This is the only reading: the book will become Pending."
      : " Later readings will be renumbered.";
    if (!window.confirm(`Delete Reading ${session.session_number} (${dates})? It will be removed from statistics.${consequence}`)) return;
    try { onChanged(await api.deleteReadingHistory(book.id, session.id)); resetForm(); await onCatalogueChanged?.(); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to delete reading"); }
  }

  return (
    <div className="dialog-backdrop history-manager-backdrop" onMouseDown={onClose}>
      <div className="dialog reading-history-dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          <div><p className="eyebrow dark">Reading record</p><h2>Manage reading history</h2></div>
          <button className="icon-button" onClick={onClose}><X /></button>
        </div>
        <h3>{book.title}</h3>
        <ReadingHistorySummary book={book} />
        <div className="history-session-actions">
          {book.reading_sessions.map((session) => (
            <div key={session.id}>
              <span>Reading {session.session_number}</span>
              <button className="outline-button" onClick={() => edit(session)}>Edit</button>
              <button className="text-button danger" onClick={() => void remove(session)}>Delete</button>
            </div>
          ))}
        </div>
        <fieldset>
          <legend>{editingId ? "Edit reading" : "Add historical reading"}</legend>
          <label className="checkbox-row"><input type="checkbox" checked={unknown} disabled={book.reading_sessions.some((item) => item.dates_unknown && item.id !== editingId)} onChange={(event) => setUnknown(event.target.checked)} /> Reading dates unknown</label>
          {!unknown && <div className="history-date-grid">
            <label>Started<input type="date" max={today} value={started} onChange={(event) => setStarted(event.target.value)} /></label>
            <label>Finished<input type="date" max={today} value={finished} disabled={editingId !== null && book.reading_sessions.find((item) => item.id === editingId)?.state === "ACTIVE"} onChange={(event) => setFinished(event.target.value)} /></label>
          </div>}
        </fieldset>
        {error && <div className="form-error">{error}</div>}
        <div className="dialog-actions">
          {editingId && <button className="text-button" onClick={resetForm}>Cancel edit</button>}
          <button className="outline-button" onClick={onClose}>Close</button>
          <button className="secondary-button" disabled={saving || (!unknown && (!started || (!finished && editingId === null)))} onClick={() => void save()}>{saving ? "Saving…" : editingId ? "Save reading" : "Add reading"}</button>
        </div>
      </div>
    </div>
  );
}

function LoanActionDialog({
  book,
  onClose,
  onConfirmed,
}: {
  book: Book;
  onClose: () => void;
  onConfirmed: () => Promise<void>;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [loanedTo, setLoanedTo] = useState("");
  const [loanDateUnknown, setLoanDateUnknown] = useState(false);
  const [loanedDate, setLoanedDate] = useState(today);
  const [expectedReturnDate, setExpectedReturnDate] = useState("");
  const [notes, setNotes] = useState("");
  const [returnDateUnknown, setReturnDateUnknown] = useState(false);
  const [returnedDate, setReturnedDate] = useState(today);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setSaving(true);
    setError("");
    try {
      if (book.active_loan) {
        await api.returnLoan(book.id, returnDateUnknown ? null : returnedDate);
      } else {
        await api.startLoan(book.id, {
          loaned_to: loanedTo,
          loaned_date: loanDateUnknown ? null : loanedDate,
          expected_return_date: expectedReturnDate || null,
          notes: notes || null,
        });
      }
      await onConfirmed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update loan");
    } finally {
      setSaving(false);
    }
  }

  async function cancelActiveLoan() {
    if (!window.confirm("Delete this active loan record? The book will become available immediately.")) return;
    setSaving(true);
    setError("");
    try {
      await api.cancelLoan(book.id);
      await onConfirmed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to cancel loan");
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div className="dialog loan-action-dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          <div>
            <p className="eyebrow dark">Physical availability</p>
            <h2>{book.active_loan ? "Return book" : "Loan book"}</h2>
          </div>
          <button className="icon-button" onClick={onClose}><X /></button>
        </div>
        <h3 className="dialog-book-title">{book.title}</h3>
        {book.active_loan ? (
          <div className="loan-form">
            <p>Currently loaned to <strong>{book.active_loan.loaned_to}</strong>.</p>
            <label className="checkbox-label">
              <input type="checkbox" checked={returnDateUnknown} onChange={(event) => setReturnDateUnknown(event.target.checked)} />
              Returned date unknown
            </label>
            {!returnDateUnknown && (
              <label>Returned date
                <input type="date" required max={today} min={book.active_loan.loaned_date ?? undefined} value={returnedDate} onChange={(event) => setReturnedDate(event.target.value)} />
              </label>
            )}
          </div>
        ) : (
          <div className="loan-form">
            <label>Loaned to <span className="required-marker">*</span>
              <input required maxLength={300} value={loanedTo} onChange={(event) => setLoanedTo(event.target.value)} />
            </label>
            <label className="checkbox-label">
              <input type="checkbox" checked={loanDateUnknown} onChange={(event) => setLoanDateUnknown(event.target.checked)} />
              Loan date unknown
            </label>
            {!loanDateUnknown && (
              <label>Loaned date<input type="date" required max={today} value={loanedDate} onChange={(event) => setLoanedDate(event.target.value)} /></label>
            )}
            <label>Expected return date
              <input type="date" min={loanDateUnknown ? undefined : loanedDate} value={expectedReturnDate} onChange={(event) => setExpectedReturnDate(event.target.value)} />
            </label>
            <label>Loan notes
              <textarea rows={3} maxLength={4000} value={notes} onChange={(event) => setNotes(event.target.value)} />
            </label>
          </div>
        )}
        {error && <div className="form-error">{error}</div>}
        <div className="dialog-actions">
          {book.active_loan && <button className="text-button destructive-text" disabled={saving} onClick={() => void cancelActiveLoan()}>Cancel loan record</button>}
          <button className="outline-button" onClick={onClose}>Close</button>
          <button className="secondary-button" disabled={saving || (!book.active_loan && !loanedTo.trim())} onClick={() => void save()}>
            {saving ? "Saving…" : book.active_loan ? "Return book" : "Confirm loan"}
          </button>
        </div>
      </div>
    </div>
  );
}

function LoanHistorySummary({ book }: { book: Book }) {
  if (book.loans.length === 0) return <p className="book-details-note">No loans recorded.</p>;
  return (
    <ol className="record-summary-list loan-summary-list">
      {book.loans.map((loan, index) => (
        <li key={loan.id}>
          <strong>{loan.state === "ACTIVE" ? "Active loan" : `Loan ${index + 1}`}</strong>
          <span>Loaned to {loan.loaned_to}</span>
          <span>
            {loan.loaned_date ? formatDate(loan.loaned_date) : "Unknown loan date"}
            {loan.state === "ACTIVE"
              ? loan.expected_return_date ? ` · expected ${formatDate(loan.expected_return_date)}` : " · no expected return date"
              : ` – ${loan.returned_date ? formatDate(loan.returned_date) : "unknown returned date"}`}
          </span>
          {loan.notes && <span>{loan.notes}</span>}
        </li>
      ))}
    </ol>
  );
}

function LoanHistoryDialog({
  book,
  onClose,
  onChanged,
  onCatalogueChanged,
}: {
  book: Book;
  onClose: () => void;
  onChanged: (book: Book) => void;
  onCatalogueChanged?: () => Promise<void>;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [editing, setEditing] = useState<Loan | null>(null);
  const [loanedTo, setLoanedTo] = useState("");
  const [loanDateUnknown, setLoanDateUnknown] = useState(false);
  const [loanedDate, setLoanedDate] = useState("");
  const [expectedReturnDate, setExpectedReturnDate] = useState("");
  const [returnDateUnknown, setReturnDateUnknown] = useState(false);
  const [returnedDate, setReturnedDate] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function reset() {
    setEditing(null); setLoanedTo(""); setLoanDateUnknown(false); setLoanedDate("");
    setExpectedReturnDate(""); setReturnDateUnknown(false); setReturnedDate(""); setNotes(""); setError("");
  }
  function beginEdit(loan: Loan) {
    setEditing(loan); setLoanedTo(loan.loaned_to); setLoanDateUnknown(!loan.loaned_date);
    setLoanedDate(loan.loaned_date ?? ""); setExpectedReturnDate(loan.expected_return_date ?? "");
    setReturnDateUnknown(loan.state === "RETURNED" && !loan.returned_date);
    setReturnedDate(loan.returned_date ?? ""); setNotes(loan.notes ?? ""); setError("");
  }
  async function accept(updated: Book) {
    onChanged(updated);
    await onCatalogueChanged?.();
    reset();
  }
  async function save() {
    if (!loanedTo.trim()) return;
    setSaving(true); setError("");
    try {
      const payload = {
        loaned_to: loanedTo,
        loaned_date: loanDateUnknown ? null : loanedDate || null,
        expected_return_date: expectedReturnDate || null,
        returned_date: returnDateUnknown ? null : returnedDate || null,
        notes: notes || null,
      };
      const updated = editing
        ? await api.updateLoanHistory(book.id, editing.id, payload)
        : await api.addLoanHistory(book.id, payload);
      await accept(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save loan record");
    } finally { setSaving(false); }
  }
  async function remove(loan: Loan) {
    if (!window.confirm(`Permanently delete this loan to “${loan.loaned_to}”?`)) return;
    setSaving(true); setError("");
    try { await accept(await api.deleteLoanHistory(book.id, loan.id)); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to delete loan record"); }
    finally { setSaving(false); }
  }

  return (
    <div className="dialog-backdrop nested-dialog-backdrop" onMouseDown={onClose}>
      <div className="dialog history-dialog loan-history-dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header"><div><p className="eyebrow dark">Loan record</p><h2>Manage loan history</h2></div><button className="icon-button" onClick={onClose}><X /></button></div>
        <h3 className="dialog-book-title">{book.title}</h3>
        <div className="history-record-list">
          {book.loans.length === 0 && <p className="muted">No loans recorded.</p>}
          {book.loans.map((loan) => (
            <div className="history-record-row" key={loan.id}>
              <div><strong>{loan.state === "ACTIVE" ? "Active loan" : "Returned loan"}</strong><span>{loan.loaned_to} · {loan.loaned_date ? formatDate(loan.loaned_date) : "unknown loan date"}</span></div>
              <div><button className="outline-button" onClick={() => beginEdit(loan)}>Edit</button><button className="text-button" onClick={() => void remove(loan)}>Delete</button></div>
            </div>
          ))}
        </div>
        <fieldset className="history-add-fieldset">
          <legend>{editing ? "Edit loan" : "Add historical loan"}</legend>
          <div className="loan-form loan-history-form">
            <label>Loaned to <span className="required-marker">*</span><input maxLength={300} value={loanedTo} onChange={(event) => setLoanedTo(event.target.value)} /></label>
            <label className="checkbox-label"><input type="checkbox" checked={loanDateUnknown} onChange={(event) => setLoanDateUnknown(event.target.checked)} /> Loan date unknown</label>
            {!loanDateUnknown && <label>Loaned date<input type="date" max={today} value={loanedDate} onChange={(event) => setLoanedDate(event.target.value)} /></label>}
            <label>Expected return<input type="date" min={loanDateUnknown ? undefined : loanedDate || undefined} value={expectedReturnDate} onChange={(event) => setExpectedReturnDate(event.target.value)} /></label>
            {editing?.state === "ACTIVE" ? (
              <p className="muted">Use the Return book action in the catalogue to complete this active loan.</p>
            ) : <>
              <label className="checkbox-label"><input type="checkbox" checked={returnDateUnknown} onChange={(event) => setReturnDateUnknown(event.target.checked)} /> Returned date unknown</label>
              {!returnDateUnknown && <label>Returned date<input type="date" max={today} min={loanDateUnknown ? undefined : loanedDate || undefined} value={returnedDate} onChange={(event) => setReturnedDate(event.target.value)} /></label>}
            </>}
            <label className="wide">Notes<textarea rows={2} maxLength={4000} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
          </div>
        </fieldset>
        {error && <div className="form-error">{error}</div>}
        <div className="dialog-actions">{editing && <button className="text-button" onClick={reset}>Cancel edit</button>}<button className="outline-button" onClick={onClose}>Close</button><button className="secondary-button" disabled={saving || !loanedTo.trim() || (!editing && !returnDateUnknown && !returnedDate)} onClick={() => void save()}>{saving ? "Saving…" : editing ? "Save loan" : "Add loan"}</button></div>
      </div>
    </div>
  );
}

function BookDetailsDialog({
  book,
  onClose,
}: {
  book: Book;
  onClose: () => void;
}) {
  const acquisition = book.acquisition_date
    ? formatDate(book.acquisition_date)
    : book.is_original_collection
      ? "Original collection · exact date unknown"
      : "Not recorded";
  const finishedReading = book.read_date
    ? formatDate(book.read_date)
    : book.status === "READ" && book.is_read_date_unknown
      ? "Read · exact date unknown"
      : "Not recorded";
  const location = book.container_id
    ? `${book.bookcase_name} · Shelf ${book.shelf_number} · ${
      book.layer === "BACKGROUND" ? "Background" : "Foreground"
    } ${book.container_type === "ROW" ? "Row" : "Pile"} ${
      book.container_number
    } · Position ${book.position}`
    : "No physical location assigned";

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div
        className="dialog book-details-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="book-details-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="dialog-header">
          <div>
            <p className="eyebrow dark">Read-only catalogue record</p>
            <h2 id="book-details-title">Book information</h2>
          </div>
          <button className="icon-button" aria-label="Close" onClick={onClose}>
            <X />
          </button>
        </div>

        <div className="book-details-summary">
          {book.cover_filename ? (
            <img src={api.coverUrl(book.cover_filename)} alt={`Cover of ${book.title}`} />
          ) : (
            <div className="book-details-cover-placeholder"><BookOpen size={34} /></div>
          )}
          <div>
            <span className={`status ${book.status.toLowerCase()}`}>
              {bookStatusLabel(book)}
            </span>
            <h3>{book.title}</h3>
            <p>{displayedAuthor(book)}</p>
          </div>
        </div>

        {book.has_multiple_authors && (
          <section className="book-details-section">
            <h3>Authors</h3>
            <ol className="structured-author-list">
              {book.structured_authors.map((author) => <li key={author}>{author}</li>)}
            </ol>
          </section>
        )}

        <section className="book-details-section">
          <h3>Bibliographic identifiers</h3>
          <dl className="book-details-grid">
            <div><dt>ISBN-10</dt><dd>{book.isbn_10 ?? "Not recorded"}</dd></div>
            <div><dt>ISBN-13</dt><dd>{book.isbn_13 ?? "Not recorded"}</dd></div>
            <div className="wide">
              <dt>Goodreads review</dt>
              <dd>
                {book.goodreads_url ? (
                  <a href={book.goodreads_url} target="_blank" rel="noreferrer">
                    Open Goodreads <ExternalLink size={14} />
                  </a>
                ) : "Not recorded"}
              </dd>
            </div>
          </dl>
        </section>

        <section className="book-details-section">
          <h3>Edition and classification</h3>
          <dl className="book-details-grid three-columns">
            <div className="wide"><dt>Subtitle</dt><dd>{book.subtitle ?? "Not recorded"}</dd></div>
            <div><dt>Pages</dt><dd>{book.page_count ?? "Not recorded"}</dd></div>
            <div><dt>Publisher</dt><dd>{book.publisher ?? "Not recorded"}</dd></div>
            <div><dt>Current edition year</dt><dd>{book.current_ed_year ?? "Not recorded"}</dd></div>
            <div><dt>Original publication year</dt><dd>{book.original_publication_year ?? "Not recorded"}</dd></div>
            <div><dt>Language</dt><dd>{book.language ?? "Not recorded"}</dd></div>
            <div><dt>Edition number</dt><dd>{book.edition_number ?? "Not recorded"}</dd></div>
            <div><dt>Category</dt><dd>{book.fiction_category ? metadataLabel(book.fiction_category) : "Not recorded"}</dd></div>
            <div><dt>Binding</dt><dd>{book.binding ? metadataLabel(book.binding) : "Not recorded"}</dd></div>
            <div><dt>Publication type</dt><dd>{book.publication_type ? metadataLabel(book.publication_type) : "Not recorded"}</dd></div>
            <div><dt>Series</dt><dd>{book.series_name ?? "Not recorded"}</dd></div>
            <div><dt>Series volume</dt><dd>{book.series_volume ?? "Not recorded"}</dd></div>
            <div className="wide"><dt>Genre</dt><dd>{book.genre_text ?? "Not recorded"}</dd></div>
          </dl>
        </section>

        <section className="book-details-section">
          <h3>Reading and acquisition history</h3>
          <dl className="book-details-grid three-columns">
            <div><dt>Acquired</dt><dd>{acquisition}</dd></div>
            <div>
              <dt>Reading started</dt>
              <dd>{book.reading_started_date ? formatDate(book.reading_started_date) : "Not recorded"}</dd>
            </div>
            <div><dt>Finished reading</dt><dd>{finishedReading}</dd></div>
          </dl>
          <ReadingHistorySummary book={book} />
        </section>

        <section className="book-details-section">
          <h3>Physical catalogue</h3>
          <dl className="book-details-grid">
            <div className="wide">
              <dt>{book.status === "CURRENTLY_READING" ? "Saved return location" : "Location"}</dt>
              <dd>{location}</dd>
            </div>
            <div><dt>BOOKPILE record</dt><dd>#{book.id}</dd></div>
            <div><dt>Stored cover</dt><dd>{book.cover_filename ? "Yes" : "No"}</dd></div>
          </dl>
          {book.status === "CURRENTLY_READING" && (
            <p className="book-details-note">
              This book currently appears in the map's Reading area; its saved
              physical position remains available for its return.
            </p>
          )}
        </section>

        <section className="book-details-section">
          <h3>Loan history</h3>
          {book.active_loan && (
            <p className="book-details-note">
              Currently on loan to <strong>{book.active_loan.loaned_to}</strong>.
              {book.active_loan.loaned_date
                ? ` Loaned ${formatDate(book.active_loan.loaned_date)}.`
                : " Unknown loan date."}
              {book.active_loan.expected_return_date
                ? ` Expected back ${formatDate(book.active_loan.expected_return_date)}.`
                : " No expected return date."}
            </p>
          )}
          <LoanHistorySummary book={book} />
        </section>

        <section className="book-details-section">
          <h3>Notes and record history</h3>
          <dl className="book-details-grid">
            <div className="wide book-details-notes">
              <dt>Notes</dt><dd>{book.notes || "No notes"}</dd>
            </div>
            <div><dt>Added to BOOKPILE</dt><dd>{formatTimestamp(book.created_at)}</dd></div>
            <div><dt>Last updated</dt><dd>{formatTimestamp(book.updated_at)}</dd></div>
          </dl>
        </section>

        <div className="dialog-actions">
          <button type="button" className="primary-button" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  tone: string;
}) {
  return (
    <article className={`stat-card ${tone}`}>
      <div className="stat-icon">{icon}</div>
      <div><strong>{value}</strong><span>{label}</span></div>
    </article>
  );
}

const monthNames = Array.from({ length: 12 }, (_, index) =>
  new Intl.DateTimeFormat(undefined, { month: "short", timeZone: "UTC" })
    .format(new Date(Date.UTC(2024, index, 1))),
);

function StatisticsDialog({ onClose }: { onClose: () => void }) {
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [statistics, setStatistics] = useState<CatalogueStatistics | null>(null);
  const [metadataOptions, setMetadataOptions] = useState(emptyMetadataOptions);
  const [metadataFilters, setMetadataFilters] = useState<MetadataFilters>(
    emptyMetadataFilters,
  );
  const [debouncedMetadataFilters, setDebouncedMetadataFilters] =
    useState<MetadataFilters>(emptyMetadataFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(
      () => setDebouncedMetadataFilters(metadataFilters),
      450,
    );
    return () => window.clearTimeout(timer);
  }, [metadataFilters]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void Promise.all([
      api.statistics(selectedYear, debouncedMetadataFilters),
      api.metadataOptions(),
    ]).then(([result, options]) => {
      if (active) {
        setStatistics(result);
        setMetadataOptions(options);
      }
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : "Unable to load statistics");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [selectedYear, debouncedMetadataFilters]);

  const rows = selectedYear === null
    ? statistics?.yearly.map((item) => ({
        label: String(item.year),
        acquired: item.acquired,
        read: item.read,
        pages: item.pages_read,
      })) ?? []
    : statistics?.monthly.map((item) => ({
        label: monthNames[item.month - 1],
        acquired: item.acquired,
        read: item.read,
        pages: item.pages_read,
      })) ?? [];
  const maximum = Math.max(
    1,
    ...rows.flatMap((item) => [item.acquired, item.read]),
  );
  const perBookRates = statistics?.reading_rate.per_book ?? [];

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div className="dialog statistics-dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header statistics-header">
          <div>
            <p className="eyebrow dark">Read-only catalogue insights</p>
            <h2>Statistics</h2>
          </div>
          <div className="statistics-header-actions">
            <label>
              Period
              <select
                value={selectedYear ?? ""}
                onChange={(event) => setSelectedYear(
                  event.target.value ? Number(event.target.value) : null,
                )}
              >
                <option value="">All time</option>
                {[...(statistics?.available_years ?? [])].reverse().map((year) => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </label>
            <button className="icon-button" onClick={onClose}><X /></button>
          </div>
        </div>
        {error && <div className="form-error">{error}</div>}
        {!statistics ? (
          <div className="empty-state">Calculating your library…</div>
        ) : (
          <>
            {loading && (
              <div className="statistics-updating" role="status">
                Updating statistics…
              </div>
            )}
            <div className="duration-stat-grid">
              <DurationCard
                title="Time spent pending"
                statistic={statistics.pending_duration}
                note="Acquisition through reading start"
              />
              <DurationCard
                title="Reading duration"
                statistic={statistics.reading_duration}
                note="Reading start through finish"
              />
            </div>
            <div className="duration-stat-grid reading-session-stat-grid">
              <article className="duration-stat-card"><p>Reading sessions completed</p><strong>{statistics.reading_sessions.completed}</strong><span>Every completed read, including re-reads</span></article>
              <article className="duration-stat-card"><p>Unique books read</p><strong>{statistics.reading_sessions.unique_books}</strong><span>{statistics.reading_sessions.rereads} completed re-reads</span></article>
            </div>
            <section className="statistics-section loan-statistics-section">
              <div className="statistics-section-heading">
                <div><h3>Loans</h3><p>Availability and complete loan history for the selected books.</p></div>
              </div>
              <div className="reading-rate-grid">
                <ReadingRateCard label="Currently on loan" value={statistics.loans.active} />
                <ReadingRateCard label="Overdue" value={statistics.loans.overdue} />
                <ReadingRateCard label="Returned loans" value={statistics.loans.completed} />
                <ReadingRateCard label="Unknown loan dates" value={statistics.loans.unknown_loan_dates} />
              </div>
              <div className="loan-statistics-details">
                <details>
                  <summary>Loans by year</summary>
                  {statistics.loans.by_year.length ? (
                    <ul>{statistics.loans.by_year.map((item) => <li key={item.year}><span>{item.year}</span><strong>{item.count}</strong></li>)}</ul>
                  ) : <p className="muted">No loans with a known loan date.</p>}
                </details>
                <details>
                  <summary>Most-loaned books</summary>
                  {statistics.loans.most_loaned.length ? (
                    <ol>{statistics.loans.most_loaned.map((item) => <li key={item.book_id}><span><strong>{item.title}</strong><small>{item.author}</small></span><b>{item.loan_count}</b></li>)}</ol>
                  ) : <p className="muted">No loan history recorded.</p>}
                </details>
              </div>
            </section>

            <details className="statistics-metadata-filters">
              <summary>Filter statistics by book metadata</summary>
              <div className="statistics-filter-grid">
                <MetadataFilterFields
                  filters={metadataFilters}
                  options={metadataOptions}
                  onChange={setMetadataFilters}
                />
                <button type="button" className="clear-filters" onClick={() => (
                  setMetadataFilters(emptyMetadataFilters())
                )}>Clear metadata filters</button>
              </div>
              <p>{statistics.filtered_book_count} books match this metadata selection.</p>
            </details>

            <section className="statistics-section reading-rate-section">
              <div className="statistics-section-heading">
                <div>
                  <h3>Estimated reading rate</h3>
                  <p>
                    Pages are spread across each known reading interval. A missing
                    start date assigns the book to its finish day.
                  </p>
                </div>
              </div>
              <div className="reading-rate-grid">
                <ReadingRateCard label="Pages in period" value={statistics.reading_rate.total_pages} />
                <ReadingRateCard label="Pages per week" value={statistics.reading_rate.pages_per_week} />
                <ReadingRateCard label="Pages per month" value={statistics.reading_rate.pages_per_month} />
                <ReadingRateCard label="Average per-book pages/day" value={statistics.reading_rate.average_per_book ?? null} />
                <ReadingRateCard label="Median per-book pages/day" value={statistics.reading_rate.median_per_book ?? null} />
              </div>
              <p className="statistics-method-note">
                Timeline estimate: {statistics.reading_rate.sample_size} read books with pages and a finish date · {" "}
                {statistics.reading_rate.excluded} excluded · {" "}
                {statistics.reading_rate.single_day_estimates} assigned to their finish day.
              </p>
              <p className="statistics-method-note">
                Per-book rate for this selection and period: {statistics.reading_rate.per_book_sample_size ?? 0} used · {" "}
                {statistics.reading_rate.per_book_excluded ?? 0} excluded · {" "}
                {statistics.reading_rate.per_book_estimates ?? 0} estimated from an unknown start date.
              </p>
              <details className="per-book-rates">
                <summary>Reading rate by book</summary>
                {perBookRates.length === 0 ? (
                  <p className="muted">No books have enough data for this calculation.</p>
                ) : (
                  <div className="per-book-rate-list">
                    {perBookRates.map((book) => (
                      <article key={book.id}>
                        <div>
                          <strong>{book.title}</strong>
                          <span>{book.author}</span>
                        </div>
                        <span>{book.page_count} pages</span>
                        <span>
                          {book.reading_days} day{book.reading_days === 1 ? "" : "s"}
                          {book.estimated_start ? " · estimated" : ""}
                        </span>
                        <strong>{book.pages_per_day} pages/day</strong>
                      </article>
                    ))}
                  </div>
                )}
              </details>
            </section>

            <section className="statistics-section">
              <div className="statistics-section-heading">
                <div>
                  <h3>{selectedYear === null ? "Acquired and read by year" : `Acquired and read in ${selectedYear}`}</h3>
                  <p>Only records with a known date are counted.</p>
                </div>
                <div className="chart-legend">
                  <span className="acquired-key" /> Acquired
                  <span className="read-key" /> Read
                </div>
              </div>
              {rows.length === 0 ? (
                <p className="muted">No known dates are available for this period.</p>
              ) : (
                <div className="comparison-chart">
                  {rows.map((item) => (
                    <div className="comparison-chart-row" key={item.label}>
                      <strong>{item.label}</strong>
                      <div className="comparison-bars">
                        <span
                          className="acquired-bar"
                          style={{ width: `${item.acquired / maximum * 100}%` }}
                        >{item.acquired || ""}</span>
                        <span
                          className="read-bar"
                          style={{ width: `${item.read / maximum * 100}%` }}
                        >{item.read || ""}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="statistics-section">
              <div className="statistics-section-heading">
                <div>
                  <h3>{selectedYear === null ? "Estimated pages read by year" : `Estimated pages read in ${selectedYear}`}</h3>
                  <p>Uses the same daily distribution as the reading-rate calculation.</p>
                </div>
              </div>
              {rows.every((item) => item.pages === 0) ? (
                <p className="muted">No read books with page counts are available for this period.</p>
              ) : (
                <div className="comparison-chart page-chart">
                  {rows.map((item) => (
                    <div className="comparison-chart-row" key={item.label}>
                      <strong>{item.label}</strong>
                      <div className="comparison-bars">
                        <span
                          className="pages-bar"
                          style={{ width: `${item.pages / Math.max(1, ...rows.map((row) => row.pages)) * 100}%` }}
                        >{item.pages ? Math.round(item.pages) : ""}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="statistics-section">
              <div className="statistics-section-heading">
                <div>
                  <h3>Collection comparison</h3>
                  <p>Current reading-status breakdown.</p>
                </div>
              </div>
              <div className="collection-comparison">
                <CollectionCard
                  title="Original Collection"
                  statistic={statistics.original_collection}
                />
                <CollectionCard
                  title="Later acquisitions"
                  statistic={statistics.later_acquisitions}
                />
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function ReadingRateCard({ label, value }: { label: string; value: number | null }) {
  return (
    <article className="reading-rate-card">
      <strong>{value === null ? "—" : Math.round(value).toLocaleString()}</strong>
      <span>{label}</span>
    </article>
  );
}

function DurationCard({
  title,
  statistic,
  note,
}: {
  title: string;
  statistic: CatalogueStatistics["pending_duration"];
  note: string;
}) {
  return (
    <article className="duration-stat-card">
      <p>{title}</p>
      <strong>
        {statistic.average_days === null ? "—" : `${statistic.average_days} days`}
      </strong>
      <span>
        Median {statistic.median_days === null ? "—" : `${statistic.median_days} days`}
      </span>
      <small>{note}</small>
      <small>{statistic.sample_size} books used · {statistic.excluded} excluded for missing dates</small>
    </article>
  );
}

function CollectionCard({
  title,
  statistic,
}: {
  title: string;
  statistic: CatalogueStatistics["original_collection"];
}) {
  return (
    <article className="collection-card">
      <h4>{title}</h4>
      <strong>{statistic.total}</strong>
      <div>
        <span>{statistic.pending} Pending</span>
        <span>{statistic.reading} Reading</span>
        <span>{statistic.read} Read</span>
      </div>
    </article>
  );
}

function SuggestionsDialog({
  initialMode,
  onClose,
  onOpenBook,
  onStartReading,
}: {
  initialMode: SuggestionMode;
  onClose: () => void;
  onOpenBook: (book: Book) => void;
  onStartReading: (book: Book) => void;
}) {
  const [mode, setMode] = useState<SuggestionMode>(initialMode);
  const [minimumDays, setMinimumDays] = useState(365);
  const [appliedMinimumDays, setAppliedMinimumDays] = useState(365);
  const [suggestion, setSuggestion] = useState<ReadingSuggestion | null>(null);
  const [seenIds, setSeenIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [metadataOptions, setMetadataOptions] = useState(emptyMetadataOptions);
  const [metadataFilters, setMetadataFilters] = useState<MetadataFilters>(
    emptyMetadataFilters,
  );
  const [appliedMetadataFilters, setAppliedMetadataFilters] = useState<MetadataFilters>(
    emptyMetadataFilters,
  );

  useEffect(() => {
    void api.metadataOptions().then(setMetadataOptions).catch(() => undefined);
  }, []);

  async function loadSuggestion(exclusions: number[]) {
    setLoading(true);
    setError("");
    try {
      setSuggestion(await api.readingSuggestion(
        mode,
        appliedMinimumDays,
        exclusions,
        appliedMetadataFilters,
      ));
    } catch (err) {
      setSuggestion(null);
      setError(
        exclusions.length
          ? "You have seen every matching book in this round."
          : err instanceof Error ? err.message : "No matching book was found",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setSeenIds([]);
    void loadSuggestion([]);
    // reloadKey deliberately starts a fresh suggestion round.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, appliedMinimumDays, appliedMetadataFilters, reloadKey]);

  function chooseMode(nextMode: SuggestionMode) {
    setMode(nextMode);
    setSuggestion(null);
    setError("");
  }

  function anotherSuggestion() {
    if (!suggestion) return;
    const nextSeen = [...seenIds, suggestion.book.id];
    setSeenIds(nextSeen);
    void loadSuggestion(nextSeen);
  }

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div className="dialog suggestion-dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          <div><p className="eyebrow dark">Choose your next book</p><h2>New read</h2></div>
          <button className="icon-button" onClick={onClose}><X /></button>
        </div>
        <div className="suggestion-modes" aria-label="Suggestion method">
          <button className={mode === "random" ? "active" : ""} onClick={() => chooseMode("random")}>
            <Shuffle size={16} /> Random
          </button>
          <button className={mode === "oldest" ? "active" : ""} onClick={() => chooseMode("oldest")}>
            <Clock3 size={16} /> Oldest
          </button>
          <button className={mode === "waiting" ? "active" : ""} onClick={() => chooseMode("waiting")}>
            <BarChart3 size={16} /> Waiting time
          </button>
        </div>
        {mode === "waiting" && (
          <div className="waiting-threshold">
            <label>
              Minimum days pending
              <input
                type="number"
                min="0"
                max="36500"
                value={minimumDays}
                onChange={(event) => setMinimumDays(Number(event.target.value))}
              />
            </label>
            <button onClick={() => setAppliedMinimumDays(Math.max(0, minimumDays))}>
              Apply
            </button>
          </div>
        )}
        <details className="suggestion-metadata-filters">
          <summary>Filter suggestions by book metadata</summary>
          <div className="statistics-filter-grid">
            <MetadataFilterFields
              filters={metadataFilters}
              options={metadataOptions}
              onChange={setMetadataFilters}
            />
            <div className="suggestion-filter-actions">
              <button
                type="button"
                className="text-button"
                onClick={() => {
                  const cleared = emptyMetadataFilters();
                  setMetadataFilters(cleared);
                  setAppliedMetadataFilters(cleared);
                }}
              >
                Clear metadata filters
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setAppliedMetadataFilters(metadataFilters)}
              >
                Apply filters
              </button>
            </div>
          </div>
        </details>
        {loading ? (
          <div className="empty-state">Looking through your unread books…</div>
        ) : suggestion ? (
          <article className="suggestion-card">
            {suggestion.book.cover_filename ? (
              <img src={api.coverUrl(suggestion.book.cover_filename)} alt={`Cover of ${suggestion.book.title}`} />
            ) : (
              <div className="suggestion-cover-placeholder"><BookOpen size={34} /></div>
            )}
            <div className="suggestion-copy">
              <span className="status pending">Pending</span>
              <h3>{suggestion.book.title}</h3>
              <p>{suggestion.book.author}</p>
              <BookDates book={suggestion.book} />
              <div className="suggestion-details">
                <span>
                  <Clock3 size={15} /> {suggestion.waiting_days === null
                    ? "Acquisition date unknown"
                    : `${suggestion.waiting_days} days pending`}
                </span>
                <span>
                  <MapPin size={15} /> {suggestion.book.location_label ?? "Location not assigned"}
                </span>
              </div>
            </div>
          </article>
        ) : (
          <div className="empty-state">
            <BookOpen size={30} />
            <p>{error}</p>
            {seenIds.length > 0 && (
              <button className="outline-button" onClick={() => setReloadKey((value) => value + 1)}>
                Start another round
              </button>
            )}
          </div>
        )}
        {suggestion && !loading && (
          <div className="suggestion-actions">
            <button className="outline-button" onClick={anotherSuggestion}>
              <Shuffle size={16} /> Another suggestion
            </button>
            <button className="outline-button" onClick={() => onOpenBook(suggestion.book)}>
              Open catalogue record
            </button>
            <button className="secondary-button" onClick={() => onStartReading(suggestion.book)}>
              <BookOpen size={16} /> Start reading
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function StatusActionDialog({
  book,
  onClose,
  onConfirmed,
}: {
  book: Book;
  onClose: () => void;
  onConfirmed: () => Promise<void>;
}) {
  const finishing = book.status === "CURRENTLY_READING";
  const rereading = book.status === "READ";
  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function confirm(action: "start" | "finish" | "cancel") {
    setSaving(true);
    setError("");
    try {
      if (action === "cancel") await api.cancelReading(book.id);
      else if (action === "finish") await api.finishReading(book.id, selectedDate);
      else await api.startReading(book.id, selectedDate);
      await onConfirmed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update this book");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop status-confirmation-backdrop" onMouseDown={onClose}>
      <div className="dialog status-confirmation" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          <div>
            <p className="eyebrow dark">Reading status</p>
            <h2>{finishing ? "Finish or cancel reading?" : rereading ? "Re-read?" : "Start reading?"}</h2>
          </div>
          <button className="icon-button" onClick={onClose}><X /></button>
        </div>
        <h3>{book.title}</h3>
        <p>{finishing
          ? `Finish this ${book.is_rereading ? "re-reading" : "reading"}, or cancel it without keeping an abandoned session.`
          : `Confirm the ${rereading ? "re-reading" : "reading"} start date. Its saved library position will be preserved.`}
        </p>
        <label>{finishing ? "Finished reading" : "Reading started"}
          <input
            type="date"
            max={new Date().toISOString().slice(0, 10)}
            value={selectedDate}
            onChange={(event) => setSelectedDate(event.target.value)}
          />
        </label>
        {error && <div className="form-error">{error}</div>}
        <div className="dialog-actions">
          <button className="text-button" onClick={onClose}>Close</button>
          {finishing && (
            <button className="outline-button" disabled={saving} onClick={() => {
              const outcome = book.is_rereading ? "return to Read" : "return to Pending";
              if (window.confirm(`Cancel this active reading and ${outcome}? The active session will be deleted.`)) {
                void confirm("cancel");
              }
            }}>Cancel current reading</button>
          )}
          <button className="secondary-button" disabled={saving || !selectedDate} onClick={() => void confirm(finishing ? "finish" : "start")}>
            {saving ? "Saving…" : finishing ? "Finish reading" : rereading ? "Start re-reading" : "Start reading"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ExistingValueInput({
  label,
  value,
  options,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  const [focused, setFocused] = useState(false);
  const suggestions = options
    .filter((option) => !value.trim()
      || option.toLocaleLowerCase().includes(value.trim().toLocaleLowerCase()))
    .slice(0, 10);
  return (
    <label className="existing-value-combobox">{label}
      <input
        role="combobox"
        aria-expanded={focused && suggestions.length > 0}
        aria-autocomplete="list"
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          onChange(value.trim());
        }}
        onChange={(event) => onChange(event.target.value)}
      />
      {focused && suggestions.length > 0 && (
        <div className="existing-value-suggestions" role="listbox">
          {suggestions.map((option) => (
            <button
              type="button"
              role="option"
              key={option}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                onChange(option);
                setFocused(false);
              }}
            >
              {option}
            </button>
          ))}
        </div>
      )}
      {options.length > 0 && <small>Choose an existing value or enter a new one.</small>}
    </label>
  );
}

function GenreSuggestionInput({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const [focused, setFocused] = useState(false);
  const parts = value.split(/[,;\n\r]/);
  const activeValue = (parts.at(-1) ?? "").trim();
  const completed = new Set(
    parts.slice(0, -1).map((part) => part.trim().toLocaleLowerCase()).filter(Boolean),
  );
  const suggestions = options
    .filter((option) => !completed.has(option.toLocaleLowerCase()))
    .filter((option) => !activeValue
      || option.toLocaleLowerCase().includes(activeValue.toLocaleLowerCase()))
    .slice(0, 10);

  function chooseGenre(genre: string) {
    const previous = parts.slice(0, -1).map((part) => part.trim()).filter(Boolean);
    onChange([...previous, genre].join(", ") + ", ");
  }

  function tidyGenres() {
    setFocused(false);
    onChange(normalizeGenreText(value));
  }

  return (
    <label className="wide genre-combobox">Genre
      <input
        role="combobox"
        aria-expanded={focused && suggestions.length > 0}
        aria-autocomplete="list"
        value={value}
        placeholder="e.g. Historical, Horror"
        autoComplete="off"
        onFocus={() => setFocused(true)}
        onBlur={tidyGenres}
        onChange={(event) => onChange(event.target.value)}
      />
      {focused && suggestions.length > 0 && (
        <div className="genre-suggestions" role="listbox">
          {suggestions.map((genre) => (
            <button
              type="button"
              role="option"
              key={genre}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => chooseGenre(genre)}
            >
              {genre}
            </button>
          ))}
        </div>
      )}
      {options.length > 0 && (
        <small>Use commas or semicolons; genres are deduplicated and sorted when saved.</small>
      )}
    </label>
  );
}

function BookDialog({
  book,
  library,
  metadataOptions,
  batchMode = false,
  onClose,
  onSaved,
  onHistoryChanged,
  onOpenExisting,
}: {
  book: Book | null;
  library: Bookcase[];
  metadataOptions: MetadataOptions;
  batchMode?: boolean;
  onClose: () => void;
  onSaved: () => Promise<void>;
  onHistoryChanged?: () => Promise<void>;
  onOpenExisting: (bookId: number, title: string) => void;
}) {
  const [form, setForm] = useState<BookPayload>(
    book
      ? {
          title: book.title,
          author: book.author,
          has_multiple_authors: book.has_multiple_authors,
          structured_authors: book.structured_authors,
          isbn_10: book.isbn_10,
          isbn_13: book.isbn_13,
          subtitle: book.subtitle,
          page_count: book.page_count,
          publisher: book.publisher,
          current_ed_year: book.current_ed_year,
          original_publication_year: book.original_publication_year,
          language: book.language,
          edition_number: book.edition_number,
          fiction_category: book.fiction_category,
          binding: book.binding,
          publication_type: book.publication_type,
          genre_text: book.genre_text,
          series_name: book.series_name,
          series_volume: book.series_volume,
          status: book.status,
          goodreads_url: book.goodreads_url,
          notes: book.notes,
          acquisition_date: book.acquisition_date,
          reading_started_date: book.reading_started_date,
          read_date: book.read_date,
          is_read_date_unknown: book.is_read_date_unknown,
          is_original_collection: book.is_original_collection,
          container_id: book.container_id,
          position: book.position,
          current_loan: null,
        }
      : emptyBook,
  );
  const [saving, setSaving] = useState(false);
  const [historyBook, setHistoryBook] = useState<Book | null>(book);
  const [showHistory, setShowHistory] = useState(false);
  const [showLoanHistory, setShowLoanHistory] = useState(false);
  const [error, setError] = useState("");
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [removeCover, setRemoveCover] = useState(false);
  const [coverPreview, setCoverPreview] = useState<string | null>(
    book?.cover_filename ? api.coverUrl(book.cover_filename) : null,
  );
  const [batchMessage, setBatchMessage] = useState("");
  const [batchDirection, setBatchDirection] = useState<"UP" | "DOWN">("UP");
  const [isbnInput, setIsbnInput] = useState(book?.isbn_13 ?? book?.isbn_10 ?? "");
  const [isbnLookup, setIsbnLookup] = useState<ISBNLookupResult | null>(null);
  const [isbnLoading, setIsbnLoading] = useState(false);
  const [isbnError, setIsbnError] = useState("");
  const [isbnWaitStage, setIsbnWaitStage] = useState(0);
  const [barcodeDecoding, setBarcodeDecoding] = useState(false);
  const barcodePhotoInput = useRef<HTMLInputElement>(null);
  const [ocrLanguages, setOcrLanguages] = useState("eng+spa");
  const [ocrRunning, setOcrRunning] = useState(false);
  const [ocrProgress, setOcrProgress] = useState<CoverOcrProgress | null>(null);
  const [ocrLines, setOcrLines] = useState<string[]>([]);
  const [ocrTitle, setOcrTitle] = useState("");
  const [ocrAuthor, setOcrAuthor] = useState("");
  const [ocrMatches, setOcrMatches] = useState<CatalogueMatch[] | null>(null);
  const [ocrError, setOcrError] = useState("");
  const [ocrMatching, setOcrMatching] = useState(false);
  const ocrPhotoInput = useRef<HTMLInputElement>(null);
  const ocrAbortController = useRef<AbortController | null>(null);
  const titleInput = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
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

  function acceptReadingHistoryChange(updated: Book) {
    setHistoryBook(updated);
    setForm((current) => ({
      ...current,
      status: updated.status,
      reading_started_date: updated.reading_started_date,
      read_date: updated.read_date,
      is_read_date_unknown: updated.is_read_date_unknown,
    }));
  }

  function acceptLoanHistoryChange(updated: Book) {
    setHistoryBook(updated);
  }

  useEffect(() => {
    if (!coverFile) return;
    const preview = URL.createObjectURL(coverFile);
    setCoverPreview(preview);
    return () => URL.revokeObjectURL(preview);
  }, [coverFile]);

  useEffect(() => {
    if (!isbnLoading) {
      setIsbnWaitStage(0);
      return;
    }
    const reassurance = window.setTimeout(() => setIsbnWaitStage(1), 3500);
    const fallback = window.setTimeout(() => setIsbnWaitStage(2), 9000);
    return () => {
      window.clearTimeout(reassurance);
      window.clearTimeout(fallback);
    };
  }, [isbnLoading]);

  useEffect(
    () => () => {
      ocrAbortController.current?.abort();
    },
    [],
  );

  useEffect(() => {
    dialogRef.current?.scrollTo({ top: 0 });
  }, []);

  async function lookUpIsbn(value = isbnInput) {
    if (!value.trim()) {
      setIsbnError("Enter an ISBN-10 or ISBN-13 first.");
      return;
    }
    setIsbnLoading(true);
    setIsbnError("");
    setIsbnLookup(null);
    try {
      const result = await api.lookupIsbn(value);
      setIsbnLookup(result);
      setIsbnInput(result.isbn);
      setForm((current) => ({
        ...current,
        ...(result.isbn.length === 10
          ? { isbn_10: result.isbn }
          : { isbn_13: result.isbn }),
      }));
    } catch (err) {
      setIsbnError(err instanceof Error ? err.message : "Unable to look up ISBN");
    } finally {
      setIsbnLoading(false);
    }
  }

  async function decodeBarcodePhoto(file: File | null) {
    if (!file) return;
    setBarcodeDecoding(true);
    setIsbnError("");
    setIsbnLookup(null);
    try {
      const decodedIsbn = await decodeIsbnBarcodePhoto(file);
      setIsbnInput(decodedIsbn);
      setForm((current) => ({ ...current, isbn_13: decodedIsbn }));
      await lookUpIsbn(decodedIsbn);
    } catch (err) {
      setIsbnError(
        err instanceof Error ? err.message : "Unable to read the barcode photo",
      );
    } finally {
      setBarcodeDecoding(false);
      if (barcodePhotoInput.current) barcodePhotoInput.current.value = "";
    }
  }

  async function recognizeCoverText(file: File | null) {
    if (!file) return;
    const controller = new AbortController();
    ocrAbortController.current?.abort();
    ocrAbortController.current = controller;
    setOcrRunning(true);
    setOcrProgress({ status: "loading OCR engine", progress: 0 });
    setOcrLines([]);
    setOcrTitle("");
    setOcrAuthor("");
    setOcrMatches(null);
    setOcrError("");
    try {
      const result = await readCoverText(
        file,
        ocrLanguages.split("+"),
        setOcrProgress,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setOcrLines(result.lines);
    } catch (err) {
      if (!controller.signal.aborted) {
        setOcrError(err instanceof Error ? err.message : "Unable to read cover text");
      }
    } finally {
      if (ocrAbortController.current === controller) {
        ocrAbortController.current = null;
        setOcrRunning(false);
        setOcrProgress(null);
      }
      if (ocrPhotoInput.current) ocrPhotoInput.current.value = "";
    }
  }

  function addOcrLine(target: "title" | "author", line: string) {
    const update = (current: string) => current ? `${current} ${line}` : line;
    if (target === "title") setOcrTitle(update);
    else setOcrAuthor(update);
    setOcrMatches(null);
    setOcrError("");
  }

  async function checkOcrCatalogue() {
    if (!ocrTitle.trim() || !ocrAuthor.trim()) {
      setOcrError("Assign or type both a Title and an Author before checking.");
      return;
    }
    setOcrMatching(true);
    setOcrError("");
    try {
      setOcrMatches(await api.matchBibliography(ocrTitle, [ocrAuthor]));
    } catch (err) {
      setOcrError(
        err instanceof Error ? err.message : "Unable to check the catalogue",
      );
    } finally {
      setOcrMatching(false);
    }
  }

  function applyRecognizedText(title: string, author: string): boolean {
    const replacingTypedText = Boolean(form.title.trim() || form.author.trim());
    if (
      replacingTypedText
      && !window.confirm("Replace the current Title and Author with this result?")
    ) {
      return false;
    }
    setForm((current) => ({
      ...current,
      title,
      author,
      has_multiple_authors: false,
      structured_authors: [],
    }));
    setBatchMessage("");
    window.setTimeout(() => titleInput.current?.focus(), 0);
    return true;
  }

  function applyIsbnCandidate(
    candidate: BibliographicCandidate,
    selected: Set<CandidateMetadataKey>,
  ) {
    const candidateAuthors = candidate.authors
      .map((name) => name.replace(/\s+/g, " ").trim())
      .filter(Boolean);
    const candidateIsMultiple = candidateAuthors.length > 1;
    const candidateAuthor = candidateIsMultiple
      ? "Multiple authors"
      : candidateAuthors[0] ?? "";
    const replacingTitle = selected.has("title")
      && Boolean(form.title.trim()) && form.title !== candidate.title;
    const replacingAuthor = selected.has("author")
      && Boolean(form.author.trim()) && form.author !== candidateAuthor;
    if (
      (replacingTitle || replacingAuthor)
      && !window.confirm("Replace the selected existing values with this result?")
    ) return;

    setForm((current) => ({
      ...current,
      ...(selected.has("title") ? { title: candidate.title } : {}),
      ...(selected.has("author") ? {
        author: candidateAuthor,
        has_multiple_authors: candidateIsMultiple,
        structured_authors: candidateIsMultiple ? candidateAuthors : [],
      } : {}),
      ...(selected.has("isbn_10")
        ? { isbn_10: candidate.identifiers.isbn_10 }
        : {}),
      ...(selected.has("isbn_13")
        ? { isbn_13: candidate.identifiers.isbn_13 }
        : {}),
      ...(selected.has("subtitle") ? { subtitle: candidate.subtitle } : {}),
      ...(selected.has("page_count") ? { page_count: candidate.page_count } : {}),
      ...(selected.has("publisher") ? { publisher: candidate.publisher } : {}),
      ...(selected.has("current_ed_year")
        ? { current_ed_year: candidate.current_ed_year }
        : {}),
      ...(selected.has("original_publication_year")
        ? { original_publication_year: candidate.original_publication_year }
        : {}),
      ...(selected.has("language") ? { language: candidate.language } : {}),
      ...(selected.has("edition_number")
        ? { edition_number: candidate.edition_number }
        : {}),
      ...(selected.has("fiction_category")
        ? { fiction_category: candidate.fiction_category }
        : {}),
      ...(selected.has("binding") ? { binding: candidate.binding } : {}),
      ...(selected.has("publication_type")
        ? { publication_type: candidate.publication_type }
        : {}),
      ...(selected.has("genre_text") ? { genre_text: candidate.genre_text } : {}),
      ...(selected.has("series_name") ? { series_name: candidate.series_name } : {}),
      ...(selected.has("series_volume")
        ? { series_volume: candidate.series_volume }
        : {}),
    }));
    setBatchMessage("");
    if (selected.has("author") && candidateIsMultiple) {
      window.alert(
        "Multiple authors were supplied by the ISBN source and have been prepared for review. Please confirm that every listed person is an author, not a translator, editor, or illustrator.",
      );
    }
    window.setTimeout(() => titleInput.current?.focus(), 0);
  }

  function toggleMultipleAuthors(enabled: boolean) {
    if (enabled) {
      setForm((current) => ({
        ...current,
        has_multiple_authors: true,
        structured_authors: current.structured_authors.length >= 2
          ? current.structured_authors
          : [current.author === "Multiple authors" ? "" : current.author, ""],
      }));
      return;
    }
    if (
      form.has_multiple_authors
      && !window.confirm(
        "Switch to a single author? The structured author list will be deleted and you must enter a new Author value.",
      )
    ) return;
    setForm((current) => ({
      ...current,
      author: "",
      has_multiple_authors: false,
      structured_authors: [],
    }));
  }

  function updateStructuredAuthor(index: number, value: string) {
    setForm((current) => ({
      ...current,
      structured_authors: current.structured_authors.map((author, authorIndex) =>
        authorIndex === index ? value : author
      ),
    }));
  }

  function moveStructuredAuthor(index: number, direction: -1 | 1) {
    setForm((current) => {
      const destination = index + direction;
      if (destination < 0 || destination >= current.structured_authors.length) {
        return current;
      }
      const authors = [...current.structured_authors];
      [authors[index], authors[destination]] = [authors[destination], authors[index]];
      return { ...current, structured_authors: authors };
    });
  }

  function removeStructuredAuthor(index: number) {
    if (form.structured_authors.length === 2) {
      const remaining = form.structured_authors[1 - index].trim();
      if (
        !window.confirm(
          `Removing this author converts the book to a single-author record${
            remaining ? ` and copies “${remaining}” into Author` : ""
          }. Continue?`,
        )
      ) return;
      setForm((current) => ({
        ...current,
        author: remaining,
        has_multiple_authors: false,
        structured_authors: [],
      }));
      return;
    }
    setForm((current) => ({
      ...current,
      structured_authors: current.structured_authors.filter((_, authorIndex) =>
        authorIndex !== index
      ),
    }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    let authorFields: Pick<BookPayload, "author" | "has_multiple_authors" | "structured_authors">;
    if (form.has_multiple_authors) {
      const structuredAuthors = form.structured_authors.map((name) =>
        name.replace(/\s+/g, " ").trim()
      );
      if (structuredAuthors.length < 2 || structuredAuthors.some((name) => !name)) {
        setError("Multiple-author books require at least two complete author names.");
        return;
      }
      const normalized = structuredAuthors.map((name) => name.toLocaleLowerCase());
      if (new Set(normalized).size !== normalized.length) {
        setError("The same author cannot be listed twice.");
        return;
      }
      if (
        form.author !== "Multiple authors"
        && !window.confirm(
          'This book is marked as having multiple authors, so the Author field must be changed to exactly “Multiple authors”. Apply that required change?',
        )
      ) {
        setError('Accept the Author change to “Multiple authors”, or turn off Multiple authors.');
        return;
      }
      authorFields = {
        author: "Multiple authors",
        has_multiple_authors: true,
        structured_authors: structuredAuthors,
      };
    } else {
      authorFields = {
        author: form.author,
        has_multiple_authors: false,
        structured_authors: [],
      };
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        ...authorFields,
        genre_text: normalizeGenreText(form.genre_text ?? "") || null,
        goodreads_url: form.goodreads_url || null,
        notes: form.notes || null,
      };
      if (
        book &&
        book.reading_sessions.length > 0 &&
        book.status !== "PENDING" &&
        payload.status === "PENDING"
      ) {
        const sessions = book.reading_sessions.map((session) => {
          const dates = session.dates_unknown
            ? "dates unknown"
            : `${session.started_date ?? "unknown"} – ${session.finished_date ?? "active"}`;
          return `Reading ${session.session_number}: ${dates}`;
        }).join("\n");
        if (!window.confirm(
          `Changing this book to Pending will permanently delete ${book.reading_sessions.length} ` +
          `reading ${book.reading_sessions.length === 1 ? "session" : "sessions"}:\n\n${sessions}\n\nContinue?`,
        )) return;
      }
      let savedBook: Book;
      if (book) {
        savedBook = await api.updateBook(book.id, payload);
      } else {
        try {
          savedBook = await api.createBook(payload, false, batchDirection);
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
            const shiftingDown = detail.shift_direction === "DOWN";
            const shiftPossible = detail.shift_possible !== false;
            if (!shiftPossible) {
              setError(
                "That occupied sequence reaches position 1, so it cannot be shifted downward. Choose another position or switch to ascending.",
              );
              return;
            }
            const rangeStart = Math.min(Number(position), Number(lastPosition));
            const rangeEnd = Math.max(Number(position), Number(lastPosition));
            const destinationStart = rangeStart + (shiftingDown ? -1 : 1);
            const destinationEnd = rangeEnd + (shiftingDown ? -1 : 1);
            const approved = window.confirm(
              `Position ${position} is occupied by “${
                occupant?.title ?? "another book"
              }”${occupant?.author ? ` — ${occupant.author}` : ""}.\n\n` +
              `Make room by moving ${shiftCount} ${
                shiftCount === 1 ? "book" : "books"
              } one position ${shiftingDown ? "down" : "up"} ` +
              `(${rangeStart}–${rangeEnd} → ${destinationStart}–${destinationEnd})?`,
            );
            if (!approved) {
              setError("The book was not added. Choose another position.");
              return;
            }
            savedBook = await api.createBook(payload, true, batchDirection);
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
        const nextPosition =
          savedBook.position === null
            ? null
            : savedBook.position + (batchDirection === "DOWN" ? -1 : 1);
        setForm((current) => ({
          ...current,
          title: "",
          author: "",
          has_multiple_authors: false,
          structured_authors: [],
          isbn_10: null,
          isbn_13: null,
          subtitle: null,
          page_count: null,
          publisher: null,
          current_ed_year: null,
          original_publication_year: null,
          language: null,
          edition_number: null,
          fiction_category: null,
          binding: null,
          publication_type: null,
          genre_text: null,
          series_name: null,
          series_volume: null,
          goodreads_url: null,
          notes: null,
          reading_started_date: null,
          read_date: null,
          is_read_date_unknown: false,
          position: nextPosition && nextPosition > 0 ? nextPosition : null,
          current_loan: null,
        }));
        setCoverFile(null);
        setCoverPreview(null);
        setRemoveCover(false);
        setBatchMessage(
          `Added “${savedBook.title}”. Container retained${
            savedBook.position === null
              ? "."
              : nextPosition && nextPosition > 0
                ? `; next position is ${nextPosition}.`
                : "; position 1 reached—enter another position or switch direction."
          }`,
        );
        setIsbnInput("");
        setIsbnLookup(null);
        setIsbnError("");
        setOcrLines([]);
        setOcrTitle("");
        setOcrAuthor("");
        setOcrMatches(null);
        setOcrError("");
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
      <div
        ref={dialogRef}
        className="dialog book-dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="dialog-header">
          <div><p className="eyebrow dark">{book ? "Update catalogue" : batchMode ? "Rapid cataloguing" : "New arrival"}</p>
          <h2>{book ? "Edit book" : batchMode ? "Batch add" : "Add a book"}</h2></div>
          <button className="icon-button" onClick={onClose}><X /></button>
        </div>
        <form onSubmit={(event) => void submit(event)}>
          <p className="required-fields-note"><span aria-hidden="true">*</span> Required field</p>
          {batchMode && (
            <div className="batch-banner">
              <span>
                Container, position sequence, status, acquisition date, and
                original-collection setting stay ready for the next book.
              </span>
              <label>
                Position direction
                <select
                  value={batchDirection}
                  onChange={(event) =>
                    setBatchDirection(event.target.value as "UP" | "DOWN")
                  }
                >
                  <option value="UP">Ascending · 6 → 7 → 8</option>
                  <option value="DOWN">Descending · 6 → 5 → 4</option>
                </select>
              </label>
            </div>
          )}
          <div className="form-grid">
            <fieldset className="wide isbn-field">
                <legend>Identify book</legend>
                <div className="isbn-lookup-row">
                  <label>
                    ISBN-10 or ISBN-13
                    <input
                      value={isbnInput}
                      maxLength={40}
                      inputMode="text"
                      autoCapitalize="characters"
                      placeholder="978-…"
                      onChange={(event) => {
                        setIsbnInput(event.target.value);
                        setIsbnLookup(null);
                        setIsbnError("");
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          void lookUpIsbn();
                        }
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="outline-button"
                    disabled={isbnLoading}
                    onClick={() => void lookUpIsbn()}
                  >
                    <ScanBarcode size={17} />
                    {isbnLoading ? "Looking up…" : "Look up ISBN"}
                  </button>
                  <label
                    className={`outline-button barcode-photo-button${
                      barcodeDecoding ? " busy" : ""
                    }`}
                    aria-disabled={barcodeDecoding || isbnLoading}
                  >
                    {barcodeDecoding ? (
                      <LoaderCircle size={17} />
                    ) : (
                      <Camera size={17} />
                    )}
                    {barcodeDecoding ? "Reading photo…" : "Photograph barcode"}
                    <input
                      ref={barcodePhotoInput}
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      capture="environment"
                      disabled={barcodeDecoding || isbnLoading}
                      onChange={(event) =>
                        void decodeBarcodePhoto(event.target.files?.[0] ?? null)
                      }
                    />
                  </label>
                </div>
                <small>
                  Lookup and barcode recognition fill the stored ISBN fields below
                  and check the catalogue. Nothing is saved until you submit the book.
                </small>
                <div className="isbn-storage-grid">
                  <label>
                    Stored ISBN-10
                    <input
                      value={form.isbn_10 ?? ""}
                      maxLength={40}
                      inputMode="text"
                      autoCapitalize="characters"
                      placeholder="0-…"
                      onChange={(event) =>
                        setForm({ ...form, isbn_10: event.target.value || null })
                      }
                    />
                  </label>
                  <label>
                    Stored ISBN-13
                    <input
                      value={form.isbn_13 ?? ""}
                      maxLength={40}
                      inputMode="numeric"
                      placeholder="978-…"
                      onChange={(event) =>
                        setForm({ ...form, isbn_13: event.target.value || null })
                      }
                    />
                  </label>
                </div>
                <div className="ocr-tools">
                  <label>
                    Cover OCR language
                    <select
                      value={ocrLanguages}
                      disabled={ocrRunning}
                      onChange={(event) => setOcrLanguages(event.target.value)}
                    >
                      <option value="eng+spa">English + Spanish</option>
                      <option value="eng">English</option>
                      <option value="spa">Spanish</option>
                      <option value="glg">Galician</option>
                    </select>
                  </label>
                  <label
                    className={`outline-button ocr-photo-button${
                      ocrRunning ? " busy" : ""
                    }`}
                    aria-disabled={ocrRunning}
                  >
                    {ocrRunning ? <LoaderCircle size={17} /> : <Camera size={17} />}
                    {ocrRunning ? "Reading cover…" : "Read cover text"}
                    <input
                      ref={ocrPhotoInput}
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      capture="environment"
                      disabled={ocrRunning}
                      onChange={(event) =>
                        void recognizeCoverText(event.target.files?.[0] ?? null)
                      }
                    />
                  </label>
                </div>
                {isbnLoading && (
                  <div className="isbn-progress" role="status" aria-live="polite">
                    <LoaderCircle size={18} />
                    <span>
                      {isbnWaitStage === 0
                        ? "Checking Open Library and your BOOKPILE catalogue…"
                        : isbnWaitStage === 1
                          ? "Still searching—some editions take a little longer…"
                          : "Trying the available bibliographic sources…"}
                    </span>
                  </div>
                )}
                {barcodeDecoding && (
                  <div className="isbn-progress" role="status" aria-live="polite">
                    <LoaderCircle size={18} />
                    <span>Reading the barcode locally; the photo is not uploaded…</span>
                  </div>
                )}
                {ocrRunning && (
                  <div className="ocr-progress" role="status" aria-live="polite">
                    <div>
                      <LoaderCircle size={18} />
                      <span>
                        {ocrProgress?.status.replaceAll("_", " ")
                          ?? "Loading OCR engine"}
                      </span>
                      <strong>
                        {Math.round((ocrProgress?.progress ?? 0) * 100)}%
                      </strong>
                    </div>
                    <progress value={ocrProgress?.progress ?? 0} max={1} />
                    <small>
                      The first use downloads language data. Recognition then runs
                      locally; the cover photo is not uploaded.
                    </small>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => ocrAbortController.current?.abort()}
                    >
                      Cancel OCR
                    </button>
                  </div>
                )}
                {ocrError && <div className="isbn-message error">{ocrError}</div>}
                {ocrLines.length > 0 && (
                  <div className="ocr-result">
                    <div className="ocr-result-heading">
                      <strong>Recognized cover lines</strong>
                      <span>Tap lines in reading order, then correct the fields.</span>
                    </div>
                    <div className="ocr-lines">
                      {ocrLines.map((line, index) => (
                        <div className="ocr-line" key={`${line}-${index}`}>
                          <span>{line}</span>
                          <div>
                            <button
                              type="button"
                              onClick={() => addOcrLine("title", line)}
                            >
                              → Title
                            </button>
                            <button
                              type="button"
                              onClick={() => addOcrLine("author", line)}
                            >
                              → Author
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="ocr-draft">
                      <label>
                        Proposed Title
                        <input
                          value={ocrTitle}
                          onChange={(event) => {
                            setOcrTitle(event.target.value);
                            setOcrMatches(null);
                          }}
                        />
                      </label>
                      <label>
                        Proposed Author
                        <input
                          value={ocrAuthor}
                          onChange={(event) => {
                            setOcrAuthor(event.target.value);
                            setOcrMatches(null);
                          }}
                        />
                      </label>
                    </div>
                    <button
                      type="button"
                      className="outline-button ocr-check-button"
                      disabled={ocrMatching}
                      onClick={() => void checkOcrCatalogue()}
                    >
                      <Search size={16} />
                      {ocrMatching ? "Checking…" : "Check BOOKPILE catalogue"}
                    </button>
                    {ocrMatches !== null && (
                      <div className="ocr-match-result">
                        {ocrMatches.length === 0 ? (
                          <p>No likely catalogue match was found.</p>
                        ) : (
                          <div className="isbn-matches">
                            <strong>
                              {ocrMatches.some((match) => match.match_class === "strong")
                                ? "Likely already in BOOKPILE"
                                : "Possible catalogue match"}
                            </strong>
                            {ocrMatches.map((match) => (
                              <div className="isbn-match" key={match.book_id}>
                                <span>
                                  <b>{match.title}</b> · {match.author}
                                  {match.location_label && (
                                    <small>{match.location_label}</small>
                                  )}
                                </span>
                                <button
                                  type="button"
                                  className="text-button"
                                  onClick={() =>
                                    onOpenExisting(match.book_id, match.title)
                                  }
                                >
                                  Open existing
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => applyRecognizedText(ocrTitle, ocrAuthor)}
                        >
                          {ocrMatches.length ? "Use Title & Author anyway" : "Use Title & Author"}
                        </button>
                      </div>
                    )}
                  </div>
                )}
                {isbnError && <div className="isbn-message error">{isbnError}</div>}
                {isbnLookup && isbnLookup.catalogue_matches.length > 0 && (
                  <div className="isbn-matches isbn-direct-matches">
                    <strong>Exact ISBN already in BOOKPILE</strong>
                    {isbnLookup.catalogue_matches.map((match) => (
                      <div className="isbn-match" key={match.book_id}>
                        <span>
                          <b>{match.title}</b> · {match.author}
                          {match.location_label && <small>{match.location_label}</small>}
                        </span>
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => onOpenExisting(match.book_id, match.title)}
                        >
                          Open existing
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {isbnLookup && isbnLookup.candidates.length === 0
                  && isbnLookup.catalogue_matches.length === 0 && (
                  <div className="isbn-message">
                    No bibliographic result was found for {isbnLookup.isbn}. You
                    can continue with manual entry.
                  </div>
                )}
                {isbnLookup?.candidates.map((candidate, candidateIndex) => (
                  <article
                    className="isbn-candidate"
                    key={`${candidate.source}-${candidate.source_record_id ?? candidateIndex}`}
                  >
                    <div className="isbn-candidate-copy">
                      <span>{candidate.source.replaceAll("_", " ")}</span>
                      <strong>{candidate.title}</strong>
                      <p>{candidate.authors.join(" · ")}</p>
                      {(candidate.publisher || candidate.current_ed_year) && (
                        <small>
                          {[candidate.publisher, candidate.current_ed_year]
                            .filter(Boolean)
                            .join(" · ")}
                        </small>
                      )}
                    </div>
                    <CandidateMetadataReview
                      candidate={candidate}
                      onApply={(selected) => applyIsbnCandidate(candidate, selected)}
                    />
                    {candidate.catalogue_matches.length > 0
                      && isbnLookup.catalogue_matches.length === 0 && (
                      <div className="isbn-matches">
                        <strong>
                          {candidate.catalogue_matches.some(
                            (match) => match.match_class === "strong",
                          )
                            ? "Likely already in BOOKPILE"
                            : "Possible catalogue match"}
                        </strong>
                        {candidate.catalogue_matches.map((match) => (
                          <div className="isbn-match" key={match.book_id}>
                            <span>
                              <b>{match.title}</b> · {match.author}
                              {match.location_label && (
                                <small>{match.location_label}</small>
                              )}
                            </span>
                            <button
                              type="button"
                              className="text-button"
                              onClick={() => onOpenExisting(match.book_id, match.title)}
                            >
                              Open existing
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
              </fieldset>
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
            <label className="wide">Title <span className="required-marker" aria-hidden="true">*</span>
              <input ref={titleInput} required aria-required="true" value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </label>
            <label className="wide">Author <span className="required-marker" aria-hidden="true">*</span>
              <input
                required
                aria-required="true"
                readOnly={form.has_multiple_authors}
                value={form.author}
                onChange={(e) => setForm({ ...form, author: e.target.value })} />
            </label>
            <fieldset className="wide structured-authors-field">
              <legend>Authorship</legend>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={form.has_multiple_authors}
                  onChange={(event) => toggleMultipleAuthors(event.target.checked)}
                />
                Multiple authors
              </label>
              {form.has_multiple_authors && (
                <div className="structured-author-editor">
                  <p>
                    Enter authors only, in display order. Translators, editors,
                    and illustrators should not be included. At least two names
                    are required.
                  </p>
                  {form.structured_authors.map((author, index) => (
                    <div className="structured-author-row" key={index}>
                      <span>{index + 1}</span>
                      <input
                        aria-label={`Author ${index + 1}`}
                        required
                        maxLength={300}
                        value={author}
                        onChange={(event) => updateStructuredAuthor(index, event.target.value)}
                      />
                      <button
                        type="button"
                        aria-label={`Move author ${index + 1} up`}
                        title="Move up"
                        disabled={index === 0}
                        onClick={() => moveStructuredAuthor(index, -1)}
                      >↑</button>
                      <button
                        type="button"
                        aria-label={`Move author ${index + 1} down`}
                        title="Move down"
                        disabled={index === form.structured_authors.length - 1}
                        onClick={() => moveStructuredAuthor(index, 1)}
                      >↓</button>
                      <button
                        type="button"
                        aria-label={`Remove author ${index + 1}`}
                        title="Remove author"
                        onClick={() => removeStructuredAuthor(index)}
                      ><Trash2 size={15} /></button>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="outline-button add-structured-author"
                    onClick={() => setForm((current) => ({
                      ...current,
                      structured_authors: [...current.structured_authors, ""],
                    }))}
                  >
                    <Plus size={15} /> Add author
                  </button>
                </div>
              )}
            </fieldset>
            <fieldset className="wide metadata-fields">
              <legend>Edition and classification</legend>
              <div className="metadata-form-grid">
                <label className="wide">Subtitle
                  <input value={form.subtitle ?? ""}
                    onChange={(e) => setForm({ ...form, subtitle: e.target.value || null })} />
                </label>
                <label>Number of pages
                  <input type="number" min="1" value={form.page_count ?? ""}
                    onChange={(e) => setForm({ ...form, page_count: e.target.value ? Number(e.target.value) : null })} />
                </label>
                <ExistingValueInput
                  label="Publisher"
                  value={form.publisher ?? ""}
                  options={metadataOptions.publishers}
                  onChange={(value) => setForm({ ...form, publisher: value || null })}
                />
                <label>Current edition year
                  <input type="number" min="1000" max="9999" placeholder="YYYY"
                    value={form.current_ed_year ?? ""}
                    onChange={(e) => setForm({ ...form, current_ed_year: e.target.value ? Number(e.target.value) : null })} />
                </label>
                <label>Original publication year
                  <input type="number" min="1000" max="9999" placeholder="YYYY"
                    value={form.original_publication_year ?? ""}
                    onChange={(e) => setForm({ ...form, original_publication_year: e.target.value ? Number(e.target.value) : null })} />
                </label>
                <ExistingValueInput
                  label="Language"
                  value={form.language ?? ""}
                  options={metadataOptions.languages}
                  onChange={(value) => setForm({ ...form, language: value || null })}
                />
                <label>Edition number
                  <input type="number" min="1" value={form.edition_number ?? ""}
                    onChange={(e) => setForm({ ...form, edition_number: e.target.value ? Number(e.target.value) : null })} />
                </label>
                <label>Category
                  <select value={form.fiction_category ?? ""}
                    onChange={(e) => setForm({ ...form, fiction_category: (e.target.value || null) as FictionCategory | null })}>
                    <option value="">Not classified</option>
                    <option value="FICTION">Fiction</option>
                    <option value="NON_FICTION">Non-fiction</option>
                  </select>
                </label>
                <label>Binding
                  <select value={form.binding ?? ""}
                    onChange={(e) => setForm({ ...form, binding: (e.target.value || null) as Binding | null })}>
                    <option value="">Not recorded</option>
                    <option value="HARDCOVER">Hardcover</option>
                    <option value="PAPERBACK">Paperback</option>
                    <option value="FLEXIBOUND">Flexibound</option>
                    <option value="SPIRAL">Spiral-bound</option>
                    <option value="STAPLED">Stapled</option>
                    <option value="OTHER">Other</option>
                  </select>
                </label>
                <label>Publication type
                  <select value={form.publication_type ?? ""}
                    onChange={(e) => setForm({ ...form, publication_type: (e.target.value || null) as PublicationType | null })}>
                    <option value="">Not classified</option>
                    <option value="CONVENTIONAL_BOOK">Conventional book</option>
                    <option value="COMIC_GRAPHIC_NOVEL">Comic / Graphic novel</option>
                    <option value="ATLAS">Atlas</option>
                    <option value="REFERENCE">Reference work</option>
                    <option value="ART_PHOTOGRAPHY_ILLUSTRATED">Art / Photography / Illustrated</option>
                    <option value="MAGAZINE_PERIODICAL">Magazine / Periodical</option>
                    <option value="OTHER">Other</option>
                  </select>
                </label>
                <ExistingValueInput
                  label="Series"
                  value={form.series_name ?? ""}
                  options={metadataOptions.series_names}
                  onChange={(value) => setForm({ ...form, series_name: value || null })}
                />
                <label>Series volume
                  <input value={form.series_volume ?? ""} placeholder="e.g. 0.5, III, Omnibus 1"
                    onChange={(e) => setForm({ ...form, series_volume: e.target.value || null })} />
                </label>
                <GenreSuggestionInput
                  value={form.genre_text ?? ""}
                  options={metadataOptions.genres}
                  onChange={(value) => setForm({ ...form, genre_text: value || null })}
                />
              </div>
            </fieldset>
            <label>Status
              <select value={form.status}
                onChange={(e) => {
                  const status = e.target.value as BookStatus;
                  const today = new Date().toISOString().slice(0, 10);
                  const suggestedStarted = latestDate(
                    today,
                    form.acquisition_date,
                  );
                  const suggestedFinished = latestDate(
                    today,
                    form.acquisition_date,
                    form.reading_started_date,
                  );
                  setForm({
                    ...form,
                    status,
                    ...(status === "CURRENTLY_READING" && !form.reading_started_date
                      ? { reading_started_date: suggestedStarted }
                      : {}),
                    ...(status === "READ" && !form.read_date
                      && !form.is_read_date_unknown
                      ? { read_date: suggestedFinished }
                      : {}),
                    ...(status === "CURRENTLY_READING"
                      ? {
                          is_read_date_unknown: false,
                        }
                      : status !== "READ"
                        ? { is_read_date_unknown: false }
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
                onChange={(e) => setForm({ ...form, position: e.target.value ? Number(e.target.value) : null })} />
            </label>
            <label className="wide">Physical container
              <select value={form.container_id ?? ""}
                onChange={(e) => setForm({ ...form, container_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Not assigned</option>
                {containers.map((container) => (
                  <option key={container.id} value={container.id}>{container.label}</option>
                ))}
              </select>
              {form.status === "CURRENTLY_READING" && (
                <small>The saved return location is retained while the book appears in the map's reading area.</small>
              )}
              {containers.length === 0 && <small>Create your library layout first to assign a location.</small>}
            </label>
            {!book && (
              <fieldset className="wide loan-on-add-fields">
                <legend>Availability</legend>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={Boolean(form.current_loan)}
                    onChange={(event) => setForm({
                      ...form,
                      current_loan: event.target.checked ? {
                        loaned_to: "",
                        loaned_date: new Date().toISOString().slice(0, 10),
                        expected_return_date: null,
                        notes: null,
                      } : null,
                    })}
                  />
                  This book is already on loan
                </label>
                {form.current_loan && (
                  <div className="loan-form inline-loan-form">
                    <label>Loaned to <span className="required-marker">*</span>
                      <input required maxLength={300} value={form.current_loan.loaned_to} onChange={(event) => setForm({ ...form, current_loan: { ...form.current_loan!, loaned_to: event.target.value } })} />
                    </label>
                    <label className="checkbox-label">
                      <input type="checkbox" checked={form.current_loan.loaned_date === null} onChange={(event) => setForm({ ...form, current_loan: { ...form.current_loan!, loaned_date: event.target.checked ? null : new Date().toISOString().slice(0, 10) } })} />
                      Loan date unknown
                    </label>
                    {form.current_loan.loaned_date !== null && (
                      <label>Loaned date<input type="date" max={new Date().toISOString().slice(0, 10)} value={form.current_loan.loaned_date} onChange={(event) => setForm({ ...form, current_loan: { ...form.current_loan!, loaned_date: event.target.value || null } })} /></label>
                    )}
                    <label>Expected return<input type="date" min={form.current_loan.loaned_date ?? undefined} value={form.current_loan.expected_return_date ?? ""} onChange={(event) => setForm({ ...form, current_loan: { ...form.current_loan!, expected_return_date: event.target.value || null } })} /></label>
                    <label className="wide">Loan notes<textarea rows={2} maxLength={4000} value={form.current_loan.notes ?? ""} onChange={(event) => setForm({ ...form, current_loan: { ...form.current_loan!, notes: event.target.value || null } })} /></label>
                  </div>
                )}
              </fieldset>
            )}
            {book && historyBook && (
              <fieldset className="wide edit-loan-history">
                <legend>Loan history</legend>
                <div className="wide edit-reading-history">
                  <div>
                    <strong>{historyBook.is_on_loan ? `On loan to ${historyBook.active_loan?.loaned_to}` : "Available"}</strong>
                    <span>{historyBook.loan_count} {historyBook.loan_count === 1 ? "loan" : "loans"} recorded</span>
                  </div>
                  <button type="button" className="outline-button" onClick={() => setShowLoanHistory(true)}>Manage loan history</button>
                </div>
              </fieldset>
            )}
            <fieldset className="wide date-fields">
              <legend>Book history</legend>
              {book && historyBook && (
                <div className="wide edit-reading-history">
                  <div>
                    <strong>Reading sessions</strong>
                    <span>
                      {historyBook.reading_session_count === 0
                        ? "No reading history"
                        : `${historyBook.reading_session_count} ${historyBook.reading_session_count === 1 ? "session" : "sessions"} recorded`}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="outline-button"
                    onClick={() => setShowHistory(true)}
                  >
                    Manage reading history
                  </button>
                </div>
              )}
              <label>Acquired
                <span className="date-input-row">
                  <input
                    type="date"
                    value={form.acquisition_date ?? ""}
                    max={earliestDate(
                      form.reading_started_date,
                      form.read_date,
                    )}
                    onChange={(e) => setForm({
                      ...form,
                      acquisition_date: e.target.value || null,
                      is_original_collection: false,
                    })}
                  />
                  <button
                    type="button"
                    disabled={!form.acquisition_date}
                    onClick={() => setForm({
                      ...form,
                      acquisition_date: null,
                    })}
                  >
                    Clear
                  </button>
                </span>
              </label>
              <label>Reading started
                <span className="date-input-row">
                  <input
                    type="date"
                    value={form.reading_started_date ?? ""}
                    min={form.acquisition_date ?? undefined}
                    max={form.read_date ?? undefined}
                    onChange={(e) => setForm({
                      ...form,
                      reading_started_date: e.target.value || null,
                    })}
                  />
                  <button
                    type="button"
                    disabled={!form.reading_started_date}
                    onClick={() => setForm({
                      ...form,
                      reading_started_date: null,
                    })}
                  >
                    Clear
                  </button>
                </span>
              </label>
              <label>Finished reading
                <span className="date-input-row">
                  <input
                    type="date"
                    value={form.read_date ?? ""}
                    min={latestDate(
                      form.acquisition_date,
                      form.reading_started_date,
                    ) || undefined}
                    disabled={form.is_read_date_unknown}
                    onChange={(e) => setForm({
                      ...form,
                      read_date: e.target.value || null,
                      is_read_date_unknown: false,
                    })}
                  />
                  <button
                    type="button"
                    disabled={!form.read_date}
                    onClick={() => setForm({
                      ...form,
                      read_date: null,
                      is_read_date_unknown: form.status === "READ",
                    })}
                  >
                    Clear
                  </button>
                </span>
              </label>
              {form.status === "READ" && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={form.is_read_date_unknown}
                    onChange={(e) => setForm({
                      ...form,
                      is_read_date_unknown: e.target.checked,
                      read_date: e.target.checked
                        ? null
                        : latestDate(
                            new Date().toISOString().slice(0, 10),
                            form.acquisition_date,
                            form.reading_started_date,
                          ),
                    })}
                  />
                  Reading date unknown
                </label>
              )}
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={form.is_original_collection}
                  onChange={(e) => setForm({
                    ...form,
                    is_original_collection: e.target.checked,
                    ...(e.target.checked ? { acquisition_date: null } : {}),
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
        {showHistory && historyBook && (
          <ReadingHistoryDialog
            book={historyBook}
            onClose={() => setShowHistory(false)}
            onChanged={acceptReadingHistoryChange}
            onCatalogueChanged={onHistoryChanged}
          />
        )}
        {showLoanHistory && historyBook && (
          <LoanHistoryDialog
            book={historyBook}
            onClose={() => setShowLoanHistory(false)}
            onChanged={acceptLoanHistoryChange}
            onCatalogueChanged={onHistoryChanged}
          />
        )}
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
  const [bookcaseDescription, setBookcaseDescription] = useState("");
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
  const [editingBookcaseId, setEditingBookcaseId] = useState<number | null>(null);
  const [bookcaseNameDraft, setBookcaseNameDraft] = useState("");
  const [bookcaseDescriptionDraft, setBookcaseDescriptionDraft] = useState("");
  const [editingShelfId, setEditingShelfId] = useState<number | null>(null);
  const [shelfNumberDraft, setShelfNumberDraft] = useState(1);
  const [editingContainerId, setEditingContainerId] = useState<number | null>(null);
  const [containerNumberDraft, setContainerNumberDraft] = useState(1);

  async function act(action: () => Promise<unknown>): Promise<boolean> {
    setError("");
    try {
      await action();
      await onChanged();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update layout");
      return false;
    }
  }

  async function saveBookcase(bookcaseId: number) {
    if (!bookcaseNameDraft.trim()) return;
    if (await act(() => api.updateBookcase(
      bookcaseId,
      bookcaseNameDraft,
      bookcaseDescriptionDraft,
    ))) {
      setEditingBookcaseId(null);
    }
  }

  async function saveShelf(shelfId: number) {
    if (await act(() => api.updateShelf(shelfId, shelfNumberDraft))) {
      setEditingShelfId(null);
    }
  }

  async function saveContainer(containerId: number) {
    if (await act(() => api.updateContainer(containerId, containerNumberDraft))) {
      setEditingContainerId(null);
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
            <textarea
              rows={2}
              placeholder="Optional description"
              value={bookcaseDescription}
              onChange={(e) => setBookcaseDescription(e.target.value)}
            />
            <button disabled={!bookcaseName.trim()} onClick={() => void act(async () => {
              await api.createBookcase(bookcaseName, bookcaseDescription);
              setBookcaseName("");
              setBookcaseDescription("");
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
                {editingBookcaseId === bookcase.id ? (
                  <div className="hierarchy-edit bookcase-edit">
                    <input
                      aria-label="Bookcase name"
                      value={bookcaseNameDraft}
                      onChange={(event) => setBookcaseNameDraft(event.target.value)}
                    />
                    <textarea
                      aria-label="Bookcase description"
                      rows={2}
                      placeholder="Optional description"
                      value={bookcaseDescriptionDraft}
                      onChange={(event) => setBookcaseDescriptionDraft(event.target.value)}
                    />
                    <div className="hierarchy-edit-actions">
                      <button
                        title="Save bookcase"
                        disabled={!bookcaseNameDraft.trim()}
                        onClick={() => void saveBookcase(bookcase.id)}
                      ><Save size={15} /></button>
                      <button
                        title="Cancel editing"
                        onClick={() => setEditingBookcaseId(null)}
                      ><X size={15} /></button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div>
                      <strong>{bookcase.name}</strong>
                      <span>
                        {bookcase.shelves.length} shelves ·{" "}
                        {bookcase.shelves.reduce((n, shelf) => n + shelf.containers.length, 0)} containers
                      </span>
                      {bookcase.description && (
                        <small className="bookcase-description">{bookcase.description}</small>
                      )}
                    </div>
                    <button
                      className="edit-hierarchy-button"
                      title="Edit bookcase"
                      onClick={() => {
                        setEditingBookcaseId(bookcase.id);
                        setBookcaseNameDraft(bookcase.name);
                        setBookcaseDescriptionDraft(bookcase.description ?? "");
                      }}
                    ><Pencil size={15} /></button>
                  </>
                )}
              </div>
              {bookcase.shelves.length === 0 ? (
                <p className="muted">No shelves in this bookcase.</p>
              ) : bookcase.shelves.map((shelf) => (
                <div className="shelf-block" key={shelf.id}>
                  <div className="shelf-heading">
                    {editingShelfId === shelf.id ? (
                      <div className="hierarchy-edit compact-edit">
                        <label>
                          Shelf number
                          <input
                            type="number"
                            min="1"
                            value={shelfNumberDraft}
                            onChange={(event) => setShelfNumberDraft(Number(event.target.value))}
                          />
                        </label>
                        <div className="hierarchy-edit-actions">
                          <button
                            title="Save shelf number"
                            disabled={shelfNumberDraft < 1}
                            onClick={() => void saveShelf(shelf.id)}
                          ><Save size={15} /></button>
                          <button
                            title="Cancel editing"
                            onClick={() => setEditingShelfId(null)}
                          ><X size={15} /></button>
                        </div>
                      </div>
                    ) : (
                      <strong>Shelf {shelf.shelf_number}</strong>
                    )}
                    <span>{shelf.containers.length} containers</span>
                    {editingShelfId !== shelf.id && (
                      <button
                        className="edit-hierarchy-button"
                        title="Renumber shelf"
                        onClick={() => {
                          setEditingShelfId(shelf.id);
                          setShelfNumberDraft(shelf.shelf_number);
                        }}
                      ><Pencil size={15} /></button>
                    )}
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
                        {editingContainerId === container.id ? (
                          <div className="hierarchy-edit compact-edit container-edit">
                            <span>
                              {container.layer === "BACKGROUND" ? "Background" : "Foreground"}{" "}
                              {container.container_type === "ROW" ? "Row" : "Pile"}
                            </span>
                            <input
                              aria-label="Container number"
                              type="number"
                              min="1"
                              value={containerNumberDraft}
                              onChange={(event) => setContainerNumberDraft(Number(event.target.value))}
                            />
                            <div className="hierarchy-edit-actions">
                              <button
                                title="Save container number"
                                disabled={containerNumberDraft < 1}
                                onClick={() => void saveContainer(container.id)}
                              ><Save size={14} /></button>
                              <button
                                title="Cancel editing"
                                onClick={() => setEditingContainerId(null)}
                              ><X size={14} /></button>
                            </div>
                          </div>
                        ) : (
                          <span>
                            {container.layer === "BACKGROUND" ? "Background" : "Foreground"}{" "}
                            {container.container_type === "ROW" ? "Row" : "Pile"}{" "}
                            {container.container_number}
                          </span>
                        )}
                        <small>{container.book_count} books</small>
                        {editingContainerId !== container.id && (
                          <button
                            className="edit-hierarchy-button"
                            title="Renumber container"
                            onClick={() => {
                              setEditingContainerId(container.id);
                              setContainerNumberDraft(container.container_number);
                            }}
                          ><Pencil size={14} /></button>
                        )}
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

const MAP_WIDTH = 960;
const MAP_INSET = 22;
const MAP_HEIGHT = 620;
const MAP_RETAINED_SPACES_STORAGE_KEY = "bookpile-map-retained-spaces";

function initialRetainedSpacesPreference(): boolean {
  try {
    return window.localStorage.getItem(MAP_RETAINED_SPACES_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

type MapColourMode =
  | "status"
  | "acquisition"
  | "finished"
  | "pending_duration"
  | "reading_duration"
  | "reading_rate"
  | "language"
  | "current_ed_year"
  | "original_publication_year"
  | "genre"
  | "fiction_category"
  | "binding"
  | "publication_type";

interface MapColourScale {
  mode: MapColourMode;
  label: string;
  colour: (book: MapBook) => string;
  detail: (book: MapBook) => string | null;
  lowLabel?: string;
  highLabel?: string;
  legendItems: Array<{ label: string; colour: string }>;
  continuous: boolean;
}

const MAP_COLOUR_OPTIONS: Array<{ value: MapColourMode; label: string }> = [
  { value: "status", label: "Reading status" },
  { value: "acquisition", label: "Acquisition recency" },
  { value: "finished", label: "Reading recency" },
  { value: "pending_duration", label: "Time spent pending" },
  { value: "reading_duration", label: "Reading duration" },
  { value: "reading_rate", label: "Reading rate (pages/day)" },
  { value: "language", label: "Language" },
  { value: "current_ed_year", label: "Current edition year" },
  { value: "original_publication_year", label: "Original publication year" },
  { value: "genre", label: "Genre focus" },
  { value: "fiction_category", label: "Fiction / non-fiction" },
  { value: "binding", label: "Binding" },
  { value: "publication_type", label: "Publication type" },
];

const MISSING_MAP_COLOUR = "#e5dfd5";
const PENDING_MAP_COLOUR = "#d7ae6c";
const READING_MAP_COLOUR = "#7699a7";
const LIGHT_MAP_COLOUR = "#d7e8ec";
const DARK_MAP_COLOUR = "#8b4035";
const FOCUSED_GENRE_COLOUR = "#397f73";
const CATEGORY_MAP_COLOURS = [
  "#397f73", "#b46f4f", "#537c9a", "#b08a3f", "#7d668f",
  "#698453", "#a55c6b", "#4f8688", "#8c704c", "#6f7796",
];

function statusBookColour(status: BookStatus) {
  if (status === "READ") return "#4f887b";
  if (status === "CURRENTLY_READING") return "#557f93";
  return "#d29a46";
}

function dateAsDay(value: string | null) {
  if (!value) return null;
  return Math.floor(Date.parse(`${value}T00:00:00Z`) / 86_400_000);
}

function durationInDays(start: string | null, end: string | null) {
  const startDay = dateAsDay(start);
  const endDay = dateAsDay(end);
  if (startDay === null || endDay === null) return null;
  return Math.max(0, endDay - startDay) + 1;
}

function metricForBook(book: MapBook, mode: MapColourMode) {
  if (mode === "acquisition") return dateAsDay(book.acquisition_date);
  if (mode === "finished") return dateAsDay(book.read_date);
  if (mode === "pending_duration") {
    return durationInDays(book.acquisition_date, book.reading_started_date);
  }
  if (mode === "reading_duration") {
    return durationInDays(book.reading_started_date, book.read_date);
  }
  if (mode === "reading_rate") {
    if (!book.page_count || !book.read_date) return null;
    const duration = book.reading_started_date
      ? durationInDays(book.reading_started_date, book.read_date)
      : 1;
    return duration ? book.page_count / duration : null;
  }
  if (mode === "current_ed_year") return book.current_ed_year;
  if (mode === "original_publication_year") return book.original_publication_year;
  return null;
}

function categoricalMapValue(book: MapBook, mode: MapColourMode) {
  if (mode === "language") return book.language;
  if (mode === "fiction_category") return book.fiction_category;
  if (mode === "binding") return book.binding;
  if (mode === "publication_type") return book.publication_type;
  return null;
}

function bookGenres(book: MapBook) {
  return (book.genre_text ?? "").split(",").map((value) => value.trim()).filter(Boolean);
}

function interpolateHex(start: string, end: string, amount: number) {
  const channel = (value: string, offset: number) =>
    Number.parseInt(value.slice(offset, offset + 2), 16);
  const mix = (offset: number) =>
    Math.round(
      channel(start, offset) +
      (channel(end, offset) - channel(start, offset)) * amount,
    ).toString(16).padStart(2, "0");
  return `#${mix(1)}${mix(3)}${mix(5)}`;
}

function dayAsDate(day: number) {
  return new Date(day * 86_400_000).toISOString().slice(0, 10);
}

function specialMapCategory(book: MapBook, mode: MapColourMode) {
  if (mode === "acquisition" && !book.acquisition_date) {
    return { label: "No acquisition date", colour: MISSING_MAP_COLOUR };
  }
  if (mode === "finished") {
    if (book.status === "PENDING") {
      return { label: "Pending", colour: PENDING_MAP_COLOUR };
    }
    if (book.status === "CURRENTLY_READING") {
      return { label: "Reading…", colour: READING_MAP_COLOUR };
    }
    if (!book.read_date) {
      return { label: "Read · date unknown", colour: MISSING_MAP_COLOUR };
    }
  }
  if (mode === "pending_duration") {
    if (book.status === "PENDING") {
      return { label: "Still pending", colour: PENDING_MAP_COLOUR };
    }
    if (metricForBook(book, mode) === null) {
      return book.status === "CURRENTLY_READING"
        ? { label: "Reading · no dates", colour: READING_MAP_COLOUR }
        : { label: "Read · no dates", colour: MISSING_MAP_COLOUR };
    }
  }
  if (mode === "reading_duration") {
    if (book.status === "PENDING") {
      return { label: "Pending", colour: PENDING_MAP_COLOUR };
    }
    if (book.status === "CURRENTLY_READING") {
      return { label: "Still reading", colour: READING_MAP_COLOUR };
    }
    if (metricForBook(book, mode) === null) {
      return { label: "Read · no dates", colour: MISSING_MAP_COLOUR };
    }
  }
  if (mode === "reading_rate") {
    if (book.status === "PENDING") {
      return { label: "Pending", colour: PENDING_MAP_COLOUR };
    }
    if (book.status === "CURRENTLY_READING") {
      return { label: "Still reading", colour: READING_MAP_COLOUR };
    }
    if (!book.read_date) {
      return { label: "Read · date unknown", colour: MISSING_MAP_COLOUR };
    }
    if (!book.page_count) {
      return { label: "Read · pages unknown", colour: MISSING_MAP_COLOUR };
    }
  }
  if (
    (mode === "current_ed_year" || mode === "original_publication_year")
    && metricForBook(book, mode) === null
  ) {
    return { label: "No year recorded", colour: MISSING_MAP_COLOUR };
  }
  return null;
}

function percentile(sortedValues: number[], fraction: number) {
  if (sortedValues.length === 0) return 0;
  const index = (sortedValues.length - 1) * fraction;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sortedValues[lower];
  const amount = index - lower;
  return sortedValues[lower] + (sortedValues[upper] - sortedValues[lower]) * amount;
}

function buildMapColourScale(
  mode: MapColourMode,
  books: MapBook[],
  selectedGenre = "",
): MapColourScale {
  const option = MAP_COLOUR_OPTIONS.find((item) => item.value === mode);
  if (mode === "status") {
    return {
      mode,
      label: option?.label ?? "Reading status",
      colour: (book) => statusBookColour(book.status),
      detail: () => null,
      legendItems: [],
      continuous: false,
    };
  }

  if (mode === "genre") {
    return {
      mode,
      label: option?.label ?? "Genre focus",
      colour: (book) => selectedGenre && bookGenres(book).includes(selectedGenre)
        ? FOCUSED_GENRE_COLOUR
        : MISSING_MAP_COLOUR,
      detail: (book) => selectedGenre && bookGenres(book).includes(selectedGenre)
        ? selectedGenre
        : "Not selected",
      legendItems: selectedGenre
        ? [
            { label: selectedGenre, colour: FOCUSED_GENRE_COLOUR },
            { label: "Other books", colour: MISSING_MAP_COLOUR },
          ]
        : [{ label: "Choose a genre", colour: MISSING_MAP_COLOUR }],
      continuous: false,
    };
  }

  if (["language", "fiction_category", "binding", "publication_type"].includes(mode)) {
    const values = Array.from(new Set(
      books.map((book) => categoricalMapValue(book, mode)).filter(
        (value): value is string => Boolean(value),
      ),
    )).sort((first, second) => first.localeCompare(second));
    const colours = new Map(values.map((value, index) => [
      value,
      CATEGORY_MAP_COLOURS[index % CATEGORY_MAP_COLOURS.length],
    ]));
    return {
      mode,
      label: option?.label ?? mode,
      colour: (book) => colours.get(categoricalMapValue(book, mode) ?? "")
        ?? MISSING_MAP_COLOUR,
      detail: (book) => {
        const value = categoricalMapValue(book, mode);
        return value ? metadataLabel(value) : "Not recorded";
      },
      legendItems: [
        ...values.map((value) => ({
          label: metadataLabel(value),
          colour: colours.get(value) ?? MISSING_MAP_COLOUR,
        })),
        { label: "Not recorded", colour: MISSING_MAP_COLOUR },
      ],
      continuous: false,
    };
  }

  const scoredBooks = books
    .filter((book) => specialMapCategory(book, mode) === null)
    .map((book) => ({ book, value: metricForBook(book, mode) }))
    .filter(
      (item): item is { book: MapBook; value: number } => item.value !== null,
    );
  const values = scoredBooks
    .map((item) => item.value)
    .sort((first, second) => first - second);
  const usePercentiles = values.length >= 3;
  const minimum = values.length > 0
    ? percentile(values, usePercentiles ? 0.01 : 0)
    : 0;
  const maximum = values.length > 0
    ? percentile(values, usePercentiles ? 0.99 : 1)
    : 0;
  const actualMinimum = values[0] ?? 0;
  const actualMaximum = values.at(-1) ?? 0;
  const isDuration = mode === "pending_duration" || mode === "reading_duration";
  const isReadingRate = mode === "reading_rate";
  const isPublicationYear = mode === "current_ed_year"
    || mode === "original_publication_year";
  const describe = (value: number) =>
    isDuration
      ? `${value} day${value === 1 ? "" : "s"}`
      : isReadingRate
        ? `${Math.round(value * 10) / 10} pages/day`
      : isPublicationYear
        ? String(value)
        : formatDate(dayAsDate(value));
  const endpointLabel = (isMinimum: boolean) => {
    if (scoredBooks.length === 0) return "No dated books";
    const value = isMinimum ? actualMinimum : actualMaximum;
    const winners = scoredBooks.filter((item) => item.value === value);
    const qualifier = isDuration
      ? isMinimum ? "Shortest" : "Longest"
      : isReadingRate
        ? isMinimum ? "Slowest" : "Fastest"
        : isMinimum ? "Oldest" : "Newest";
    if (winners.length !== 1) {
      return `${qualifier}: tie (${winners.length}) · ${describe(value)}`;
    }
    return `${qualifier}: “${winners[0].book.title}” · ${describe(value)}`;
  };
  const legendItems = Array.from(
    new Map(
      books
        .map((book) => specialMapCategory(book, mode))
        .filter((item): item is { label: string; colour: string } => item !== null)
        .map((item) => [item.label, item]),
    ).values(),
  );

  return {
    mode,
    label: option?.label ?? mode,
    colour: (book) => {
      const category = specialMapCategory(book, mode);
      if (category) return category.colour;
      const value = metricForBook(book, mode);
      if (value === null) return MISSING_MAP_COLOUR;
      const amount = maximum === minimum
        ? 0.65
        : Math.max(0, Math.min(1, (value - minimum) / (maximum - minimum)));
      return interpolateHex(LIGHT_MAP_COLOUR, DARK_MAP_COLOUR, amount);
    },
    detail: (book) => {
      const category = specialMapCategory(book, mode);
      if (category) return category.label;
      const value = metricForBook(book, mode);
      return value === null ? "No data" : describe(value);
    },
    lowLabel: endpointLabel(true),
    highLabel: endpointLabel(false),
    legendItems,
    continuous: true,
  };
}

function overlapArea(first: VisualRect, second: VisualRect) {
  const width = Math.max(
    0,
    Math.min(first.x + first.width, second.x + second.width) -
    Math.max(first.x, second.x),
  );
  const height = Math.max(
    0,
    Math.min(first.y + first.height, second.y + second.height) -
    Math.max(first.y, second.y),
  );
  return width * height;
}

function mapHierarchyBounds(
  bookcase: MapBookcase,
  shelf: MapShelf | null,
  container: MapContainer | null,
  bookcaseRect: VisualRect,
  shelfLayout: Map<number, number>,
  containerLayout: Map<number, VisualRect>,
): MapWorldBounds {
  if (!shelf) {
    return {
      minX: bookcaseRect.x,
      minY: bookcaseRect.y,
      maxX: bookcaseRect.x + bookcaseRect.width,
      maxY: bookcaseRect.y + bookcaseRect.height,
    };
  }

  const availableHeight = MAP_HEIGHT - 22;
  const totalWeight = bookcase.shelves.reduce(
    (total, item) => total + (shelfLayout.get(item.id) ?? 1),
    0,
  );
  let shelfY = 11;
  let shelfHeight = 0;
  for (const item of bookcase.shelves) {
    const height = availableHeight * (shelfLayout.get(item.id) ?? 1) /
      Math.max(totalWeight, 1);
    if (item.id === shelf.id) {
      shelfHeight = height;
      break;
    }
    shelfY += height;
  }
  const shelfRect: VisualRect = {
    x: bookcaseRect.x + bookcaseRect.width * MAP_INSET / MAP_WIDTH,
    y: bookcaseRect.y + bookcaseRect.height * shelfY / MAP_HEIGHT,
    width: bookcaseRect.width * (MAP_WIDTH - MAP_INSET * 2) / MAP_WIDTH,
    height: bookcaseRect.height * Math.max(1, shelfHeight - 5) / MAP_HEIGHT,
  };
  if (!container) {
    return {
      minX: shelfRect.x,
      minY: shelfRect.y,
      maxX: shelfRect.x + shelfRect.width,
      maxY: shelfRect.y + shelfRect.height,
    };
  }

  const index = shelf.containers.findIndex((item) => item.id === container.id);
  const fallbackWidth = 100 / Math.max(shelf.containers.length, 1);
  const placement = containerLayout.get(container.id) ?? {
    x: Math.max(0, index) * fallbackWidth,
    y: 0,
    width: fallbackWidth,
    height: 100,
  };
  const usableWidth = MAP_WIDTH - MAP_INSET * 2 - 16;
  const contentY = shelfY + 7;
  const contentHeight = Math.max(8, shelfHeight - 17);
  const containerRect: VisualRect = {
    x: bookcaseRect.x + bookcaseRect.width *
      (MAP_INSET + 8 + usableWidth * placement.x / 100) / MAP_WIDTH,
    y: bookcaseRect.y + bookcaseRect.height *
      (contentY + contentHeight * placement.y / 100) / MAP_HEIGHT,
    width: bookcaseRect.width * usableWidth * placement.width / 100 / MAP_WIDTH,
    height: bookcaseRect.height * contentHeight * placement.height / 100 / MAP_HEIGHT,
  };
  return {
    minX: containerRect.x,
    minY: containerRect.y,
    maxX: containerRect.x + containerRect.width,
    maxY: containerRect.y + containerRect.height,
  };
}

function MapContainerGraphic({
  container,
  x,
  y,
  width,
  height,
  onSelect,
  onOpen,
  obscured,
  inspectionSelected,
  inspectionMuted,
  inspectionSilhouette,
  focusedBookId,
  cataloguePageMean,
  colourScale,
  editing,
  rearranging,
  activeBookId,
  reservedBooks,
  onEdit,
  onRectPointerDown,
  onBookSelect,
  onBookOpen,
  onRearrangeBookSelect,
  onDestination,
  onBookPointerDown,
}: {
  container: MapContainer;
  x: number;
  y: number;
  width: number;
  height: number;
  onSelect: () => void;
  onOpen: () => void;
  obscured: boolean;
  inspectionSelected: boolean;
  inspectionMuted: boolean;
  inspectionSilhouette: boolean;
  focusedBookId: number | null;
  cataloguePageMean: number;
  colourScale: MapColourScale;
  editing: boolean;
  rearranging: boolean;
  activeBookId: number | null;
  reservedBooks: MapBook[];
  onEdit: () => void;
  onRectPointerDown: (
    event: React.PointerEvent<SVGGElement | SVGRectElement>,
    mode: "move" | "resize",
  ) => void;
  onBookSelect: (book: MapBook) => void;
  onBookOpen: (book: MapBook) => void;
  onRearrangeBookSelect: (book: MapBook) => void;
  onDestination: (containerId: number, position: number) => void;
  onBookPointerDown: (
    book: MapBook,
    event: React.PointerEvent<Element>,
  ) => void;
}) {
  const padding = 3;
  const bookAreaHeight = Math.max(6, height - padding * 2);
  const availableWidth = Math.max(20, width - padding * 2);
  const books = container.books;
  const occupiedBooks = [...books, ...reservedBooks].filter(
    (book, index, items) => items.findIndex((item) => item.id === book.id) === index,
  );
  const isRow = container.container_type === "ROW";
  const maxPosition = Math.max(
    0,
    ...occupiedBooks.map((book) => book.position ?? 1),
  );
  const targetPositions = rearranging
    ? Array.from({ length: maxPosition + 1 }, (_, index) => index + 1)
    : [];
  const slotCount = Math.max(1, rearranging ? maxPosition + 1 : maxPosition);
  const proportionalSegments = proportionalBookSegments(
    occupiedBooks,
    isRow ? availableWidth : bookAreaHeight,
    cataloguePageMean,
  );
  const visibleBookIds = new Set(books.map((book) => book.id));
  const reservedBookIds = new Set(reservedBooks.map((book) => book.id));
  const visibleSegments = proportionalSegments.filter(
    ({ book }) => visibleBookIds.has(book.id),
  );
  const reservedSegments = proportionalSegments.filter(
    ({ book }) => reservedBookIds.has(book.id),
  );
  const activate = (event: React.KeyboardEvent<SVGGElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (editing) onEdit();
      else if (!rearranging) onSelect();
    }
  };

  return (
    <g
      className={`map-container ${editing ? "editing" : ""} ${rearranging ? "rearranging" : ""} ${obscured ? "obscured" : ""} ${inspectionSelected ? "inspection-selected" : ""} ${inspectionMuted ? "inspection-muted" : ""} ${inspectionSilhouette ? "inspection-silhouette" : ""} ${
        container.layer === "FOREGROUND" ? "foreground" : ""
      }`}
      role="button"
      tabIndex={0}
      onClick={(event) => {
        event.stopPropagation();
        if (editing) onEdit();
        else if (!rearranging) onSelect();
      }}
      onPointerDown={(event) => {
        if (editing) onRectPointerDown(event, "move");
      }}
      onDoubleClick={(event) => {
        if (editing || rearranging) return;
        event.stopPropagation();
        onOpen();
      }}
      onKeyDown={activate}
    >
      <title>
        {container.layer === "BACKGROUND" ? "Background" : "Foreground"}{" "}
        {container.container_type === "ROW" ? "Row" : "Pile"}{" "}
        {container.container_number} · {container.book_count} books
      </title>
      <rect x={x} y={y} width={width} height={height} rx="2" />
      {targetPositions.map((position) => {
        const slotWidth = availableWidth / slotCount;
        const slotHeight = bookAreaHeight / slotCount;
        return (
          <rect
            key={`target-${position}`}
            className="map-rearrange-target"
            data-container-id={container.id}
            data-position={position}
            x={isRow
              ? x + padding + (position - 1) * slotWidth
              : x + padding}
            y={isRow
              ? y + padding
              : y + padding + (position - 1) * slotHeight}
            width={isRow ? Math.max(1, slotWidth - 0.5) : availableWidth}
            height={isRow ? bookAreaHeight : Math.max(1, slotHeight - 0.5)}
            onClick={(event) => {
              event.stopPropagation();
              onDestination(container.id, position);
            }}
          >
            <title>Move to position {position}</title>
          </rect>
        );
      })}
      {books.length > 0 && isRow ? (
        visibleSegments.map(({ book, offset, thickness }) => {
          const hitWidth = Math.max(thickness, 2);
          return (
            <g
              key={book.id}
              className="map-book-target"
              role={editing ? undefined : "button"}
              tabIndex={editing ? -1 : 0}
              aria-label={editing ? undefined : `Show ${book.title} in the catalogue`}
              data-container-id={container.id}
              data-position={book.position ?? 1}
              onPointerDown={(event) => {
                if (rearranging) onBookPointerDown(book, event);
              }}
              onClick={(event) => {
                if (editing) return;
                event.stopPropagation();
                if (rearranging) onRearrangeBookSelect(book);
                else onBookSelect(book);
              }}
              onDoubleClick={(event) => {
                if (editing || rearranging) return;
                event.stopPropagation();
                onBookOpen(book);
              }}
              onKeyDown={(event) => {
                if (
                  !editing &&
                  (event.key === "Enter" || event.key === " ")
                ) {
                  event.preventDefault();
                  event.stopPropagation();
                  if (rearranging) onRearrangeBookSelect(book);
                  else onBookSelect(book);
                }
              }}
            >
              <rect
                className={`map-book ${rearranging && book.id === activeBookId ? "active-move" : ""} ${
                  focusedBookId === null
                    ? ""
                    : book.id === focusedBookId
                      ? "focused"
                      : "muted"
                }`}
                x={x + padding + offset}
                y={y + padding}
                width={thickness}
                height={bookAreaHeight}
                fill={focusedBookId === book.id ? "#287fbd" : colourScale.colour(book)}
              />
              <rect
                className="map-book-hit-area"
                x={x + padding + offset - (hitWidth - thickness) / 2}
                y={y + padding}
                width={hitWidth}
                height={bookAreaHeight}
              />
              <title>
                {book.title}
                {colourScale.detail(book) ? ` · ${colourScale.detail(book)}` : ""}
              </title>
            </g>
          );
        })
      ) : books.length > 0 ? (
        visibleSegments.map(({ book, offset, thickness }) => {
          const hitHeight = Math.max(thickness, 2);
          return (
            <g
              key={book.id}
              className="map-book-target"
              role={editing ? undefined : "button"}
              tabIndex={editing ? -1 : 0}
              aria-label={editing ? undefined : `Show ${book.title} in the catalogue`}
              data-container-id={container.id}
              data-position={book.position ?? 1}
              onPointerDown={(event) => {
                if (rearranging) onBookPointerDown(book, event);
              }}
              onClick={(event) => {
                if (editing) return;
                event.stopPropagation();
                if (rearranging) onRearrangeBookSelect(book);
                else onBookSelect(book);
              }}
              onDoubleClick={(event) => {
                if (editing || rearranging) return;
                event.stopPropagation();
                onBookOpen(book);
              }}
              onKeyDown={(event) => {
                if (
                  !editing &&
                  (event.key === "Enter" || event.key === " ")
                ) {
                  event.preventDefault();
                  event.stopPropagation();
                  if (rearranging) onRearrangeBookSelect(book);
                  else onBookSelect(book);
                }
              }}
            >
              <rect
                className={`map-book ${rearranging && book.id === activeBookId ? "active-move" : ""} ${
                  focusedBookId === null
                    ? ""
                    : book.id === focusedBookId
                      ? "focused"
                      : "muted"
                }`}
                x={x + padding}
                y={y + padding + offset}
                width={availableWidth}
                height={thickness}
                fill={focusedBookId === book.id ? "#287fbd" : colourScale.colour(book)}
              />
              <rect
                className="map-book-hit-area"
                x={x + padding}
                y={y + padding + offset - (hitHeight - thickness) / 2}
                width={availableWidth}
                height={hitHeight}
              />
              <title>
                {book.title}
                {colourScale.detail(book) ? ` · ${colourScale.detail(book)}` : ""}
              </title>
            </g>
          );
        })
      ) : null}
      {reservedSegments.map(({ book, offset, thickness }) => {
        return (
          <rect
            key={`reserved-${book.id}`}
            className={`map-book reserved ${rearranging ? "interactive" : ""} ${book.id === activeBookId ? "active-move" : ""}`}
            data-container-id={container.id}
            data-position={book.position ?? 1}
            x={isRow
              ? x + padding + offset
              : x + padding}
            y={isRow
              ? y + padding
              : y + padding + offset}
            width={isRow ? thickness : availableWidth}
            height={isRow ? bookAreaHeight : thickness}
            onClick={(event) => {
              if (!rearranging) return;
              event.stopPropagation();
              if (book.id === activeBookId) {
                onDestination(container.id, book.position ?? 1);
              } else {
                onRearrangeBookSelect(book);
              }
            }}
          >
            <title>
              {book.title} · retained position while {book.is_on_loan
                ? "On loan"
                : "Reading"}
            </title>
          </rect>
        );
      })}
      {editing && (
        <rect
          className="map-svg-resize-handle"
          x={x + Math.max(0, width - 14)}
          y={y + Math.max(0, height - 14)}
          width={14}
          height={14}
          rx={2}
          onPointerDown={(event) => onRectPointerDown(event, "resize")}
        />
      )}
    </g>
  );
}

function MapShelfGraphic({
  shelf,
  y,
  height,
  onShelf,
  onContainer,
  onContainerOpen,
  containerLayout,
  inspectedContainerId,
  focusedBookId,
  cataloguePageMean,
  colourScale,
  editing,
  rearranging,
  activeBookId,
  reservedBooksByContainer,
  onEditShelf,
  onEditContainer,
  onContainerLayoutChange,
  onBookSelect,
  onBookOpen,
  onRearrangeBookSelect,
  onDestination,
  onBookPointerDown,
}: {
  shelf: MapShelf;
  y: number;
  height: number;
  onShelf: () => void;
  onContainer: (container: MapContainer) => void;
  onContainerOpen: (container: MapContainer) => void;
  containerLayout: Map<number, VisualRect>;
  inspectedContainerId: number | null;
  focusedBookId: number | null;
  cataloguePageMean: number;
  colourScale: MapColourScale;
  editing: boolean;
  rearranging: boolean;
  activeBookId: number | null;
  reservedBooksByContainer: Map<number, MapBook[]>;
  onEditShelf: () => void;
  onEditContainer: (container: MapContainer) => void;
  onContainerLayoutChange: (containerId: number, rect: VisualRect) => void;
  onBookSelect: (book: MapBook) => void;
  onBookOpen: (book: MapBook) => void;
  onRearrangeBookSelect: (book: MapBook) => void;
  onDestination: (containerId: number, position: number) => void;
  onBookPointerDown: (
    book: MapBook,
    event: React.PointerEvent<Element>,
  ) => void;
}) {
  const contentY = y + 7;
  const contentHeight = Math.max(8, height - 17);
  const hasForeground = shelf.containers.some(
    (container) => container.layer === "FOREGROUND",
  );
  const placementFor = (container: MapContainer, index: number): VisualRect => {
    const fallbackWidth = 100 / Math.max(shelf.containers.length, 1);
    return containerLayout.get(container.id) ?? {
      x: index * fallbackWidth,
      y: 0,
      width: fallbackWidth,
      height: 100,
    };
  };
  const inspectedIndex = shelf.containers.findIndex(
    (container) => container.id === inspectedContainerId,
  );
  const inspectedContainer = inspectedIndex >= 0
    ? shelf.containers[inspectedIndex]
    : null;
  const inspectedPlacement = inspectedContainer
    ? placementFor(inspectedContainer, inspectedIndex)
    : null;

  return (
    <g
      className="map-shelf"
      role="button"
      tabIndex={0}
      onClick={(event) => {
        event.stopPropagation();
        if (editing) onEditShelf();
        else if (!rearranging) onShelf();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.stopPropagation();
          if (editing) onEditShelf();
          else if (!rearranging) onShelf();
        }
      }}
    >
      <title>Shelf {shelf.shelf_number} · {shelf.book_count} books</title>
      <rect
        x={MAP_INSET}
        y={y}
        width={MAP_WIDTH - MAP_INSET * 2}
        height={height - 5}
        rx="5"
        className="map-shelf-frame"
      />
      {shelf.containers.map((container, index) => {
        const usableWidth = MAP_WIDTH - MAP_INSET * 2 - 16;
        const placement = placementFor(container, index);
        const inspectionSilhouette = Boolean(
          inspectedContainer?.layer === "BACKGROUND" &&
          container.layer === "FOREGROUND" &&
          inspectedPlacement &&
          overlapArea(placement, inspectedPlacement) > 0.0001,
        );
        return (
          <MapContainerGraphic
            key={container.id}
            container={container}
            x={MAP_INSET + 8 + usableWidth * placement.x / 100}
            y={contentY + contentHeight * placement.y / 100}
            width={usableWidth * placement.width / 100}
            height={contentHeight * placement.height / 100}
            obscured={hasForeground && container.layer === "BACKGROUND"}
            inspectionSelected={container.id === inspectedContainerId}
            inspectionMuted={
              inspectedContainerId !== null &&
              container.id !== inspectedContainerId &&
              !inspectionSilhouette
            }
            inspectionSilhouette={inspectionSilhouette}
            focusedBookId={focusedBookId}
            cataloguePageMean={cataloguePageMean}
            colourScale={colourScale}
            editing={editing}
            rearranging={rearranging}
            activeBookId={activeBookId}
            reservedBooks={reservedBooksByContainer.get(container.id) ?? []}
            onEdit={() => onEditContainer(container)}
            onBookSelect={onBookSelect}
            onBookOpen={onBookOpen}
            onRearrangeBookSelect={onRearrangeBookSelect}
            onDestination={onDestination}
            onBookPointerDown={onBookPointerDown}
            onRectPointerDown={(event, mode) => {
              event.preventDefault();
              event.stopPropagation();
              onEditContainer(container);
              const svg = event.currentTarget.ownerSVGElement;
              if (!svg) return;
              const bounds = svg.getBoundingClientRect();
              const startX = event.clientX;
              const startY = event.clientY;
              const start = placement;
              const move = (moveEvent: PointerEvent) => {
                const deltaX =
                  (moveEvent.clientX - startX) * MAP_WIDTH /
                  Math.max(bounds.width, 1) / usableWidth * 100;
                const deltaY =
                  (moveEvent.clientY - startY) * MAP_HEIGHT /
                  Math.max(bounds.height, 1) / contentHeight * 100;
                const next = mode === "move"
                  ? {
                      ...start,
                      x: Math.max(0, Math.min(100 - start.width, start.x + deltaX)),
                      y: Math.max(0, Math.min(100 - start.height, start.y + deltaY)),
                    }
                  : {
                      ...start,
                      width: Math.max(4, Math.min(100 - start.x, start.width + deltaX)),
                      height: Math.max(4, Math.min(100 - start.y, start.height + deltaY)),
                    };
                onContainerLayoutChange(container.id, next);
              };
              const stop = () => {
                window.removeEventListener("pointermove", move);
                window.removeEventListener("pointerup", stop);
              };
              window.addEventListener("pointermove", move);
              window.addEventListener("pointerup", stop, { once: true });
            }}
            onSelect={() => onContainer(container)}
            onOpen={() => onContainerOpen(container)}
          />
        );
      })}
      <line
        x1={MAP_INSET}
        y1={y + height - 5}
        x2={MAP_WIDTH - MAP_INSET}
        y2={y + height - 5}
        className="map-shelf-board"
      />
    </g>
  );
}

function MapBookcaseGraphic({
  bookcase,
  onBookcase,
  onShelf,
  onContainer,
  onContainerOpen,
  rect,
  shelfLayout,
  containerLayout,
  inspectedContainerId,
  focusedBookId,
  cataloguePageMean,
  colourScale,
  editing,
  rearranging,
  activeBookId,
  reservedBooksByContainer,
  onEditBookcase,
  onEditShelf,
  onEditContainer,
  onContainerLayoutChange,
  onShelfWeightsChange,
  onRectPointerDown,
  onBookSelect,
  onBookOpen,
  onRearrangeBookSelect,
  onDestination,
  onBookPointerDown,
}: {
  bookcase: MapBookcase;
  onBookcase: () => void;
  onShelf: (shelf: MapShelf) => void;
  onContainer: (shelf: MapShelf, container: MapContainer) => void;
  onContainerOpen: (shelf: MapShelf, container: MapContainer) => void;
  rect: VisualRect;
  shelfLayout: Map<number, number>;
  containerLayout: Map<number, VisualRect>;
  inspectedContainerId: number | null;
  focusedBookId: number | null;
  cataloguePageMean: number;
  colourScale: MapColourScale;
  editing: boolean;
  rearranging: boolean;
  activeBookId: number | null;
  reservedBooksByContainer: Map<number, MapBook[]>;
  onEditBookcase: () => void;
  onEditShelf: (shelf: MapShelf) => void;
  onEditContainer: (container: MapContainer) => void;
  onContainerLayoutChange: (containerId: number, rect: VisualRect) => void;
  onShelfWeightsChange: (
    firstShelfId: number,
    firstWeight: number,
    secondShelfId: number,
    secondWeight: number,
  ) => void;
  onRectPointerDown: (
    event: React.PointerEvent<HTMLElement>,
    mode: "move" | "resize",
  ) => void;
  onBookSelect: (book: MapBook) => void;
  onBookOpen: (book: MapBook) => void;
  onRearrangeBookSelect: (book: MapBook) => void;
  onDestination: (containerId: number, position: number) => void;
  onBookPointerDown: (
    book: MapBook,
    event: React.PointerEvent<Element>,
  ) => void;
}) {
  const height = MAP_HEIGHT;
  const availableHeight = height - 22;
  const totalWeight = bookcase.shelves.reduce(
    (total, shelf) => total + (shelfLayout.get(shelf.id) ?? 1),
    0,
  );
  const shelfHeights = bookcase.shelves.map(
    (shelf) =>
      availableHeight * (shelfLayout.get(shelf.id) ?? 1) /
      Math.max(totalWeight, 1),
  );
  let shelfY = 11;

  return (
    <article
      className="map-bookcase-card"
      role="button"
      tabIndex={0}
      onClick={editing ? onEditBookcase : rearranging ? undefined : onBookcase}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          if (editing) onEditBookcase();
          else if (!rearranging) onBookcase();
        }
      }}
      style={{
        left: `${rect.x}%`,
        top: `${rect.y}%`,
        width: `${rect.width}%`,
        height: `${rect.height}%`,
      }}
    >
      <svg
        viewBox={`0 0 ${MAP_WIDTH} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Visual index for ${bookcase.name}`}
      >
        <rect
          x="5"
          y="4"
          width={MAP_WIDTH - 10}
          height={height - 9}
          rx="9"
          className="map-furniture-frame"
        />
        {bookcase.shelves.map((shelf, index) => {
          const currentY = shelfY;
          const currentHeight = shelfHeights[index];
          shelfY += currentHeight;
          const nextShelf = bookcase.shelves[index + 1];
          return (
            <g key={shelf.id}>
              <MapShelfGraphic
                shelf={shelf}
                y={currentY}
                height={currentHeight}
                onShelf={() => onShelf(shelf)}
                onContainer={(container) => onContainer(shelf, container)}
                onContainerOpen={(container) => onContainerOpen(shelf, container)}
                containerLayout={containerLayout}
                inspectedContainerId={inspectedContainerId}
                focusedBookId={focusedBookId}
                cataloguePageMean={cataloguePageMean}
                colourScale={colourScale}
                editing={editing}
                rearranging={rearranging}
                activeBookId={activeBookId}
                reservedBooksByContainer={reservedBooksByContainer}
                onEditShelf={() => onEditShelf(shelf)}
                onEditContainer={onEditContainer}
                onContainerLayoutChange={onContainerLayoutChange}
                onBookSelect={onBookSelect}
                onBookOpen={onBookOpen}
                onRearrangeBookSelect={onRearrangeBookSelect}
                onDestination={onDestination}
                onBookPointerDown={onBookPointerDown}
              />
              {editing && nextShelf && (
                <line
                  className="map-shelf-resize-handle"
                  x1={MAP_INSET}
                  x2={MAP_WIDTH - MAP_INSET}
                  y1={shelfY - 5}
                  y2={shelfY - 5}
                  onPointerDown={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onEditShelf(shelf);
                    const svg = event.currentTarget.ownerSVGElement;
                    if (!svg) return;
                    const bounds = svg.getBoundingClientRect();
                    const startY = event.clientY;
                    const firstStart = shelfLayout.get(shelf.id) ?? 1;
                    const secondStart = shelfLayout.get(nextShelf.id) ?? 1;
                    const move = (moveEvent: PointerEvent) => {
                      const logicalDelta =
                        (moveEvent.clientY - startY) * MAP_HEIGHT /
                        Math.max(bounds.height, 1);
                      const weightDelta =
                        logicalDelta / availableHeight * Math.max(totalWeight, 1);
                      const boundedDelta = Math.max(
                        0.25 - firstStart,
                        Math.min(secondStart - 0.25, weightDelta),
                      );
                      onShelfWeightsChange(
                        shelf.id,
                        firstStart + boundedDelta,
                        nextShelf.id,
                        secondStart - boundedDelta,
                      );
                    };
                    const stop = () => {
                      window.removeEventListener("pointermove", move);
                      window.removeEventListener("pointerup", stop);
                    };
                    window.addEventListener("pointermove", move);
                    window.addEventListener("pointerup", stop, { once: true });
                  }}
                />
              )}
            </g>
          );
        })}
      </svg>
      {editing && (
        <>
          <button
            type="button"
            className="map-direct-handle move"
            title="Drag furniture"
            aria-label="Drag furniture"
            onPointerDown={(event) => onRectPointerDown(event, "move")}
          >
            ↕
          </button>
          <button
            type="button"
            className="map-direct-handle resize"
            title="Resize furniture"
            aria-label="Resize furniture"
            onPointerDown={(event) => onRectPointerDown(event, "resize")}
          >
            ↘
          </button>
        </>
      )}
    </article>
  );
}

function RangeField({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="map-range">
      <span>{label}<strong>{Math.round(value * 10) / 10}</strong></span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function MapNumberField({
  label,
  value,
  positive = false,
  onChange,
}: {
  label: string;
  value: number;
  positive?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <label className="map-number-field">
      <span>{label}</span>
      <input
        type="number"
        step="0.5"
        min={positive ? 0.5 : undefined}
        value={value}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next) && (!positive || next > 0)) onChange(next);
        }}
      />
    </label>
  );
}

function MapInspectorBookRow({
  book,
  selected,
  onSelect,
}: {
  book: MapBook;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`map-inspector-book ${selected ? "selected" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      {book.cover_filename ? (
        <img
          src={api.coverUrl(book.cover_filename)}
          alt=""
          loading="lazy"
        />
      ) : (
        <span className="map-inspector-cover-placeholder" aria-hidden="true">
          <BookOpen size={20} />
        </span>
      )}
      <span>
        <strong>{book.title}</strong>
        <small>{displayedAuthor(book)}</small>
      </span>
    </button>
  );
}

function MapCompleteBookInformation({ book }: { book: Book }) {
  const acquisition = book.acquisition_date
    ? formatDate(book.acquisition_date)
    : book.is_original_collection
      ? "Original collection · exact date unknown"
      : "Not recorded";
  const finishedReading = book.read_date
    ? formatDate(book.read_date)
    : book.status === "READ" && book.is_read_date_unknown
      ? "Read · exact date unknown"
      : "Not recorded";
  const location = book.container_id
    ? `${book.bookcase_name} · Shelf ${book.shelf_number} · ${
      book.layer === "BACKGROUND" ? "Background" : "Foreground"
    } ${book.container_type === "ROW" ? "Row" : "Pile"} ${
      book.container_number
    } · Position ${book.position}`
    : "No physical location assigned";

  return (
    <div className="map-complete-book-information">
      <div className="book-details-summary">
        {book.cover_filename ? (
          <img src={api.coverUrl(book.cover_filename)} alt={`Cover of ${book.title}`} />
        ) : (
          <div className="book-details-cover-placeholder"><BookOpen size={34} /></div>
        )}
        <div>
          <span className={`status ${book.status.toLowerCase()}`}>
            {bookStatusLabel(book)}
          </span>
          <h3>{book.title}</h3>
          <p>{displayedAuthor(book)}</p>
        </div>
      </div>

      {book.has_multiple_authors && (
        <section className="book-details-section">
          <h3>Authors</h3>
          <ol className="structured-author-list">
            {book.structured_authors.map((author) => <li key={author}>{author}</li>)}
          </ol>
        </section>
      )}

      <section className="book-details-section">
        <h3>Bibliographic identifiers</h3>
        <dl className="book-details-grid">
          <div><dt>ISBN-10</dt><dd>{book.isbn_10 ?? "Not recorded"}</dd></div>
          <div><dt>ISBN-13</dt><dd>{book.isbn_13 ?? "Not recorded"}</dd></div>
          <div className="wide"><dt>Goodreads review</dt><dd>
            {book.goodreads_url ? (
              <a href={book.goodreads_url} target="_blank" rel="noreferrer">
                Open Goodreads <ExternalLink size={14} />
              </a>
            ) : "Not recorded"}
          </dd></div>
        </dl>
      </section>

      <section className="book-details-section">
        <h3>Edition and classification</h3>
        <dl className="book-details-grid three-columns">
          <div className="wide"><dt>Subtitle</dt><dd>{book.subtitle ?? "Not recorded"}</dd></div>
          <div><dt>Pages</dt><dd>{book.page_count ?? "Not recorded"}</dd></div>
          <div><dt>Publisher</dt><dd>{book.publisher ?? "Not recorded"}</dd></div>
          <div><dt>Current edition year</dt><dd>{book.current_ed_year ?? "Not recorded"}</dd></div>
          <div><dt>Original publication year</dt><dd>{book.original_publication_year ?? "Not recorded"}</dd></div>
          <div><dt>Language</dt><dd>{book.language ?? "Not recorded"}</dd></div>
          <div><dt>Edition number</dt><dd>{book.edition_number ?? "Not recorded"}</dd></div>
          <div><dt>Category</dt><dd>{book.fiction_category ? metadataLabel(book.fiction_category) : "Not recorded"}</dd></div>
          <div><dt>Binding</dt><dd>{book.binding ? metadataLabel(book.binding) : "Not recorded"}</dd></div>
          <div><dt>Publication type</dt><dd>{book.publication_type ? metadataLabel(book.publication_type) : "Not recorded"}</dd></div>
          <div><dt>Series</dt><dd>{book.series_name ?? "Not recorded"}</dd></div>
          <div><dt>Series volume</dt><dd>{book.series_volume ?? "Not recorded"}</dd></div>
          <div className="wide"><dt>Genre</dt><dd>{book.genre_text ?? "Not recorded"}</dd></div>
        </dl>
      </section>

      <section className="book-details-section">
        <h3>Reading and acquisition history</h3>
        <dl className="book-details-grid three-columns">
          <div><dt>Acquired</dt><dd>{acquisition}</dd></div>
          <div><dt>Reading started</dt><dd>{book.reading_started_date ? formatDate(book.reading_started_date) : "Not recorded"}</dd></div>
          <div><dt>Finished reading</dt><dd>{finishedReading}</dd></div>
        </dl>
        <ReadingHistorySummary book={book} />
      </section>

      <section className="book-details-section">
        <h3>Physical catalogue</h3>
        <dl className="book-details-grid">
          <div className="wide"><dt>{book.status === "CURRENTLY_READING" ? "Saved return location" : "Location"}</dt><dd>{location}</dd></div>
          <div><dt>BOOKPILE record</dt><dd>#{book.id}</dd></div>
          <div><dt>Stored cover</dt><dd>{book.cover_filename ? "Yes" : "No"}</dd></div>
        </dl>
      </section>

      <section className="book-details-section">
        <h3>Loan history</h3>
        {book.active_loan && (
          <p className="book-details-note">
            Currently on loan to <strong>{book.active_loan.loaned_to}</strong>.
            {book.active_loan.loaned_date
              ? ` Loaned ${formatDate(book.active_loan.loaned_date)}.`
              : " Unknown loan date."}
            {book.active_loan.expected_return_date
              ? ` Expected back ${formatDate(book.active_loan.expected_return_date)}.`
              : " No expected return date."}
          </p>
        )}
        <LoanHistorySummary book={book} />
      </section>

      <section className="book-details-section">
        <h3>Notes and record history</h3>
        <dl className="book-details-grid">
          <div className="wide book-details-notes"><dt>Notes</dt><dd>{book.notes || "No notes"}</dd></div>
          <div><dt>Added to BOOKPILE</dt><dd>{formatTimestamp(book.created_at)}</dd></div>
          <div><dt>Last updated</dt><dd>{formatTimestamp(book.updated_at)}</dd></div>
        </dl>
      </section>
    </div>
  );
}

const emptyVisualLayout: VisualLayout = {
  bookcases: [],
  shelves: [],
  containers: [],
  outside: { x: 54, y: 70, width: 28, height: 18 },
  loaned: { x: 84, y: 70, width: 14, height: 18 },
};
const MAP_LAYOUT_EDITOR_ENABLED = true;
const MAP_REARRANGEMENT_ENABLED = true;

function LibraryMapDialog({
  onClose,
  onFilter,
  onReadingFilter,
  onLoanFilter,
  onBookFilter,
  onChanged,
  focusedBook,
}: {
  onClose: () => void;
  onFilter: (
    bookcaseId: number,
    shelfId?: number | "",
    containerId?: number | "",
  ) => void;
  onReadingFilter: () => void;
  onLoanFilter: () => void;
  onBookFilter: (book: { id: number; title: string }) => void;
  onChanged: () => Promise<void>;
  focusedBook: Book | null;
}) {
  const [map, setMap] = useState<LibraryMapData>({
    bookcases: [],
    outside_books: [],
    loaned_books: [],
    effective_page_mean: 200,
    layout: emptyVisualLayout,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingLayout, setEditingLayout] = useState(false);
  const [draft, setDraft] = useState<VisualLayout>(emptyVisualLayout);
  const [selectedBookcase, setSelectedBookcase] = useState("");
  const [selectedShelf, setSelectedShelf] = useState("");
  const [selectedContainer, setSelectedContainer] = useState("");
  const [saving, setSaving] = useState(false);
  const [colourMode, setColourMode] = useState<MapColourMode>("status");
  const [selectedMapGenre, setSelectedMapGenre] = useState("");
  const [legendExpanded, setLegendExpanded] = useState(false);
  const [mapToolsOpen, setMapToolsOpen] = useState(false);
  const [showRetainedShelfSpaces, setShowRetainedShelfSpaces] = useState(
    initialRetainedSpacesPreference,
  );
  const [cameraControlsExpanded, setCameraControlsExpanded] = useState(false);
  const [focusMenuOpen, setFocusMenuOpen] = useState(false);
  const [inspectionMenuOpen, setInspectionMenuOpen] = useState(false);
  const [inspectionMode, setInspectionMode] = useState<MapInspectionMode>(
    focusedBook ? "book" : null,
  );
  const [inspectedBookId, setInspectedBookId] = useState<number | null>(
    focusedBook?.id ?? null,
  );
  const [inspectedContainerId, setInspectedContainerId] = useState<number | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspectorCompleteBook, setInspectorCompleteBook] = useState<Book | null>(null);
  const [inspectorDetailsLoading, setInspectorDetailsLoading] = useState(false);
  const [inspectorDetailsError, setInspectorDetailsError] = useState("");
  const [focusBookcase, setFocusBookcase] = useState("");
  const [focusShelf, setFocusShelf] = useState("");
  const [focusContainer, setFocusContainer] = useState("");
  const [layoutPanelMinimized, setLayoutPanelMinimized] = useState(false);
  const [rearrangementPanelMinimized, setRearrangementPanelMinimized] = useState(false);
  const [rearranging, setRearranging] = useState(false);
  const [selectedMoveBookId, setSelectedMoveBookId] = useState<number | null>(null);
  const [oldPositionMode, setOldPositionMode] =
    useState<OldPositionMode>("COLLAPSE");
  const [newPositionMode, setNewPositionMode] =
    useState<NewPositionMode>("SQUEEZE");
  const [releaseShelfSpace, setReleaseShelfSpace] = useState(false);
  const [rearrangementSteps, setRearrangementSteps] =
    useState<RearrangementStep[]>([]);
  const [completedRearrangements, setCompletedRearrangements] =
    useState<RearrangementOperation[]>([]);
  const [completedPreviewStack, setCompletedPreviewStack] =
    useState<RearrangementResult[]>([]);
  const [rearrangementPreview, setRearrangementPreview] =
    useState<RearrangementResult | null>(null);
  const [previewingMove, setPreviewingMove] = useState(false);
  const [applyingMove, setApplyingMove] = useState(false);
  const [preciseContainer, setPreciseContainer] = useState("");
  const [precisePosition, setPrecisePosition] = useState(1);
  const [readingExitStatus, setReadingExitStatus] =
    useState<"" | "PENDING" | "READ">("");
  const [pendingReadingDestination, setPendingReadingDestination] = useState<{
    containerId: number;
    position: number;
  } | null>(null);
  const [dragGhost, setDragGhost] = useState<{
    title: string;
    x: number;
    y: number;
  } | null>(null);
  const [camera, setCamera] = useState<MapCamera>(LEGACY_MAP_CAMERA);
  const [viewportSize, setViewportSize] = useState<MapViewportSize>({
    width: 0,
    height: 0,
  });
  const roomRef = useRef<HTMLDivElement>(null);
  const worldRef = useRef<HTMLDivElement>(null);
  const ignoreNextBookClick = useRef(false);
  const cameraInitialized = useRef(false);
  const cameraHoldDelay = useRef<number | null>(null);
  const cameraHoldInterval = useRef<number | null>(null);
  const cameraPointers = useRef(new Map<number, { x: number; y: number }>());
  const cameraGesture = useRef<{
    moved: boolean;
    totalDistance: number;
    pinchDistance: number | null;
    pinchMidpoint: { x: number; y: number } | null;
    pinchCamera: MapCamera | null;
    pinchAnchor: Pick<MapCamera, "centerX" | "centerY"> | null;
  }>({
    moved: false,
    totalDistance: 0,
    pinchDistance: null,
    pinchMidpoint: null,
    pinchCamera: null,
    pinchAnchor: null,
  });
  const suppressNextMapClick = useRef(false);

  const loadMap = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.libraryMap();
      setMap(result);
      setDraft(structuredClone(result.layout));
      setSelectedBookcase(String(result.bookcases[0]?.id ?? ""));
      setSelectedShelf(String(result.bookcases[0]?.shelves[0]?.id ?? ""));
      setSelectedContainer(
        String(result.bookcases[0]?.shelves[0]?.containers[0]?.id ?? ""),
      );
      setFocusBookcase(String(result.bookcases[0]?.id ?? ""));
      setFocusShelf("");
      setFocusContainer("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load map");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMap();
  }, [loadMap]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        MAP_RETAINED_SPACES_STORAGE_KEY,
        String(showRetainedShelfSpaces),
      );
    } catch {
      // Presentation preferences may be unavailable in private browsing.
    }
  }, [showRetainedShelfSpaces]);

  const previewContainerLayouts = new Map(
    (rearrangementPreview?.container_layouts ?? []).map((item) => [item.id, item]),
  );
  const projectedVisualLayout = rearranging && previewContainerLayouts.size > 0
    ? {
        ...map.layout,
        containers: map.layout.containers.map(
          (item) => previewContainerLayouts.get(item.id) ?? item,
        ),
      }
    : map.layout;
  const fullGeometryLayout = editingLayout ? draft : projectedVisualLayout;
  const activeLayout = useMemo(() => {
    if (editingLayout || rearranging || showRetainedShelfSpaces) {
      return fullGeometryLayout;
    }
    const absentByContainer = new Map<number, MapBook[]>();
    const absentBooks = new Map<number, MapBook>();
    for (const book of [...map.outside_books, ...map.loaned_books]) {
      absentBooks.set(book.id, book);
    }
    for (const book of absentBooks.values()) {
      if (book.container_id === null || book.position === null) continue;
      absentByContainer.set(book.container_id, [
        ...(absentByContainer.get(book.container_id) ?? []),
        book,
      ]);
    }
    const containers = new Map(
      map.bookcases.flatMap((bookcase) =>
        bookcase.shelves.flatMap((shelf) =>
          shelf.containers.map((container) => [container.id, container] as const),
        ),
      ),
    );
    return {
      ...fullGeometryLayout,
      containers: fullGeometryLayout.containers.map((item) => {
        const container = containers.get(item.id);
        const absent = absentByContainer.get(item.id) ?? [];
        if (!container || absent.length === 0) return item;
        const rect = containerRectWithoutAbsentBooks(
          item,
          container.container_type,
          item.row_anchor,
          container.books,
          absent,
          map.effective_page_mean,
        );
        return { ...item, ...rect };
      }),
    };
  }, [
    editingLayout,
    fullGeometryLayout,
    map.bookcases,
    map.effective_page_mean,
    map.loaned_books,
    map.outside_books,
    rearranging,
    showRetainedShelfSpaces,
  ]);
  const layoutDirty = editingLayout && JSON.stringify(draft) !== JSON.stringify(map.layout);
  const confirmDiscardLayout = useCallback((): boolean => (
    !layoutDirty || window.confirm("Discard the unsaved library layout changes?")
  ), [layoutDirty]);
  const cancelLayoutEditing = useCallback(() => {
    if (!confirmDiscardLayout()) return;
    setDraft(structuredClone(map.layout));
    setEditingLayout(false);
    setError("");
  }, [confirmDiscardLayout, map.layout]);
  const requestMapClose = useCallback(() => {
    if (!confirmDiscardLayout()) return;
    onClose();
  }, [confirmDiscardLayout, onClose]);
  const bookcaseRects = new Map(
    activeLayout.bookcases.map((item) => [item.id, item]),
  );
  const shelfWeights = new Map(
    activeLayout.shelves.map((item) => [item.id, item.height_weight]),
  );
  const containerRects = new Map(
    activeLayout.containers.map((item) => [
      item.id,
      { x: item.x, y: item.y, width: item.width, height: item.height },
    ]),
  );
  const focusedBookcaseItem = map.bookcases.find(
    (bookcase) => bookcase.id === Number(focusBookcase),
  );
  const focusedShelfItems = focusedBookcaseItem?.shelves ?? [];
  const focusedShelfItem = focusedShelfItems.find(
    (shelf) => shelf.id === Number(focusShelf),
  );
  const focusedContainerItems = focusedShelfItem?.containers ?? [];
  const selectedBookcaseItem = draft.bookcases.find(
    (item) => item.id === Number(selectedBookcase),
  );
  const selectedShelfItem = draft.shelves.find(
    (item) => item.id === Number(selectedShelf),
  );
  const selectedContainerItem = draft.containers.find(
    (item) => item.id === Number(selectedContainer),
  );
  const containerContexts = useMemo(
    () =>
      new Map(
        map.bookcases.flatMap((bookcase) =>
          bookcase.shelves.flatMap((shelf) =>
            shelf.containers.map((container) => [
              container.id,
              { shelfId: shelf.id, layer: container.layer },
            ] as const),
          ),
        ),
      ),
    [map],
  );
  const draftContainerCollisions = useMemo(() => {
    const collisions: Array<[number, number]> = [];
    for (let firstIndex = 0; firstIndex < draft.containers.length; firstIndex += 1) {
      const first = draft.containers[firstIndex];
      const firstContext = containerContexts.get(first.id);
      for (
        let secondIndex = firstIndex + 1;
        secondIndex < draft.containers.length;
        secondIndex += 1
      ) {
        const second = draft.containers[secondIndex];
        const secondContext = containerContexts.get(second.id);
        if (
          firstContext?.shelfId === secondContext?.shelfId &&
          firstContext?.layer === secondContext?.layer &&
          overlapArea(first, second) > 0.0001
        ) {
          collisions.push([first.id, second.id]);
        }
      }
    }
    return collisions;
  }, [containerContexts, draft.containers]);
  const allMapBooks = useMemo(
    () => [
      ...map.bookcases.flatMap((bookcase) =>
        bookcase.shelves.flatMap((shelf) =>
          shelf.containers.flatMap((container) => container.books),
        ),
      ),
      ...map.outside_books,
      ...map.loaned_books,
    ],
    [map],
  );
  const cataloguePageMean = useMemo(
    () => map.effective_page_mean > 0
      ? map.effective_page_mean
      : effectiveCataloguePageMean(allMapBooks),
    [allMapBooks, map.effective_page_mean],
  );
  const mapContainers = useMemo(
    () => map.bookcases.flatMap((bookcase) =>
      bookcase.shelves.flatMap((shelf) =>
        shelf.containers.map((container) => ({
          ...container,
          shelfId: shelf.id,
          label: `${bookcase.name} · Shelf ${shelf.shelf_number} · ${
            container.layer === "BACKGROUND" ? "Background" : "Foreground"
          } ${container.container_type === "ROW" ? "Row" : "Pile"} ${
            container.container_number
          }`,
        })),
      ),
    ),
    [map],
  );
  const inspectedBook = allMapBooks.find((book) => book.id === inspectedBookId) ?? null;
  const inspectedContainerContext = useMemo(() => {
    if (inspectedContainerId === null) return null;
    for (const bookcase of map.bookcases) {
      for (const shelf of bookcase.shelves) {
        const container = shelf.containers.find(
          (candidate) => candidate.id === inspectedContainerId,
        );
        if (container) return { bookcase, shelf, container };
      }
    }
    return null;
  }, [inspectedContainerId, map.bookcases]);
  const projectedBooks = useMemo(() => {
    const placements = new Map(
      (rearrangementPreview?.placements ?? []).map((item) => [item.book_id, item]),
    );
    return allMapBooks.map((book) => {
      const placement = placements.get(book.id);
      return placement ? {
        ...book,
        container_id: placement.container_id,
        position: placement.position,
        status: placement.status,
      } : book;
    });
  }, [allMapBooks, rearrangementPreview]);
  const mapGenres = useMemo(
    () => Array.from(new Set(projectedBooks.flatMap(bookGenres))).sort(
      (first, second) => first.localeCompare(second),
    ),
    [projectedBooks],
  );
  const displayMap = useMemo<LibraryMapData>(() => ({
    ...map,
    bookcases: map.bookcases.map((bookcase) => ({
      ...bookcase,
      shelves: bookcase.shelves.map((shelf) => ({
        ...shelf,
        containers: shelf.containers.map((container) => ({
          ...container,
          books: projectedBooks.filter((book) =>
            book.status !== "CURRENTLY_READING" &&
            !book.is_on_loan &&
            book.container_id === container.id &&
            book.position !== null,
          ),
        })),
      })),
    })),
    outside_books: projectedBooks.filter(
      (book) => book.status === "CURRENTLY_READING" && !book.is_on_loan,
    ),
    loaned_books: projectedBooks.filter((book) => book.is_on_loan),
  }), [map, projectedBooks]);
  const readingGrid = useMemo(() => readingIconGrid(
    displayMap.outside_books.length,
    LEGACY_MAP_ASPECT_RATIO *
      activeLayout.outside.width / Math.max(activeLayout.outside.height, 0.01) *
      0.76 / 0.44,
  ), [
    activeLayout.outside.height,
    activeLayout.outside.width,
    displayMap.outside_books.length,
  ]);
  const loanedBookGroups = useMemo(
    () => proportionalOutsideBookGroups(
      displayMap.loaned_books,
      cataloguePageMean,
    ),
    [cataloguePageMean, displayMap.loaned_books],
  );
  const reservedBooksByContainer = useMemo(() => {
    const result = new Map<number, MapBook[]>();
    if (!rearranging && !editingLayout && !showRetainedShelfSpaces) return result;
    const seen = new Set<number>();
    for (const book of projectedBooks) {
      if (
        !seen.has(book.id) &&
        (book.status === "CURRENTLY_READING" || book.is_on_loan) &&
        book.container_id !== null &&
        book.position !== null
      ) {
        seen.add(book.id);
        result.set(book.container_id, [
          ...(result.get(book.container_id) ?? []),
          book,
        ]);
      }
    }
    return result;
  }, [editingLayout, projectedBooks, rearranging, showRetainedShelfSpaces]);
  const activeMoveBookId = rearrangementPreview?.next_active_book_id ??
    selectedMoveBookId;
  const selectedMoveBook = projectedBooks.find(
    (book) => book.id === selectedMoveBookId,
  ) ?? null;
  const activeMoveBook = projectedBooks.find(
    (book) => book.id === activeMoveBookId,
  ) ?? null;
  const movementGroups = rearrangementPreview
    ? rearrangementPreview.movement_groups?.length
      ? rearrangementPreview.movement_groups
      : rearrangementPreview.movement_log.length
        ? [rearrangementPreview.movement_log]
        : []
    : [];
  const selectedOriginalMoveBook = projectedBooks.find(
    (book) => book.id === selectedMoveBookId,
  ) ?? null;
  const selectedOriginalContainer = mapContainers.find(
    (container) => container.id === selectedOriginalMoveBook?.container_id,
  );
  const selectedOriginalLocation = selectedOriginalContainer &&
    selectedOriginalMoveBook?.position
    ? `${selectedOriginalContainer.label} · Position ${selectedOriginalMoveBook.position}`
    : "No retained physical position";
  const colourScale = useMemo(
    () => buildMapColourScale(colourMode, projectedBooks, selectedMapGenre),
    [projectedBooks, colourMode, selectedMapGenre],
  );
  const activeColourLabel = MAP_COLOUR_OPTIONS.find(
    (option) => option.value === colourMode,
  )?.label ?? "Reading status";
  const cameraBounds = useMemo(
    () => boundsForMapRects([
      ...activeLayout.bookcases,
      activeLayout.outside,
      activeLayout.loaned,
    ]),
    [activeLayout.bookcases, activeLayout.loaned, activeLayout.outside],
  );
  const resetMapView = useCallback(() => {
    setCamera(fitMapVerticalBounds(cameraBounds, viewportSize, 0));
  }, [cameraBounds, viewportSize]);
  const stopCameraHold = useCallback(() => {
    if (cameraHoldDelay.current !== null) {
      window.clearTimeout(cameraHoldDelay.current);
      cameraHoldDelay.current = null;
    }
    if (cameraHoldInterval.current !== null) {
      window.clearInterval(cameraHoldInterval.current);
      cameraHoldInterval.current = null;
    }
  }, []);

  useEffect(() => {
    const room = roomRef.current;
    if (!room) return;
    const observer = new ResizeObserver(([entry]) => {
      setViewportSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(room);
    return () => observer.disconnect();
  }, [loading]);

  useEffect(() => {
    if (
      loading ||
      cameraInitialized.current ||
      viewportSize.width <= 0 ||
      viewportSize.height <= 0
    ) return;
    cameraInitialized.current = true;
    resetMapView();
  }, [loading, resetMapView, viewportSize.height, viewportSize.width]);

  useEffect(() => {
    function closeWithKeyboard(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (inspectorOpen || inspectedBookId !== null || inspectedContainerId !== null) {
        clearInspectionSelection();
      } else if (inspectionMenuOpen) setInspectionMenuOpen(false);
      else if (focusMenuOpen) setFocusMenuOpen(false);
      else if (mapToolsOpen) setMapToolsOpen(false);
      else requestMapClose();
    }
    window.addEventListener("keydown", closeWithKeyboard);
    return () => window.removeEventListener("keydown", closeWithKeyboard);
  }, [
    focusMenuOpen,
    inspectedBookId,
    inspectedContainerId,
    inspectionMenuOpen,
    inspectorOpen,
    mapToolsOpen,
    requestMapClose,
  ]);

  useEffect(() => {
    if (!mapToolsOpen) return;
    function closeTools(event: MouseEvent) {
      if (!(event.target as Element).closest("[data-map-tools]")) {
        setMapToolsOpen(false);
      }
    }
    document.addEventListener("mousedown", closeTools);
    return () => document.removeEventListener("mousedown", closeTools);
  }, [mapToolsOpen]);

  useEffect(() => {
    if (!focusMenuOpen) return;
    function closeFocusMenu(event: MouseEvent) {
      if (!(event.target as Element).closest("[data-map-focus]")) {
        setFocusMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", closeFocusMenu);
    return () => document.removeEventListener("mousedown", closeFocusMenu);
  }, [focusMenuOpen]);

  useEffect(() => {
    if (!inspectionMenuOpen) return;
    function closeInspectionMenu(event: MouseEvent) {
      if (!(event.target as Element).closest("[data-map-inspection]")) {
        setInspectionMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", closeInspectionMenu);
    return () => document.removeEventListener("mousedown", closeInspectionMenu);
  }, [inspectionMenuOpen]);

  useEffect(() => {
    if (!layoutDirty) return;
    function protectDraftFromBrowserBack(event: PopStateEvent) {
      if (window.confirm("Discard the unsaved library layout changes?")) return;
      event.stopImmediatePropagation();
      window.history.pushState(
        { ...(window.history.state ?? {}), bookpileView: "bookpile-library-map" },
        "",
      );
    }
    window.addEventListener("popstate", protectDraftFromBrowserBack, true);
    return () => window.removeEventListener("popstate", protectDraftFromBrowserBack, true);
  }, [layoutDirty]);

  useEffect(() => stopCameraHold, [stopCameraHold]);

  function runCameraAction(action: MapCameraAction) {
    setCamera((current) => {
      if (action === "zoom-in") return zoomMapCamera(current, 1.25);
      if (action === "zoom-out") return zoomMapCamera(current, 0.8);
      return panMapCamera(current, action, viewportSize);
    });
  }

  function startCameraHold(action: MapCameraAction) {
    stopCameraHold();
    runCameraAction(action);
    cameraHoldDelay.current = window.setTimeout(() => {
      cameraHoldInterval.current = window.setInterval(
        () => runCameraAction(action),
        70,
      );
    }, 280);
  }

  function cameraControlHandlers(action: MapCameraAction) {
    return {
      onPointerDown: (event: React.PointerEvent<HTMLButtonElement>) => {
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        startCameraHold(action);
      },
      onPointerUp: stopCameraHold,
      onPointerCancel: stopCameraHold,
      onPointerLeave: stopCameraHold,
      onClick: (event: React.MouseEvent<HTMLButtonElement>) => {
        if (event.detail === 0) runCameraAction(action);
      },
    };
  }

  function roomPoint(clientX: number, clientY: number) {
    const bounds = roomRef.current?.getBoundingClientRect();
    return {
      x: clientX - (bounds?.left ?? 0),
      y: clientY - (bounds?.top ?? 0),
    };
  }

  function initializePinchGesture() {
    const points = [...cameraPointers.current.values()];
    if (points.length < 2) return;
    const [first, second] = points;
    const midpoint = {
      x: (first.x + second.x) / 2,
      y: (first.y + second.y) / 2,
    };
    const gesture = cameraGesture.current;
    gesture.pinchDistance = Math.max(
      1,
      Math.hypot(second.x - first.x, second.y - first.y),
    );
    gesture.pinchMidpoint = midpoint;
    gesture.pinchCamera = camera;
    gesture.pinchAnchor = mapViewportPointToWorld(camera, viewportSize, midpoint);
    gesture.moved = true;
  }

  function beginCameraGesture(event: React.PointerEvent<HTMLDivElement>) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const target = event.target as Element;
    if (target.closest(
      ".map-camera-controls, .map-direct-handle, .map-svg-resize-handle, " +
      ".map-shelf-resize-handle, .map-layout-editor, .map-rearrangement-panel",
    )) return;
    const point = roomPoint(event.clientX, event.clientY);
    cameraPointers.current.set(event.pointerId, point);
    event.currentTarget.setPointerCapture(event.pointerId);
    if (cameraPointers.current.size === 1) {
      cameraGesture.current = {
        moved: false,
        totalDistance: 0,
        pinchDistance: null,
        pinchMidpoint: null,
        pinchCamera: null,
        pinchAnchor: null,
      };
    } else if (cameraPointers.current.size === 2) {
      initializePinchGesture();
    }
  }

  function moveCameraGesture(event: React.PointerEvent<HTMLDivElement>) {
    const previous = cameraPointers.current.get(event.pointerId);
    if (!previous) return;
    const point = roomPoint(event.clientX, event.clientY);
    cameraPointers.current.set(event.pointerId, point);
    const gesture = cameraGesture.current;
    if (cameraPointers.current.size >= 2) {
      const points = [...cameraPointers.current.values()];
      const [first, second] = points;
      const midpoint = {
        x: (first.x + second.x) / 2,
        y: (first.y + second.y) / 2,
      };
      if (
        gesture.pinchDistance === null ||
        gesture.pinchMidpoint === null ||
        gesture.pinchCamera === null ||
        gesture.pinchAnchor === null
      ) {
        initializePinchGesture();
        return;
      }
      const distance = Math.max(
        1,
        Math.hypot(second.x - first.x, second.y - first.y),
      );
      const zoomed = zoomMapCamera(
        gesture.pinchCamera,
        distance / gesture.pinchDistance,
        gesture.pinchAnchor,
      );
      setCamera(panMapCameraByPixels(
        zoomed,
        {
          x: midpoint.x - gesture.pinchMidpoint.x,
          y: midpoint.y - gesture.pinchMidpoint.y,
        },
        viewportSize,
      ));
      gesture.moved = true;
      return;
    }
    const delta = { x: point.x - previous.x, y: point.y - previous.y };
    gesture.totalDistance += Math.hypot(delta.x, delta.y);
    if (gesture.totalDistance > 4) gesture.moved = true;
    if (gesture.moved) {
      event.preventDefault();
      setCamera((current) => panMapCameraByPixels(current, delta, viewportSize));
    }
  }

  function endCameraGesture(event: React.PointerEvent<HTMLDivElement>) {
    if (!cameraPointers.current.has(event.pointerId)) return;
    cameraPointers.current.delete(event.pointerId);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (cameraPointers.current.size === 1) {
      const remaining = [...cameraPointers.current.values()][0];
      cameraGesture.current.pinchDistance = null;
      cameraGesture.current.pinchMidpoint = remaining;
      cameraGesture.current.pinchCamera = null;
      cameraGesture.current.pinchAnchor = null;
    }
    if (cameraPointers.current.size === 0 && cameraGesture.current.moved) {
      suppressNextMapClick.current = true;
    }
  }

  function zoomCameraWithWheel(event: React.WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    const point = roomPoint(event.clientX, event.clientY);
    const factor = Math.exp(-Math.max(-120, Math.min(120, event.deltaY)) * 0.002);
    setCamera((current) => zoomMapCamera(
      current,
      factor,
      mapViewportPointToWorld(current, viewportSize, point),
    ));
  }

  function updateBookcaseRect(field: keyof VisualRect, value: number) {
    setDraft((current) => ({
      ...current,
      bookcases: current.bookcases.map((item) =>
        item.id === Number(selectedBookcase)
          ? { ...item, [field]: value }
          : item,
      ),
    }));
  }

  function hierarchyFocusBounds(): MapWorldBounds | null {
    const bookcase = focusedBookcaseItem;
    const rect = bookcase ? bookcaseRects.get(bookcase.id) : null;
    if (!bookcase || !rect) return null;
    const focusedContainer = focusedShelfItem
      ? focusedContainerItems.find(
          (container) => container.id === Number(focusContainer),
        ) ?? null
      : null;
    return mapHierarchyBounds(
      bookcase,
      focusedShelfItem ?? null,
      focusedContainer,
      rect,
      shelfWeights,
      containerRects,
    );
  }

  function focusSelectedHierarchy() {
    const bounds = hierarchyFocusBounds();
    if (!bounds) return;
    setCamera(fitMapBounds(bounds, viewportSize));
    setFocusMenuOpen(false);
    setLegendExpanded(false);
  }

  function clearInspectionSelection() {
    setInspectedBookId(null);
    setInspectedContainerId(null);
    setInspectorOpen(false);
    setInspectorCompleteBook(null);
    setInspectorDetailsError("");
  }

  function chooseInspectionMode(mode: MapInspectionMode) {
    clearInspectionSelection();
    setInspectionMode(mode);
    setInspectionMenuOpen(false);
    setFocusMenuOpen(false);
    setMapToolsOpen(false);
  }

  function inspectBook(book: MapBook, open = false) {
    const nextId = nextInspectionId(inspectedBookId, book.id, open);
    if (nextId === null) {
      clearInspectionSelection();
      return;
    }
    setInspectedBookId(nextId);
    setInspectedContainerId(null);
    setInspectorOpen(open);
    setInspectorCompleteBook(null);
    setInspectorDetailsError("");
  }

  function inspectContainer(containerId: number, open = false) {
    const nextId = nextInspectionId(inspectedContainerId, containerId, open);
    if (nextId === null) {
      clearInspectionSelection();
      return;
    }
    setInspectedContainerId(nextId);
    setInspectedBookId(null);
    setInspectorOpen(open);
    setInspectorCompleteBook(null);
    setInspectorDetailsError("");
  }

  function handleBookSelection(book: MapBook, open = false) {
    if (inspectionMode === "book") {
      inspectBook(book, open);
      return;
    }
    if (inspectionMode === "container") {
      if (book.container_id !== null) inspectContainer(book.container_id, open);
      return;
    }
    onBookFilter(book);
  }

  function selectedInspectionBounds(): MapWorldBounds | null {
    if (inspectedContainerContext) {
      const rect = bookcaseRects.get(inspectedContainerContext.bookcase.id);
      if (!rect) return null;
      return mapHierarchyBounds(
        inspectedContainerContext.bookcase,
        inspectedContainerContext.shelf,
        inspectedContainerContext.container,
        rect,
        shelfWeights,
        containerRects,
      );
    }
    if (!inspectedBook) return null;
    if (inspectedBook.is_on_loan) {
      return {
        minX: activeLayout.loaned.x,
        minY: activeLayout.loaned.y,
        maxX: activeLayout.loaned.x + activeLayout.loaned.width,
        maxY: activeLayout.loaned.y + activeLayout.loaned.height,
      };
    }
    if (inspectedBook.status === "CURRENTLY_READING") {
      return {
        minX: activeLayout.outside.x,
        minY: activeLayout.outside.y,
        maxX: activeLayout.outside.x + activeLayout.outside.width,
        maxY: activeLayout.outside.y + activeLayout.outside.height,
      };
    }
    if (inspectedBook.container_id === null) return null;
    const context = (() => {
      for (const bookcase of map.bookcases) {
        for (const shelf of bookcase.shelves) {
          const container = shelf.containers.find(
            (candidate) => candidate.id === inspectedBook.container_id,
          );
          if (container) return { bookcase, shelf, container };
        }
      }
      return null;
    })();
    if (!context) return null;
    const rect = bookcaseRects.get(context.bookcase.id);
    return rect
      ? mapHierarchyBounds(
          context.bookcase,
          context.shelf,
          context.container,
          rect,
          shelfWeights,
          containerRects,
        )
      : null;
  }

  function frameInspectionSelection() {
    const bounds = selectedInspectionBounds();
    if (!bounds) return;
    setCamera(fitMapBounds(bounds, viewportSize));
    setLegendExpanded(false);
  }

  async function showCompleteInspectorBook(bookId: number) {
    setInspectorDetailsLoading(true);
    setInspectorDetailsError("");
    try {
      setInspectorCompleteBook(await api.book(bookId));
    } catch (err) {
      setInspectorDetailsError(
        err instanceof Error ? err.message : "Unable to load complete book information",
      );
    } finally {
      setInspectorDetailsLoading(false);
    }
  }

  function updateContainerRect(containerId: number, rect: VisualRect) {
    setDraft((current) => {
      const original = current.containers.find((item) => item.id === containerId);
      const context = containerContexts.get(containerId);
      if (!original || !context) return current;
      const candidate = {
        x: Math.max(0, Math.min(100 - rect.width, rect.x)),
        y: Math.max(0, Math.min(100 - rect.height, rect.y)),
        width: Math.max(4, Math.min(100 - rect.x, rect.width)),
        height: Math.max(4, Math.min(100 - rect.y, rect.height)),
      };
      const peers = current.containers.filter((item) => {
        if (item.id === containerId) return false;
        const peerContext = containerContexts.get(item.id);
        return (
          peerContext?.shelfId === context.shelfId &&
          peerContext.layer === context.layer
        );
      });
      const previousOverlap = peers.reduce(
        (total, peer) => total + overlapArea(original, peer),
        0,
      );
      const nextOverlap = peers.reduce(
        (total, peer) => total + overlapArea(candidate, peer),
        0,
      );
      if (nextOverlap > previousOverlap + 0.0001) return current;
      return {
        ...current,
        containers: current.containers.map((item) =>
          item.id === containerId ? { ...item, ...candidate } : item,
        ),
      };
    });
  }

  function updateShelfWeights(
    firstShelfId: number,
    firstWeight: number,
    secondShelfId: number,
    secondWeight: number,
  ) {
    setDraft((current) => ({
      ...current,
      shelves: current.shelves.map((item) => {
        if (item.id === firstShelfId) {
          return { ...item, height_weight: firstWeight };
        }
        if (item.id === secondShelfId) {
          return { ...item, height_weight: secondWeight };
        }
        return item;
      }),
    }));
  }

  function beginRoomRectInteraction(
    event: React.PointerEvent<HTMLElement>,
    start: VisualRect,
    mode: "move" | "resize",
    update: (rect: VisualRect) => void,
  ) {
    event.preventDefault();
    event.stopPropagation();
    const world = worldRef.current;
    if (!world) return;
    const bounds = world.getBoundingClientRect();
    const startX = event.clientX;
    const startY = event.clientY;
    const move = (moveEvent: PointerEvent) => {
      const deltaX = (moveEvent.clientX - startX) / Math.max(bounds.width, 1) * 100;
      const deltaY = (moveEvent.clientY - startY) / Math.max(bounds.height, 1) * 100;
      update(
        mode === "move"
          ? {
              ...start,
              x: start.x + deltaX,
              y: start.y + deltaY,
            }
          : {
              ...start,
              width: Math.max(0.5, start.width + deltaX),
              height: Math.max(0.5, start.height + deltaY),
            },
      );
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
  }

  function resetRearrangement(leaveMode = false) {
    setSelectedMoveBookId(null);
    setRearrangementSteps([]);
    setCompletedRearrangements([]);
    setCompletedPreviewStack([]);
    setRearrangementPreview(null);
    setPreciseContainer("");
    setPrecisePosition(1);
    setReadingExitStatus("");
    setPendingReadingDestination(null);
    setDragGhost(null);
    setError("");
    if (!leaveMode) {
      setOldPositionMode("COLLAPSE");
      setNewPositionMode("SQUEEZE");
      setReleaseShelfSpace(false);
    }
  }

  async function previewSteps(
    bookId: number,
    steps: RearrangementStep[],
    oldMode = oldPositionMode,
  ) {
    setPreviewingMove(true);
    setError("");
    try {
      const result = await api.previewRearrangement({
        completed_operations: completedRearrangements,
        book_id: bookId,
        old_position_mode: oldMode,
        release_shelf_space: releaseShelfSpace,
        steps,
      });
      setRearrangementSteps(steps);
      setRearrangementPreview(result);
      setOldPositionMode(result.effective_old_position_mode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to preview movement");
    } finally {
      setPreviewingMove(false);
    }
  }

  function startMoveBook(book: MapBook) {
    if (book.is_on_loan) {
      setError("Return this book before rearranging its physical position.");
      return;
    }
    setSelectedMoveBookId(book.id);
    setRearrangementSteps([]);
    if (completedRearrangements.length === 0) setRearrangementPreview(null);
    setReadingExitStatus("");
    setPendingReadingDestination(null);
    setError("");
    if (book.container_id !== null) {
      setPreciseContainer(String(book.container_id));
      setPrecisePosition(book.position ?? 1);
    }
  }

  function selectMoveBook(book: MapBook) {
    if (ignoreNextBookClick.current) {
      ignoreNextBookClick.current = false;
      return;
    }
    if (selectedMoveBookId !== null) {
      if (rearrangementSteps.length > 0 && rearrangementPreview?.complete) {
        setError("Apply or cancel the current movement before selecting another book.");
        return;
      }
      if (book.id === activeMoveBookId) return;
      if (book.container_id !== null && book.position !== null) {
        void addPhysicalDestination(book.container_id, book.position);
      }
      return;
    }
    startMoveBook(book);
  }

  async function addPhysicalDestination(
    containerId: number,
    position: number,
    context?: {
      bookId: number;
      steps: RearrangementStep[];
      sourceBook: MapBook;
      readingStatus?: "PENDING" | "READ";
    },
  ) {
    const bookId = context?.bookId ?? selectedMoveBookId;
    const steps = context?.steps ?? rearrangementSteps;
    const sourceBook = context?.sourceBook ?? selectedMoveBook;
    const returnStatus = context?.readingStatus ?? readingExitStatus;
    if (
      bookId === null ||
      !sourceBook ||
      (!context && rearrangementSteps.length > 0 && rearrangementPreview?.complete)
    ) {
      return;
    }
    if (sourceBook.status === "CURRENTLY_READING" && !returnStatus) {
      setPendingReadingDestination({ containerId, position });
      setError("");
      return;
    }
    setPendingReadingDestination(null);
    const step: RearrangementStep = {
      destination_kind: "PHYSICAL",
      container_id: containerId,
      position,
      new_position_mode: newPositionMode,
      reading_exit_status: sourceBook.status === "CURRENTLY_READING"
        ? returnStatus || null
        : null,
    };
    await previewSteps(bookId, [...steps, step]);
  }

  async function addReadingDestination(context?: {
    bookId: number;
    steps: RearrangementStep[];
    sourceBook: MapBook;
  }) {
    const bookId = context?.bookId ?? selectedMoveBookId;
    const steps = context?.steps ?? rearrangementSteps;
    const sourceBook = context?.sourceBook ?? selectedMoveBook;
    if (bookId === null || !sourceBook || steps.length > 0) return;
    if (sourceBook.status === "CURRENTLY_READING") return;
    await previewSteps(bookId, [{ destination_kind: "READING" }]);
  }

  function chooseReadingReturnStatus(status: "PENDING" | "READ") {
    setReadingExitStatus(status);
    setError("");
    if (pendingReadingDestination && selectedMoveBookId && selectedMoveBook) {
      void addPhysicalDestination(
        pendingReadingDestination.containerId,
        pendingReadingDestination.position,
        {
          bookId: selectedMoveBookId,
          steps: rearrangementSteps,
          sourceBook: selectedMoveBook,
          readingStatus: status,
        },
      );
    }
  }

  function restoreLastCompletedOperation() {
    const previous = completedRearrangements.at(-1);
    if (!previous) return false;
    setCompletedRearrangements((current) => current.slice(0, -1));
    setRearrangementPreview(completedPreviewStack.at(-1) ?? null);
    setCompletedPreviewStack((current) => current.slice(0, -1));
    setSelectedMoveBookId(previous.book_id);
    setOldPositionMode(previous.old_position_mode);
    setReleaseShelfSpace(previous.release_shelf_space ?? false);
    setRearrangementSteps(previous.steps);
    setNewPositionMode(
      previous.steps.at(-1)?.new_position_mode ?? "SQUEEZE",
    );
    setError("");
    return true;
  }

  async function undoRearrangementStep() {
    if (rearrangementSteps.length === 0) {
      restoreLastCompletedOperation();
      return;
    }
    if (selectedMoveBookId === null) return;
    const next = rearrangementSteps.slice(0, -1);
    if (next.length === 0) {
      if (restoreLastCompletedOperation()) return;
      setRearrangementSteps([]);
      setRearrangementPreview(null);
      setError("");
      return;
    }
    await previewSteps(selectedMoveBookId, next);
  }

  async function applyRearrangement() {
    if (
      selectedMoveBookId === null ||
      rearrangementSteps.length === 0 ||
      !rearrangementPreview?.valid_to_apply
    ) return;
    const statusChanges = rearrangementPreview.placements.some((placement) => {
      const original = allMapBooks.find((book) => book.id === placement.book_id);
      return original && original.status !== placement.status;
    });
    const summary = movementGroups
      .map((group, index) => (
        movementGroups.length > 1
          ? `Move ${index + 1}\n${group.join("\n")}`
          : group.join("\n")
      ))
      .join("\n\n");
    if (!window.confirm(
      `${statusChanges ? "This also changes a reading status.\n\n" : ""}${summary}\n\nApply these changes?`,
    )) return;
    setApplyingMove(true);
    setError("");
    try {
      await api.applyRearrangement(
        {
          completed_operations: completedRearrangements,
          book_id: selectedMoveBookId,
          old_position_mode: oldPositionMode,
          release_shelf_space: releaseShelfSpace,
          steps: rearrangementSteps,
        },
        rearrangementPreview.revision,
      );
      resetRearrangement();
      await Promise.all([loadMap(), onChanged()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to apply movement");
    } finally {
      setApplyingMove(false);
    }
  }

  function startAnotherRearrangement() {
    if (
      selectedMoveBookId === null ||
      !rearrangementPreview?.complete ||
      rearrangementSteps.length === 0
    ) return;
    setCompletedRearrangements((current) => [
      ...current,
      {
        book_id: selectedMoveBookId,
        old_position_mode: oldPositionMode,
        release_shelf_space: releaseShelfSpace,
        steps: rearrangementSteps,
      },
    ]);
    setCompletedPreviewStack((current) => [
      ...current,
      rearrangementPreview,
    ]);
    setSelectedMoveBookId(null);
    setRearrangementSteps([]);
    setOldPositionMode("COLLAPSE");
    setNewPositionMode("SQUEEZE");
    setReleaseShelfSpace(false);
    setReadingExitStatus("");
    setPendingReadingDestination(null);
    setPreciseContainer("");
    setPrecisePosition(1);
    setError("");
  }

  function beginBookDrag(
    book: MapBook,
    event: React.PointerEvent<Element>,
  ) {
    const beginningSelection = selectedMoveBookId === null;
    if (
      (!beginningSelection && book.id !== activeMoveBookId) ||
      (!beginningSelection && rearrangementPreview?.complete)
    ) return;
    event.stopPropagation();
    if (beginningSelection) startMoveBook(book);
    const dragBookId = beginningSelection ? book.id : selectedMoveBookId;
    const dragSteps = beginningSelection ? [] : rearrangementSteps;
    const dragSourceBook = beginningSelection ? book : selectedMoveBook;
    if (dragBookId === null || !dragSourceBook) return;
    const startX = event.clientX;
    const startY = event.clientY;
    let dragging = false;
    const move = (moveEvent: PointerEvent) => {
      if (
        !dragging &&
        Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY) > 6
      ) dragging = true;
      if (dragging) {
        setDragGhost({ title: book.title, x: moveEvent.clientX, y: moveEvent.clientY });
      }
    };
    const stop = (upEvent: PointerEvent) => {
      window.removeEventListener("pointermove", move);
      setDragGhost(null);
      if (!dragging) return;
      ignoreNextBookClick.current = true;
      const target = document.elementFromPoint(upEvent.clientX, upEvent.clientY)
        ?.closest<SVGElement>("[data-container-id][data-position]");
      const readingTarget = document.elementFromPoint(
        upEvent.clientX,
        upEvent.clientY,
      )?.closest("[data-reading-target]");
      const containerId = Number(target?.dataset.containerId);
      const position = Number(target?.dataset.position);
      if (containerId > 0 && position > 0) {
        void addPhysicalDestination(containerId, position, {
          bookId: dragBookId,
          steps: dragSteps,
          sourceBook: dragSourceBook,
        });
      } else if (readingTarget) {
        void addReadingDestination({
          bookId: dragBookId,
          steps: dragSteps,
          sourceBook: dragSourceBook,
        });
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
  }

  async function saveLayout() {
    setSaving(true);
    setError("");
    try {
      const saved = await api.updateVisualLayout(draft);
      setMap((current) => ({ ...current, layout: saved }));
      setDraft(structuredClone(saved));
      setEditingLayout(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save layout");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop map-backdrop" onMouseDown={requestMapClose}>
      <div
        className={`dialog map-dialog map-fullscreen ${inspectorOpen ? "inspector-open" : ""}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="dialog-header">
          <div className="map-title-chip">
            <h2>Library map</h2>
          </div>
          <div className="map-header-actions">
            <div className="map-inspection" data-map-inspection>
              <button
                className={`outline-button map-inspection-trigger ${inspectionMode ? "active" : ""}`}
                type="button"
                aria-label="Inspection mode"
                aria-haspopup="menu"
                aria-expanded={inspectionMenuOpen}
                disabled={editingLayout || rearranging}
                title={inspectionMode === "book"
                  ? "Inspect books"
                  : inspectionMode === "container"
                    ? "Inspect containers"
                    : "Choose inspection mode"}
                onClick={() => {
                  setFocusMenuOpen(false);
                  setMapToolsOpen(false);
                  setInspectionMenuOpen((current) => !current);
                }}
              >
                <Info size={18} />
              </button>
              {inspectionMenuOpen && (
                <div className="menu-popover map-inspection-menu" role="menu">
                  <strong>Inspection mode</strong>
                  <button
                    role="menuitemradio"
                    aria-checked={inspectionMode === "book"}
                    className={inspectionMode === "book" ? "active" : ""}
                    onClick={() => chooseInspectionMode("book")}
                  >
                    <BookOpen size={16} /> Inspect books
                  </button>
                  <button
                    role="menuitemradio"
                    aria-checked={inspectionMode === "container"}
                    className={inspectionMode === "container" ? "active" : ""}
                    onClick={() => chooseInspectionMode("container")}
                  >
                    <LibraryBig size={16} /> Inspect containers
                  </button>
                  <button
                    role="menuitemradio"
                    aria-checked={inspectionMode === null}
                    onClick={() => chooseInspectionMode(null)}
                  >
                    <X size={16} /> Exit inspection
                  </button>
                </div>
              )}
            </div>
            <div className="map-focus" data-map-focus>
              <button
                className="outline-button map-focus-trigger"
                type="button"
                aria-label="Focus map"
                aria-haspopup="menu"
                aria-expanded={focusMenuOpen}
                title="Focus furniture, shelf, or container"
                onClick={() => {
                  setInspectionMenuOpen(false);
                  setMapToolsOpen(false);
                  setFocusMenuOpen((current) => !current);
                }}
              >
                <Focus size={18} />
              </button>
              {focusMenuOpen && (
                <div className="menu-popover map-focus-menu" role="menu">
                  <strong>Focus map</strong>
                  <label>
                    Furniture
                    <select
                      value={focusBookcase}
                      onChange={(event) => {
                        setFocusBookcase(event.target.value);
                        setFocusShelf("");
                        setFocusContainer("");
                      }}
                    >
                      {map.bookcases.map((bookcase) => (
                        <option key={bookcase.id} value={bookcase.id}>
                          {bookcase.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Shelf <small>optional</small>
                    <select
                      value={focusShelf}
                      onChange={(event) => {
                        setFocusShelf(event.target.value);
                        setFocusContainer("");
                      }}
                    >
                      <option value="">Whole furniture</option>
                      {focusedShelfItems.map((shelf) => (
                        <option key={shelf.id} value={shelf.id}>
                          Shelf {shelf.shelf_number}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Container <small>optional</small>
                    <select
                      value={focusContainer}
                      disabled={!focusedShelfItem}
                      onChange={(event) => setFocusContainer(event.target.value)}
                    >
                      <option value="">Whole shelf</option>
                      {focusedContainerItems.map((container) => (
                        <option key={container.id} value={container.id}>
                          {container.layer === "BACKGROUND" ? "Background" : "Foreground"}{" "}
                          {container.container_type === "ROW" ? "row" : "pile"}{" "}
                          {container.container_number}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="map-focus-actions">
                    <button type="button" onClick={() => {
                      resetMapView();
                      setFocusMenuOpen(false);
                    }}>
                      <RotateCcw size={15} /> Reset world
                    </button>
                    <button
                      type="button"
                      className="primary-button"
                      disabled={!focusedBookcaseItem}
                      onClick={focusSelectedHierarchy}
                    >
                      <Focus size={15} /> Focus
                    </button>
                  </div>
                </div>
              )}
            </div>
            <div className="map-tools" data-map-tools>
              <button
                className={`outline-button map-tools-trigger ${editingLayout || rearranging ? "active" : ""}`}
                type="button"
                aria-label="Map tools"
                aria-haspopup="menu"
                aria-expanded={mapToolsOpen}
                title="Map tools"
                onClick={() => {
                  setInspectionMenuOpen(false);
                  setFocusMenuOpen(false);
                  setMapToolsOpen((current) => !current);
                }}
              >
                <Settings2 size={18} />
              </button>
              {mapToolsOpen && (
                <div className="menu-popover map-tools-menu" role="menu">
                  {!MAP_REARRANGEMENT_ENABLED && (
                    <p className="map-tools-notice">
                      Book rearrangement returns after its complete floating
                      workflow is integrated with pan and zoom.
                    </p>
                  )}
                  <button
                    role="menuitem"
                    disabled={!MAP_REARRANGEMENT_ENABLED}
                    onClick={() => {
                      if (rearranging) resetRearrangement();
                      setRearranging((current) => !current);
                      setRearrangementPanelMinimized(false);
                      chooseInspectionMode(null);
                      setLegendExpanded(false);
                      setMapToolsOpen(false);
                    }}
                  >
                    <ArrowRightLeft size={16} />
                    {rearranging ? "Exit rearrange" : "Rearrange books"}
                  </button>
                  {!editingLayout ? (
                    <button
                      role="menuitem"
                      disabled={!MAP_LAYOUT_EDITOR_ENABLED || rearranging}
                      onClick={() => {
                        setDraft(structuredClone(map.layout));
                        chooseInspectionMode(null);
                        setEditingLayout(true);
                        setLayoutPanelMinimized(false);
                        setLegendExpanded(false);
                        setMapToolsOpen(false);
                      }}
                    >
                      <Pencil size={16} /> Edit layout
                    </button>
                  ) : (
                    <>
                      <button
                        role="menuitem"
                        onClick={() => {
                          cancelLayoutEditing();
                          setMapToolsOpen(false);
                        }}
                      >
                        <RotateCcw size={16} /> Cancel layout editing
                      </button>
                      <button
                        role="menuitem"
                        disabled={saving || draftContainerCollisions.length > 0}
                        onClick={() => {
                          setMapToolsOpen(false);
                          void saveLayout();
                        }}
                      >
                        <Save size={16} /> {saving ? "Saving…" : "Save layout"}
                      </button>
                    </>
                  )}
                  <label className="map-tools-toggle">
                    <input
                      type="checkbox"
                      checked={showRetainedShelfSpaces}
                      onChange={(event) =>
                        setShowRetainedShelfSpaces(event.target.checked)}
                    />
                    <span>
                      <strong>Show retained shelf spaces</strong>
                      <small>Outline books that are Reading or On loan.</small>
                    </span>
                  </label>
                </div>
              )}
            </div>
            <button className="outline-button map-exit-button" onClick={requestMapClose}>
              <ArrowLeft size={17} /> <span>Back to catalogue</span>
            </button>
          </div>
        </div>
        <div className={`map-legend ${legendExpanded ? "expanded" : "collapsed"}`}>
          {!legendExpanded ? (
            <button
              type="button"
              className="map-legend-summary"
              aria-expanded="false"
              onClick={() => setLegendExpanded(true)}
            >
              <span>Colour by {activeColourLabel}</span>
              <ChevronDown size={16} />
            </button>
          ) : <>
          <label className="map-colour-picker">
            Colour by
            <select
              value={colourMode}
              onChange={(event) => setColourMode(event.target.value as MapColourMode)}
            >
              {MAP_COLOUR_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {colourMode === "genre" && (
            <label className="map-colour-picker map-genre-picker">
              Genre
              <select
                value={selectedMapGenre}
                onChange={(event) => setSelectedMapGenre(event.target.value)}
              >
                <option value="">Choose a genre…</option>
                {mapGenres.map((genre) => (
                  <option key={genre} value={genre}>{genre}</option>
                ))}
              </select>
            </label>
          )}
          {colourMode === "status" ? (
            <div className="map-status-legend">
              <span><i className="pending" /> Pending</span>
              <span><i className="reading" /> Reading…</span>
              <span><i className="read" /> Read</span>
            </div>
          ) : colourScale.continuous ? (
            <div className="map-scale-legend" aria-label={`${colourScale.label} scale`}>
              <span>{colourScale.lowLabel}</span>
              <i className="map-colour-gradient" />
              <span>{colourScale.highLabel}</span>
              {colourScale.legendItems.map((item) => (
                <span key={item.label}>
                  <i style={{ background: item.colour }} /> {item.label}
                </span>
              ))}
            </div>
          ) : (
            <div className="map-status-legend" aria-label={`${colourScale.label} legend`}>
              {colourScale.legendItems.map((item) => (
                <span key={item.label}>
                  <i style={{ background: item.colour }} /> {item.label}
                </span>
              ))}
            </div>
          )}
          <button
            type="button"
            className="map-legend-collapse"
            aria-label="Collapse colour legend"
            title="Collapse colour legend"
            onClick={() => setLegendExpanded(false)}
          >
            <ChevronUp size={16} />
          </button>
          </>}
        </div>
        {error && <div className="form-error">{error}</div>}
        {loading ? (
          <div className="empty-state">Drawing the library…</div>
        ) : (
          <>
            {editingLayout && (
              <aside className={`map-layout-editor map-workspace-panel ${
                layoutPanelMinimized ? "minimized" : ""
              }`}>
                <header className="map-workspace-header">
                  <div>
                    <p className="eyebrow dark">Visual workspace</p>
                    <h3>Edit layout</h3>
                  </div>
                  <div className="map-workspace-actions">
                    <button
                      className="icon-button"
                      type="button"
                      title={layoutPanelMinimized ? "Restore editor" : "Minimize editor"}
                      aria-label={layoutPanelMinimized ? "Restore layout editor" : "Minimize layout editor"}
                      onClick={() => {
                        setLayoutPanelMinimized((current) => !current);
                        setLegendExpanded(false);
                      }}
                    >
                      {layoutPanelMinimized ? <ChevronUp /> : <ChevronDown />}
                    </button>
                    {!layoutPanelMinimized && (
                      <>
                        <button
                          className="outline-button"
                          type="button"
                          onClick={cancelLayoutEditing}
                        >
                          Cancel
                        </button>
                        <button
                          className="primary-button"
                          type="button"
                          disabled={saving || draftContainerCollisions.length > 0}
                          onClick={() => void saveLayout()}
                        >
                          <Save size={15} /> {saving ? "Saving…" : "Save"}
                        </button>
                      </>
                    )}
                  </div>
                </header>
                {!layoutPanelMinimized && <div className="map-layout-editor-content">
                {error && <div className="form-error map-workspace-error">{error}</div>}
                <p className="map-direct-help">
                  Direct controls: drag ↕ to move furniture or the Reading area,
                  drag ↘ to resize them, drag a container to move it, and drag
                  shelf dividers or container corners to resize.
                  {draftContainerCollisions.length > 0 && (
                    <strong>
                      {" "}Separate {draftContainerCollisions.length} existing
                      same-layer container overlap
                      {draftContainerCollisions.length === 1 ? "" : "s"} before saving.
                    </strong>
                  )}
                </p>
                <div className="map-editor-section">
                  <label>
                    Furniture
                    <select
                      value={selectedBookcase}
                      onChange={(event) => setSelectedBookcase(event.target.value)}
                    >
                      {map.bookcases.map((bookcase) => (
                        <option key={bookcase.id} value={bookcase.id}>
                          {bookcase.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {selectedBookcaseItem && (
                    <div className="map-range-grid">
                      {(["x", "y", "width", "height"] as const).map((field) => (
                        <MapNumberField
                          key={field}
                          label={field === "x" ? "Horizontal" : field === "y"
                            ? "Vertical" : field[0].toUpperCase() + field.slice(1)}
                          value={selectedBookcaseItem[field]}
                          positive={field === "width" || field === "height"}
                          onChange={(value) => updateBookcaseRect(field, value)}
                        />
                      ))}
                    </div>
                  )}
                </div>
                <div className="map-editor-section">
                  <strong className="map-editor-title">On-loan area</strong>
                  <div className="map-range-grid">
                    {(["x", "y", "width", "height"] as const).map((field) => (
                      <MapNumberField
                        key={field}
                        label={field === "x" ? "Horizontal" : field === "y" ? "Vertical" : field[0].toUpperCase() + field.slice(1)}
                        value={draft.loaned[field]}
                        positive={field === "width" || field === "height"}
                        onChange={(value) => setDraft((current) => ({ ...current, loaned: { ...current.loaned, [field]: value } }))}
                      />
                    ))}
                  </div>
                </div>
                <div className="map-editor-section">
                  <strong className="map-editor-title">Reading / outside area</strong>
                  <div className="map-range-grid">
                    {(["x", "y", "width", "height"] as const).map((field) => (
                      <MapNumberField
                        key={field}
                        label={field === "x" ? "Horizontal" : field === "y"
                          ? "Vertical" : field[0].toUpperCase() + field.slice(1)}
                        value={draft.outside[field]}
                        positive={field === "width" || field === "height"}
                        onChange={(value) =>
                          setDraft((current) => ({
                            ...current,
                            outside: { ...current.outside, [field]: value },
                          }))}
                      />
                    ))}
                  </div>
                </div>
                <div className="map-editor-section">
                  <label>
                    Shelf height
                    <select
                      value={selectedShelf}
                      onChange={(event) => setSelectedShelf(event.target.value)}
                    >
                      {map.bookcases.flatMap((bookcase) =>
                        bookcase.shelves.map((shelf) => (
                          <option key={shelf.id} value={shelf.id}>
                            {bookcase.name} · Shelf {shelf.shelf_number}
                          </option>
                        )),
                      )}
                    </select>
                  </label>
                  {selectedShelfItem && (
                    <RangeField
                      label="Relative height"
                      value={selectedShelfItem.height_weight}
                      min={0.25}
                      max={8}
                      step={0.25}
                      onChange={(value) =>
                        setDraft((current) => ({
                          ...current,
                          shelves: current.shelves.map((item) =>
                            item.id === selectedShelfItem.id
                              ? { ...item, height_weight: value }
                              : item,
                          ),
                        }))}
                    />
                  )}
                </div>
                <div className="map-editor-section">
                  <label>
                    Container size
                    <select
                      value={selectedContainer}
                      onChange={(event) => setSelectedContainer(event.target.value)}
                    >
                      {map.bookcases.flatMap((bookcase) =>
                        bookcase.shelves.flatMap((shelf) =>
                          shelf.containers.map((container) => (
                            <option key={container.id} value={container.id}>
                              {bookcase.name} · S{shelf.shelf_number} ·{" "}
                              {container.layer === "BACKGROUND" ? "BG" : "FG"}{" "}
                              {container.container_type === "ROW" ? "Row" : "Pile"}{" "}
                              {container.container_number}
                            </option>
                          )),
                        ),
                      )}
                    </select>
                  </label>
                  {selectedContainerItem && (
                    <div className="map-range-grid">
                      <RangeField
                        label="Start"
                        value={selectedContainerItem.x}
                        max={100 - selectedContainerItem.width}
                        onChange={(value) =>
                          updateContainerRect(selectedContainerItem.id, {
                            ...selectedContainerItem,
                            x: value,
                          })}
                      />
                      <RangeField
                        label="Width"
                        value={selectedContainerItem.width}
                        min={4}
                        max={100 - selectedContainerItem.x}
                        onChange={(value) =>
                          updateContainerRect(selectedContainerItem.id, {
                            ...selectedContainerItem,
                            width: value,
                          })}
                      />
                      <RangeField
                        label="Vertical"
                        value={selectedContainerItem.y}
                        max={100 - selectedContainerItem.height}
                        onChange={(value) =>
                          updateContainerRect(selectedContainerItem.id, {
                            ...selectedContainerItem,
                            y: value,
                          })}
                      />
                      <RangeField
                        label="Height"
                        value={selectedContainerItem.height}
                        min={4}
                        max={100 - selectedContainerItem.y}
                        onChange={(value) =>
                          updateContainerRect(selectedContainerItem.id, {
                            ...selectedContainerItem,
                            height: value,
                          })}
                      />
                    </div>
                  )}
                </div>
                </div>}
              </aside>
            )}
            {rearranging && (
              <aside className={`map-rearrangement-panel ${
                rearrangementPanelMinimized ? "minimized" : ""
              }`}>
                <div className="map-rearrangement-heading">
                  <div>
                    <p className="eyebrow dark">Draft movement</p>
                    {activeMoveBook ? (
                      <h3>{activeMoveBook.title} <small>— {activeMoveBook.author}</small></h3>
                    ) : (
                      <h3>Select a book on the map</h3>
                    )}
                  </div>
                  <div className="map-workspace-actions">
                    {selectedMoveBookId !== null && !rearrangementPanelMinimized && (
                      <button className="text-button" onClick={() => resetRearrangement()}>
                        <RotateCcw size={15} /> Cancel draft
                      </button>
                    )}
                    <button
                      className="icon-button"
                      title={rearrangementPanelMinimized ? "Restore rearrangement" : "Minimize rearrangement"}
                      aria-label={rearrangementPanelMinimized ? "Restore rearrangement" : "Minimize rearrangement"}
                      onClick={() => setRearrangementPanelMinimized((current) => !current)}
                    >
                      {rearrangementPanelMinimized ? <ChevronUp /> : <ChevronDown />}
                    </button>
                  </div>
                </div>
                {!rearrangementPanelMinimized && <>
                <div className="map-move-modes">
                  <label>
                    Old position
                    <select
                      value={oldPositionMode}
                      disabled={
                        rearrangementSteps.length > 0 ||
                        newPositionMode === "SWAP"
                      }
                      onChange={(event) => setOldPositionMode(
                        event.target.value as OldPositionMode,
                      )}
                    >
                      <option value="COLLAPSE">Collapse</option>
                      <option value="LEAVE_GAP">Leave gap</option>
                    </select>
                  </label>
                  <label>
                    New position
                    <select
                      value={newPositionMode}
                      disabled={
                        rearrangementSteps.length > 0 &&
                        Boolean(rearrangementPreview?.complete)
                      }
                      onChange={(event) => {
                        const value = event.target.value as NewPositionMode;
                        setNewPositionMode(value);
                        if (value === "SWAP") setOldPositionMode("LEAVE_GAP");
                      }}
                    >
                      <option value="SQUEEZE">Squeeze</option>
                      <option value="SWAP">Swap</option>
                      <option value="CONTINUE">Continue</option>
                    </select>
                  </label>
                  <label className="checkbox-label map-release-space">
                    <input
                      type="checkbox"
                      checked={releaseShelfSpace}
                      disabled={rearrangementSteps.length > 0}
                      onChange={(event) => setReleaseShelfSpace(event.target.checked)}
                    />
                    Release shelf space if this move removes pages from its source container
                  </label>
                </div>
                {selectedMoveBookId === null ? (
                  <p className="map-rearrangement-help">
                    Tap a book, or choose one with the precise controls below.
                    Then tap its destination or drag the selected book there.
                  </p>
                ) : (
                  <>
                    <div className="map-current-position">
                      <MapPin size={16} />
                      <span><strong>Original position</strong>{selectedOriginalLocation}</span>
                    </div>
                    {selectedOriginalMoveBook?.status === "CURRENTLY_READING" && !selectedOriginalMoveBook.is_on_loan && (
                      <div className="map-reading-return-choice">
                        <div>
                          <strong>{selectedOriginalMoveBook.is_rereading
                            ? "Finish this re-reading and return the book as Read:"
                            : "Return this Reading book to the library as:"}</strong>
                          <span>
                            {pendingReadingDestination
                              ? "The destination is selected. Confirm the new status to preview the move."
                              : "Moving it back changes its reading status; choose before applying a destination."}
                          </span>
                        </div>
                        <div>
                          {!selectedOriginalMoveBook.is_rereading && (
                            <button
                              type="button"
                              className={readingExitStatus === "PENDING" ? "active" : ""}
                              disabled={rearrangementSteps.length > 0}
                              onClick={() => chooseReadingReturnStatus("PENDING")}
                            >
                              Pending
                            </button>
                          )}
                          <button
                            type="button"
                            className={readingExitStatus === "READ" ? "active" : ""}
                            disabled={rearrangementSteps.length > 0}
                            onClick={() => chooseReadingReturnStatus("READ")}
                          >
                            Read
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
                <div className="map-precise-move">
                  <label>
                    Book
                    <select
                      value={selectedMoveBookId ?? ""}
                      disabled={rearrangementSteps.length > 0}
                      onChange={(event) => {
                        const book = projectedBooks.find(
                          (item) => item.id === Number(event.target.value),
                        );
                        if (book) startMoveBook(book);
                        else resetRearrangement(true);
                      }}
                    >
                      <option value="">Choose book</option>
                      {[...projectedBooks]
                        .filter((book) => !book.is_on_loan)
                        .sort((first, second) => first.title.localeCompare(second.title))
                        .map((book) => (
                          <option key={book.id} value={book.id}>
                            {book.title} — {book.author}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Destination container
                    <select
                      value={preciseContainer}
                      onChange={(event) => setPreciseContainer(event.target.value)}
                    >
                      <option value="">Choose container</option>
                      {mapContainers.map((container) => (
                        <option key={container.id} value={container.id}>
                          {container.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Position
                    <input
                      type="number"
                      min="1"
                      value={precisePosition}
                      onChange={(event) => setPrecisePosition(Number(event.target.value))}
                    />
                  </label>
                  <button
                    className="outline-button"
                    disabled={
                      previewingMove ||
                      selectedMoveBookId === null ||
                      !preciseContainer ||
                      (
                        rearrangementSteps.length > 0 &&
                        Boolean(rearrangementPreview?.complete)
                      )
                    }
                    onClick={() => void addPhysicalDestination(
                      Number(preciseContainer),
                      precisePosition,
                    )}
                  >
                    <ArrowRightLeft size={15} /> Preview destination
                  </button>
                </div>
                {rearrangementPreview && (
                  <div className="map-movement-summary">
                    {movementGroups.map((group, groupIndex) => (
                      <section key={`move-${groupIndex}`}>
                        {movementGroups.length > 1 && (
                          <h4>Move {groupIndex + 1}</h4>
                        )}
                        <ul>
                          {group.map((line, lineIndex) => (
                            <li key={`${lineIndex}-${line}`}>{line}</li>
                          ))}
                        </ul>
                      </section>
                    ))}
                    {rearrangementPreview.gaps.map((gap) => {
                      const container = mapContainers.find(
                        (item) => item.id === gap.container_id,
                      );
                      return (
                        <p className="map-gap-warning" key={gap.container_id}>
                          Gap in {container?.label ?? `container ${gap.container_id}`}:
                          {" "}{gap.positions.join(", ")}
                        </p>
                      );
                    })}
                    {(rearrangementPreview.geometry_errors ?? []).map((message) => (
                      <p className="map-gap-warning" key={message}>{message}</p>
                    ))}
                    {!rearrangementPreview.complete && (
                      <p className="map-chain-warning">
                        Continue by choosing a destination for {activeMoveBook?.title}.
                      </p>
                    )}
                    {rearrangementPreview.complete &&
                      rearrangementPreview.placements.length === 0 &&
                      rearrangementPreview.gaps.length === 0 && (
                        <p className="map-no-net-change">
                          These moves cancel one another out: every book ends in
                          its original position, so there are no changes to
                          apply. Undo a step, add another move, or cancel the
                          draft.
                        </p>
                      )}
                  </div>
                )}
                <div className="map-rearrangement-actions">
                  {(rearrangementSteps.length > 0 || completedRearrangements.length > 0) && (
                    <button
                      className="text-button"
                      disabled={previewingMove || applyingMove}
                      onClick={() => void undoRearrangementStep()}
                    >
                      <RotateCcw size={15} /> Undo last step
                    </button>
                  )}
                  {rearrangementSteps.length > 0 && rearrangementPreview?.complete && (
                    <button
                      className="outline-button"
                      disabled={previewingMove || applyingMove}
                      onClick={startAnotherRearrangement}
                    >
                      <Plus size={15} /> Add another move
                    </button>
                  )}
                  <button
                    className="primary-button"
                    disabled={
                      previewingMove ||
                      applyingMove ||
                      rearrangementSteps.length === 0 ||
                      !rearrangementPreview?.valid_to_apply
                    }
                    onClick={() => void applyRearrangement()}
                  >
                    <Check size={15} /> {applyingMove ? "Applying…" : "Apply"}
                  </button>
                </div>
                </>}
              </aside>
            )}
            <div
              ref={roomRef}
              className={`map-room ${editingLayout ? "editing" : ""} ${
                rearranging ? "rearranging" : ""
              }`}
              onPointerDown={beginCameraGesture}
              onPointerMove={moveCameraGesture}
              onPointerUp={endCameraGesture}
              onPointerCancel={endCameraGesture}
              onWheel={zoomCameraWithWheel}
              onClickCapture={(event) => {
                if (!suppressNextMapClick.current) return;
                suppressNextMapClick.current = false;
                event.preventDefault();
                event.stopPropagation();
              }}
              onClick={(event) => {
                if (event.target === event.currentTarget && inspectionMode) {
                  clearInspectionSelection();
                }
              }}
            >
              <div
                ref={worldRef}
                className="map-world"
                style={{
                  width:
                    Math.max(1, viewportSize.height) *
                    LEGACY_MAP_ASPECT_RATIO *
                    camera.zoom,
                  height: Math.max(1, viewportSize.height) * camera.zoom,
                  transform: mapCameraTransform(camera),
                }}
                onClick={(event) => {
                  if (event.target === event.currentTarget && inspectionMode) {
                    clearInspectionSelection();
                  }
                }}
              >
              {(editingLayout || rearranging || displayMap.outside_books.length > 0) && (
                <section
                  className={`map-outside map-reading ${inspectedContainerId !== null ? "inspection-muted" : ""}`}
                  data-reading-target
                  role="button"
                  tabIndex={0}
                  title="Show currently reading books"
                  onClick={editingLayout
                    ? undefined
                    : rearranging
                      ? () => void addReadingDestination()
                      : inspectionMode
                        ? clearInspectionSelection
                        : onReadingFilter}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      if (!editingLayout) {
                        if (rearranging) void addReadingDestination();
                        else if (inspectionMode) clearInspectionSelection();
                        else onReadingFilter();
                      }
                    }
                  }}
                  style={{
                    left: `${activeLayout.outside.x}%`,
                    top: `${activeLayout.outside.y}%`,
                    width: `${activeLayout.outside.width}%`,
                    height: `${activeLayout.outside.height}%`,
                  }}
                >
                  <svg
                    className="map-reading-table"
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                    aria-hidden="true"
                  >
                    <path className="table-lamp-stem" d="M50 10 L50 4" />
                    <path className="table-lamp-shade" d="M43 10 Q50 3 57 10 Z" />
                    <rect className="table-surface" x="8" y="10" width="84" height="50" rx="7" />
                    <rect className="table-edge" x="14" y="56" width="72" height="4" rx="2" />
                    <path className="table-support" d="M46 60 L46 91 M54 60 L54 91" />
                    <ellipse className="table-base" cx="50" cy="93" rx="18" ry="5" />
                  </svg>
                  <div
                    className="map-reading-icons"
                    style={{
                      width: `${readingGrid.occupiedPercent * 0.76}%`,
                      height: `${readingGrid.occupiedPercent * 0.44}%`,
                      gridTemplateRows: `repeat(${readingGrid.rows}, minmax(0, 1fr))`,
                      gridTemplateColumns: `repeat(${readingGrid.columns}, minmax(0, 1fr))`,
                    }}
                  >
                    {displayMap.outside_books.map((book) => (
                      <span
                        key={book.id}
                        role={editingLayout ? undefined : "button"}
                        tabIndex={editingLayout ? -1 : 0}
                        className={
                          inspectedBook
                            ? book.id === inspectedBook.id
                              ? "focused"
                              : "muted"
                            : ""
                        }
                        title={`${book.title}${
                          colourScale.detail(book)
                            ? ` · ${colourScale.detail(book)}`
                            : ""
                        }`}
                        onClick={(event) => {
                          if (editingLayout) return;
                          event.stopPropagation();
                          if (rearranging) selectMoveBook(book);
                          else handleBookSelection(book);
                        }}
                        onDoubleClick={(event) => {
                          if (editingLayout || rearranging) return;
                          event.stopPropagation();
                          handleBookSelection(book, true);
                        }}
                        onPointerDown={(event) => {
                          if (rearranging) beginBookDrag(book, event);
                        }}
                        onKeyDown={(event) => {
                          if (
                            !editingLayout &&
                            (event.key === "Enter" || event.key === " ")
                          ) {
                            event.preventDefault();
                            event.stopPropagation();
                            if (rearranging) selectMoveBook(book);
                            else handleBookSelection(book);
                          }
                        }}
                      >
                        <svg
                          className="map-open-book"
                          viewBox="0 0 100 72"
                          preserveAspectRatio="xMidYMid meet"
                          aria-hidden="true"
                        >
                          <path
                            d="M50 62 C38 52 24 49 9 52 L9 11 C25 8 39 12 50 22 Z"
                            style={{ fill: inspectedBook?.id === book.id
                              ? "#287fbd"
                              : colourScale.colour(book) }}
                          />
                          <path
                            d="M50 62 C62 52 76 49 91 52 L91 11 C75 8 61 12 50 22 Z"
                            style={{ fill: inspectedBook?.id === book.id
                              ? "#287fbd"
                              : colourScale.colour(book) }}
                          />
                          <path className="open-book-detail" d="M50 22 L50 62 M15 17 C28 15 39 19 46 25 M85 17 C72 15 61 19 54 25" />
                        </svg>
                      </span>
                    ))}
                  </div>
                  {editingLayout && (
                    <>
                      <button
                        type="button"
                        className="map-direct-handle move"
                        title="Drag reading area"
                        aria-label="Drag reading area"
                        onPointerDown={(event) =>
                          beginRoomRectInteraction(
                            event,
                            activeLayout.outside,
                            "move",
                            (rect) =>
                              setDraft((current) => ({ ...current, outside: rect })),
                          )}
                      >
                        ↕
                      </button>
                      <button
                        type="button"
                        className="map-direct-handle resize"
                        title="Resize reading area"
                        aria-label="Resize reading area"
                        onPointerDown={(event) =>
                          beginRoomRectInteraction(
                            event,
                            activeLayout.outside,
                            "resize",
                            (rect) =>
                              setDraft((current) => ({ ...current, outside: rect })),
                          )}
                      >
                        ↘
                      </button>
                    </>
                  )}
                </section>
              )}
              {(editingLayout || rearranging || displayMap.loaned_books.length > 0) && (
                <section
                  className={`map-outside map-loaned ${inspectedContainerId !== null ? "inspection-muted" : ""}`}
                  role="button"
                  tabIndex={0}
                  title="Show books currently on loan"
                  onClick={editingLayout || rearranging
                    ? undefined
                    : inspectionMode
                      ? clearInspectionSelection
                      : onLoanFilter}
                  onKeyDown={(event) => {
                    if (!editingLayout && !rearranging && (event.key === "Enter" || event.key === " ")) {
                      event.preventDefault();
                      if (inspectionMode) clearInspectionSelection();
                      else onLoanFilter();
                    }
                  }}
                  style={{
                    left: `${activeLayout.loaned.x}%`,
                    top: `${activeLayout.loaned.y}%`,
                    width: `${activeLayout.loaned.width}%`,
                    height: `${activeLayout.loaned.height}%`,
                  }}
                >
                  <svg
                    className="map-loan-cloud"
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                    aria-hidden="true"
                  >
                    <path d="M12 94 C4 94 1 84 7 77 C1 67 4 55 13 51 C8 38 16 27 28 28 C31 14 45 8 56 19 C66 10 82 17 83 31 C96 31 102 44 96 55 C103 65 99 78 90 82 C87 94 73 98 63 92 C52 101 38 97 33 90 C24 98 16 98 12 94 Z" />
                  </svg>
                  <div className="map-outside-books map-loaned-books">
                    {loanedBookGroups.map((group, groupIndex) => (
                      <div
                        className="map-loaned-row"
                        key={`loan-row-${groupIndex}`}
                        style={{
                          flexBasis: `${Math.min(
                            62,
                            90 / Math.max(1, loanedBookGroups.length),
                          )}%`,
                        }}
                      >
                      {group.map(({ book, share }) => (
                      <span
                        key={book.id}
                        role={editingLayout ? undefined : "button"}
                        tabIndex={editingLayout ? -1 : 0}
                        className={inspectedBook ? book.id === inspectedBook.id ? "focused" : "muted" : ""}
                        title={`${book.title} · On loan to ${book.loaned_to ?? "unknown"}`}
                        onClick={(event) => {
                          if (editingLayout) return;
                          event.stopPropagation();
                          if (rearranging) selectMoveBook(book); else handleBookSelection(book);
                        }}
                        onDoubleClick={(event) => {
                          if (editingLayout || rearranging) return;
                          event.stopPropagation();
                          handleBookSelection(book, true);
                        }}
                        onPointerDown={(event) => { if (rearranging) beginBookDrag(book, event); }}
                        style={{ width: `${share * 100}%` }}
                      ><i style={{ background: inspectedBook?.id === book.id ? "#287fbd" : colourScale.colour(book) }} /></span>
                      ))}
                      </div>
                    ))}
                  </div>
                  {editingLayout && <>
                    <button type="button" className="map-direct-handle move" title="Drag on-loan area" onPointerDown={(event) => beginRoomRectInteraction(event, activeLayout.loaned, "move", (rect) => setDraft((current) => ({ ...current, loaned: rect })))}>↕</button>
                    <button type="button" className="map-direct-handle resize" title="Resize on-loan area" onPointerDown={(event) => beginRoomRectInteraction(event, activeLayout.loaned, "resize", (rect) => setDraft((current) => ({ ...current, loaned: rect })))}>↘</button>
                  </>}
                </section>
              )}
              {displayMap.bookcases.map((bookcase) => (
                <MapBookcaseGraphic
                  key={bookcase.id}
                  bookcase={bookcase}
                  rect={bookcaseRects.get(bookcase.id) ?? {
                    x: 2, y: 8, width: 28, height: 72,
                  }}
                  shelfLayout={shelfWeights}
                  containerLayout={containerRects}
                  inspectedContainerId={inspectedContainerId}
                  focusedBookId={inspectedBookId}
                  cataloguePageMean={cataloguePageMean}
                  colourScale={colourScale}
                  editing={editingLayout}
                  rearranging={rearranging}
                  activeBookId={activeMoveBookId}
                  reservedBooksByContainer={reservedBooksByContainer}
                  onEditBookcase={() => setSelectedBookcase(String(bookcase.id))}
                  onEditShelf={(shelf) => setSelectedShelf(String(shelf.id))}
                  onEditContainer={(container) =>
                    setSelectedContainer(String(container.id))}
                  onContainerLayoutChange={updateContainerRect}
                  onShelfWeightsChange={updateShelfWeights}
                  onBookSelect={(book) => handleBookSelection(book)}
                  onBookOpen={(book) => handleBookSelection(book, true)}
                  onRearrangeBookSelect={selectMoveBook}
                  onDestination={(containerId, position) =>
                    void addPhysicalDestination(containerId, position)}
                  onBookPointerDown={beginBookDrag}
                  onRectPointerDown={(event, mode) => {
                    setSelectedBookcase(String(bookcase.id));
                    const rect = bookcaseRects.get(bookcase.id);
                    if (!rect) return;
                    beginRoomRectInteraction(
                      event,
                      rect,
                      mode,
                      (nextRect) =>
                        setDraft((current) => ({
                          ...current,
                          bookcases: current.bookcases.map((item) =>
                            item.id === bookcase.id
                              ? { ...item, ...nextRect }
                              : item,
                          ),
                        })),
                    );
                  }}
                  onBookcase={() => {
                    if (inspectionMode) clearInspectionSelection();
                    else onFilter(bookcase.id);
                  }}
                  onShelf={(shelf) => {
                    if (inspectionMode) clearInspectionSelection();
                    else onFilter(bookcase.id, shelf.id);
                  }}
                  onContainer={(shelf, container) => {
                    if (inspectionMode === "container") inspectContainer(container.id);
                    else if (inspectionMode === "book") clearInspectionSelection();
                    else onFilter(bookcase.id, shelf.id, container.id);
                  }}
                  onContainerOpen={(shelf, container) => {
                    if (inspectionMode === "container") inspectContainer(container.id, true);
                    else if (inspectionMode === "book") clearInspectionSelection();
                    else onFilter(bookcase.id, shelf.id, container.id);
                  }}
                />
              ))}
              </div>
              <div
                className={`map-camera-controls ${cameraControlsExpanded ? "expanded" : ""}`}
                aria-label="Map camera controls"
              >
                <button
                  type="button"
                  className={`map-camera-toggle ${cameraControlsExpanded ? "active" : ""}`}
                  aria-label={cameraControlsExpanded
                    ? "Hide map camera controls"
                    : "Show map camera controls"}
                  aria-expanded={cameraControlsExpanded}
                  title={cameraControlsExpanded
                    ? "Hide camera controls"
                    : "Show camera controls"}
                  onClick={() => setCameraControlsExpanded((current) => !current)}
                >
                  <Camera />
                </button>
                <div className="map-zoom-controls">
                  <button
                    type="button"
                    className="map-camera-button"
                    aria-label="Zoom map in"
                    title="Zoom in"
                    {...cameraControlHandlers("zoom-in")}
                  ><ZoomIn /></button>
                  <span aria-live="polite">{Math.round(camera.zoom * 100)}%</span>
                  <button
                    type="button"
                    className="map-camera-button"
                    aria-label="Zoom map out"
                    title="Zoom out"
                    {...cameraControlHandlers("zoom-out")}
                  ><ZoomOut /></button>
                </div>
                <div className="map-pan-controls">
                  <button
                    type="button"
                    className="map-camera-button up"
                    aria-label="Pan map up"
                    title="Pan up"
                    {...cameraControlHandlers("up")}
                  ><ArrowUp /></button>
                  <button
                    type="button"
                    className="map-camera-button left"
                    aria-label="Pan map left"
                    title="Pan left"
                    {...cameraControlHandlers("left")}
                  ><ArrowLeft /></button>
                  <button
                    type="button"
                    className="map-camera-button reset"
                    aria-label="Reset map view"
                    title="Reset view"
                    onClick={resetMapView}
                  ><RotateCcw /></button>
                  <button
                    type="button"
                    className="map-camera-button right"
                    aria-label="Pan map right"
                    title="Pan right"
                    {...cameraControlHandlers("right")}
                  ><ArrowRight /></button>
                  <button
                    type="button"
                    className="map-camera-button down"
                    aria-label="Pan map down"
                    title="Pan down"
                    {...cameraControlHandlers("down")}
                  ><ArrowDown /></button>
                </div>
              </div>
            </div>
            {(inspectedBook || inspectedContainerContext) && !inspectorOpen && (
              <div className="map-selection-bar" role="status">
                <span>
                  <strong>
                    {inspectedContainerContext
                      ? `${inspectedContainerContext.container.book_count} books selected`
                      : inspectedBook?.title}
                  </strong>
                  <small>
                    {inspectedContainerContext
                      ? `${inspectedContainerContext.bookcase.name} · Shelf ${inspectedContainerContext.shelf.shelf_number}`
                      : inspectedBook
                        ? displayedAuthor(inspectedBook)
                        : ""}
                  </small>
                </span>
                <div>
                  <button type="button" onClick={frameInspectionSelection}>
                    <Focus size={15} /> Frame
                  </button>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => setInspectorOpen(true)}
                  >
                    <Info size={15} />
                    {inspectedContainerContext ? "Show books" : "Show book"}
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="Clear map selection"
                    title="Clear selection"
                    onClick={clearInspectionSelection}
                  >
                    <X size={17} />
                  </button>
                </div>
              </div>
            )}
            {inspectorOpen && (inspectedBook || inspectedContainerContext) && (
              <aside
                className={`map-inspector-drawer ${inspectorCompleteBook ? "complete" : ""}`}
                aria-label="Map selection details"
              >
                <header>
                  <div>
                    <p className="eyebrow">
                      {inspectorCompleteBook
                        ? "Complete catalogue record"
                        : inspectedContainerContext
                          ? "Container inspection"
                          : "Book inspection"}
                    </p>
                    <h3>
                      {inspectorCompleteBook
                        ? inspectorCompleteBook.title
                        : inspectedContainerContext
                        ? `${inspectedContainerContext.bookcase.name} · Shelf ${inspectedContainerContext.shelf.shelf_number}`
                        : inspectedBook?.title}
                    </h3>
                  </div>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={inspectorCompleteBook
                      ? "Back to compact inspector"
                      : "Close inspector"}
                    onClick={() => {
                      if (inspectorCompleteBook) {
                        setInspectorCompleteBook(null);
                        setInspectorDetailsError("");
                      } else {
                        clearInspectionSelection();
                      }
                    }}
                  >
                    <X size={18} />
                  </button>
                </header>
                <div className={`map-inspector-content ${inspectorCompleteBook ? "complete" : ""}`}>
                  {inspectorDetailsLoading ? (
                    <p className="map-inspector-empty"><LoaderCircle className="spin" /> Loading complete information…</p>
                  ) : inspectorDetailsError ? (
                    <div className="form-error map-inspector-error">{inspectorDetailsError}</div>
                  ) : inspectorCompleteBook ? (
                    <MapCompleteBookInformation book={inspectorCompleteBook} />
                  ) : inspectedContainerContext ? (
                    inspectedContainerContext.container.books.length > 0 ? (
                      [...inspectedContainerContext.container.books]
                        .sort((first, second) =>
                          (first.position ?? 0) - (second.position ?? 0))
                        .map((book) => (
                          <MapInspectorBookRow
                            key={book.id}
                            book={book}
                            selected={book.id === inspectedBookId}
                            onSelect={() => {
                              setInspectedBookId((current) =>
                                current === book.id ? null : book.id);
                              setInspectorCompleteBook(null);
                              setInspectorDetailsError("");
                            }}
                          />
                        ))
                    ) : (
                      <p className="map-inspector-empty">This container is empty.</p>
                    )
                  ) : inspectedBook ? (
                    <MapInspectorBookRow
                      book={inspectedBook}
                      selected
                      onSelect={clearInspectionSelection}
                    />
                  ) : null}
                </div>
                <footer>
                  {inspectorCompleteBook ? (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          setInspectorCompleteBook(null);
                          setInspectorDetailsError("");
                        }}
                      >
                        <ArrowLeft size={15} />
                        {inspectedContainerContext
                          ? "Back to container inspection"
                          : "Back to book inspection"}
                      </button>
                      <button
                        type="button"
                        className="primary-button"
                        onClick={() => onBookFilter(inspectorCompleteBook)}
                      >
                        <ExternalLink size={15} /> Open this book in catalogue
                      </button>
                    </>
                  ) : (
                    <>
                      <button type="button" onClick={frameInspectionSelection}>
                        <Focus size={15} /> Frame selection
                      </button>
                      <button
                        type="button"
                        disabled={inspectedBookId === null || inspectorDetailsLoading}
                        title={inspectedBookId === null ? "Select a book first" : undefined}
                        onClick={() => {
                          if (inspectedBookId !== null) {
                            void showCompleteInspectorBook(inspectedBookId);
                          }
                        }}
                      >
                        <Info size={15} /> Show book complete information
                      </button>
                      <button
                        type="button"
                        className="primary-button"
                        onClick={() => {
                          if (inspectedContainerContext) {
                            onFilter(
                              inspectedContainerContext.bookcase.id,
                              inspectedContainerContext.shelf.id,
                              inspectedContainerContext.container.id,
                            );
                          } else if (inspectedBook) {
                            onBookFilter(inspectedBook);
                          }
                        }}
                      >
                        <ExternalLink size={15} /> Open filtered catalogue
                      </button>
                    </>
                  )}
                </footer>
              </aside>
            )}
            {dragGhost && (
              <div
                className="map-drag-ghost"
                style={{ left: dragGhost.x + 14, top: dragGhost.y + 14 }}
              >
                <BookOpen size={15} /> {dragGhost.title}
              </div>
            )}
          </>
        )}
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
              <h3>Loan history as CSV</h3>
              <p>One row per active or returned loan, including borrower text, dates, and notes.</p>
              <a className="outline-button" href={api.downloadUrl("/exports/loans.csv")} download>
                <Download size={17} /> Export loan history
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
          <article>
            <div className="data-option-icon csv"><FileSpreadsheet /></div>
            <div>
              <h3>Reading history as CSV</h3>
              <p>
                One row per reading session, including re-reads, dates, state,
                duration, and the book identifiers needed for analysis.
              </p>
              <a
                className="outline-button"
                href={api.downloadUrl("/exports/reading-sessions.csv")}
                download
              >
                <Download size={17} /> Export reading history
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
