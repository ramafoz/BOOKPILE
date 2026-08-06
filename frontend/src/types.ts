export type BookStatus = "PENDING" | "CURRENTLY_READING" | "READ";
export type ContainerType = "ROW" | "PILE";
export type Layer = "BACKGROUND" | "FOREGROUND";

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
  status: BookStatus;
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
  containers: Array<VisualRect & { id: number }>;
  outside: VisualRect;
}

export interface Book {
  id: number;
  title: string;
  author: string;
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
}

export interface Stats {
  total: number;
  pending: number;
  currently_reading: number;
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

export interface CatalogueStatistics {
  selected_year: number | null;
  available_years: number[];
  yearly: Array<{ year: number; acquired: number; read: number }>;
  monthly: Array<{ month: number; acquired: number; read: number }>;
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
  published_date: string | null;
  page_count: number | null;
  subjects: string[];
  language: string | null;
  edition: string | null;
  genres: string[];
  category: string | null;
  format: string | null;
  confidence_or_match_notes: string | null;
  catalogue_matches: CatalogueMatch[];
}

export interface ISBNLookupResult {
  isbn: string;
  candidates: BibliographicCandidate[];
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
}
