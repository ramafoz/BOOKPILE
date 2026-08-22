export type BookStatus = "PENDING" | "CURRENTLY_READING" | "READ";
export type ContainerType = "ROW" | "PILE";
export type Layer = "BACKGROUND" | "FOREGROUND";
export type FictionCategory = "FICTION" | "NON_FICTION";
export type Binding = "HARDCOVER" | "PAPERBACK" | "FLEXIBOUND" | "SPIRAL" | "STAPLED" | "OTHER";
export type PublicationType = "CONVENTIONAL_BOOK" | "COMIC_GRAPHIC_NOVEL" | "ATLAS" | "REFERENCE" | "ART_PHOTOGRAPHY_ILLUSTRATED" | "MAGAZINE_PERIODICAL" | "OTHER";

export interface Container {
  id: number;
  shelf_id: number;
  container_type: ContainerType;
  layer: Layer;
  container_number: number;
  book_count: number;
}

export interface Shelf {
  id: number;
  bookcase_id: number;
  shelf_number: number;
  containers: Container[];
}

export interface Bookcase {
  id: number;
  name: string;
  description: string | null;
  shelves: Shelf[];
}

export interface MapBook {
  id: number;
  title: string;
  author: string;
  has_multiple_authors: boolean;
  structured_authors: string[];
  cover_filename: string | null;
  isbn_10: string | null;
  isbn_13: string | null;
  subtitle: string | null;
  page_count: number | null;
  publisher: string | null;
  current_ed_year: number | null;
  original_publication_year: number | null;
  language: string | null;
  edition_number: number | null;
  fiction_category: FictionCategory | null;
  binding: Binding | null;
  publication_type: PublicationType | null;
  genre_text: string | null;
  series_name: string | null;
  series_volume: string | null;
  status: BookStatus;
  is_rereading: boolean;
  is_on_loan: boolean;
  loaned_to: string | null;
  container_id: number | null;
  position: number | null;
  acquisition_date: string | null;
  reading_started_date: string | null;
  read_date: string | null;
}

export interface MapContainer extends Container {
  books: MapBook[];
  status_counts: {
    pending: number;
    reading: number;
    read: number;
  };
}

export interface MapShelf {
  id: number;
  bookcase_id: number;
  shelf_number: number;
  book_count: number;
  containers: MapContainer[];
}

export interface MapBookcase {
  id: number;
  name: string;
  description: string | null;
  book_count: number;
  shelves: MapShelf[];
}

export interface LibraryMapData {
  bookcases: MapBookcase[];
  outside_books: MapBook[];
  loaned_books: MapBook[];
  effective_page_mean: number;
  layout: VisualLayout;
}

export interface VisualRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface VisualLayout {
  bookcases: Array<VisualRect & { id: number }>;
  shelves: Array<{ id: number; height_weight: number }>;
  containers: Array<VisualRect & {
    id: number;
    row_anchor: "LEFT" | "RIGHT";
    pile_support_kind: "SHELF" | "ROW" | null;
    pile_support_container_id: number | null;
  }>;
  outside: VisualRect;
  loaned: VisualRect;
}

export interface Loan {
  id: number;
  book_id: number;
  loaned_to: string;
  notes: string | null;
  state: "ACTIVE" | "RETURNED";
  loaned_date: string | null;
  expected_return_date: string | null;
  returned_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface LoanPayload {
  loaned_to: string;
  loaned_date: string | null;
  expected_return_date: string | null;
  notes: string | null;
}

export interface Book {
  id: number;
  title: string;
  author: string;
  has_multiple_authors: boolean;
  structured_authors: string[];
  isbn_10: string | null;
  isbn_13: string | null;
  subtitle: string | null;
  page_count: number | null;
  publisher: string | null;
  current_ed_year: number | null;
  original_publication_year: number | null;
  language: string | null;
  edition_number: number | null;
  fiction_category: FictionCategory | null;
  binding: Binding | null;
  publication_type: PublicationType | null;
  genre_text: string | null;
  series_name: string | null;
  series_volume: string | null;
  status: BookStatus;
  goodreads_url: string | null;
  notes: string | null;
  acquisition_date: string | null;
  reading_started_date: string | null;
  read_date: string | null;
  is_read_date_unknown: boolean;
  is_original_collection: boolean;
  container_id: number | null;
  position: number | null;
  created_at: string;
  updated_at: string;
  cover_filename: string | null;
  location_label: string | null;
  bookcase_name: string | null;
  shelf_number: number | null;
  container_type: ContainerType | null;
  layer: Layer | null;
  container_number: number | null;
  reading_sessions: ReadingSession[];
  reading_session_count: number;
  is_rereading: boolean;
  loans: Loan[];
  loan_count: number;
  active_loan: Loan | null;
  is_on_loan: boolean;
  return_location_label: string | null;
}

export interface ReadingSession {
  id: number;
  book_id: number;
  session_number: number;
  state: "ACTIVE" | "COMPLETED";
  started_date: string | null;
  finished_date: string | null;
  dates_unknown: boolean;
  created_at: string;
  updated_at: string;
}

export interface Stats {
  total: number;
  pending: number;
  currently_reading: number;
  currently_rereading: number;
  read: number;
}

export interface DurationStatistic {
  average_days: number | null;
  median_days: number | null;
  sample_size: number;
  excluded: number;
}

export interface CollectionStatistic {
  total: number;
  pending: number;
  reading: number;
  read: number;
}

export interface MetadataOptions {
  languages: string[];
  genres: string[];
  publishers: string[];
  series_names: string[];
  fiction_categories: FictionCategory[];
  bindings: Binding[];
  publication_types: PublicationType[];
}

export interface MetadataFilters {
  isbn: string;
  languages: string[];
  genres: string[];
  publishers: string[];
  fictionCategories: FictionCategory[];
  bindings: Binding[];
  publicationTypes: PublicationType[];
  seriesNames: string[];
  seriesState: "ANY" | "YES" | "NO";
  authorStructure: "ANY" | "SINGLE" | "MULTIPLE";
  readingActivity: "ANY" | "INITIAL" | "REREADING";
  pageMin: string;
  pageMax: string;
  publicationYearField: "current_ed_year" | "original_publication_year";
  publicationYearMin: string;
  publicationYearMax: string;
}

export interface CatalogueStatistics {
  selected_year: number | null;
  available_years: number[];
  filtered_book_count: number;
  yearly: Array<{ year: number; acquired: number; read: number; pages_read: number }>;
  monthly: Array<{ month: number; acquired: number; read: number; pages_read: number }>;
  reading_rate: {
    total_pages: number;
    pages_per_week: number | null;
    pages_per_month: number | null;
    sample_size: number;
    excluded: number;
    single_day_estimates: number;
    average_per_book: number | null;
    median_per_book: number | null;
    per_book_sample_size: number;
    per_book_excluded: number;
    per_book_estimates: number;
    per_book: Array<{
      id: number;
      title: string;
      author: string;
      page_count: number;
      reading_days: number;
      pages_per_day: number;
      read_date: string;
      estimated_start: boolean;
      session_number: number;
    }>;
  };
  reading_sessions: {
    completed: number;
    unique_books: number;
    rereads: number;
  };
  loans: {
    active: number;
    overdue: number;
    completed: number;
    unknown_loan_dates: number;
    by_year: Array<{ year: number; count: number }>;
    most_loaned: Array<{
      book_id: number;
      title: string;
      author: string;
      loan_count: number;
    }>;
  };
  pending_duration: DurationStatistic;
  reading_duration: DurationStatistic;
  original_collection: CollectionStatistic;
  later_acquisitions: CollectionStatistic;
}

export interface ReadingSuggestion {
  book: Book;
  waiting_days: number | null;
}

export interface CatalogueMatch {
  book_id: number;
  title: string;
  author: string;
  status: BookStatus;
  cover_filename: string | null;
  location_label: string | null;
  match_class: "strong" | "possible";
  reason: string;
}

export interface BibliographicCandidate {
  source: string;
  source_record_id: string | null;
  identifiers: {
    isbn_10: string | null;
    isbn_13: string | null;
  };
  title: string;
  subtitle: string | null;
  authors: string[];
  publisher: string | null;
  current_ed_year: number | null;
  original_publication_year: number | null;
  page_count: number | null;
  subjects: string[];
  language: string | null;
  edition_number: number | null;
  fiction_category: FictionCategory | null;
  binding: Binding | null;
  publication_type: PublicationType | null;
  genre_text: string | null;
  series_name: string | null;
  series_volume: string | null;
  confidence_or_match_notes: string | null;
  catalogue_matches: CatalogueMatch[];
}

export interface ISBNLookupResult {
  isbn: string;
  candidates: BibliographicCandidate[];
  catalogue_matches: CatalogueMatch[];
}

export type OldPositionMode = "COLLAPSE" | "LEAVE_GAP";
export type NewPositionMode = "SQUEEZE" | "SWAP" | "CONTINUE";

export interface RearrangementStep {
  destination_kind?: "PHYSICAL" | "READING";
  container_id?: number | null;
  position?: number | null;
  new_position_mode?: NewPositionMode;
  reading_exit_status?: "PENDING" | "READ" | null;
}

export interface RearrangementOperation {
  book_id: number;
  old_position_mode: OldPositionMode;
  steps: RearrangementStep[];
}

export interface RearrangementRequest extends RearrangementOperation {
  completed_operations?: RearrangementOperation[];
}

export interface RearrangementResult {
  revision: string;
  valid_to_apply: boolean;
  complete: boolean;
  effective_old_position_mode: OldPositionMode;
  next_active_book_id: number | null;
  placements: Array<{
    book_id: number;
    container_id: number | null;
    position: number | null;
    status: BookStatus;
  }>;
  gaps: Array<{ container_id: number; positions: number[] }>;
  movement_log: string[];
  movement_groups?: string[][];
  warnings: string[];
}

export interface BookPayload {
  title: string;
  author: string;
  has_multiple_authors: boolean;
  structured_authors: string[];
  isbn_10: string | null;
  isbn_13: string | null;
  subtitle: string | null;
  page_count: number | null;
  publisher: string | null;
  current_ed_year: number | null;
  original_publication_year: number | null;
  language: string | null;
  edition_number: number | null;
  fiction_category: FictionCategory | null;
  binding: Binding | null;
  publication_type: PublicationType | null;
  genre_text: string | null;
  series_name: string | null;
  series_volume: string | null;
  status: BookStatus;
  goodreads_url: string | null;
  notes: string | null;
  acquisition_date: string | null;
  reading_started_date: string | null;
  read_date: string | null;
  is_read_date_unknown: boolean;
  is_original_collection: boolean;
  container_id: number | null;
  position: number | null;
  current_loan?: LoanPayload | null;
}
