import type {
  Book,
  BookPayload,
  BookStatus,
  Bookcase,
  ContainerType,
  Layer,
  Stats,
  CatalogueStatistics,
  ReadingSuggestion,
  RearrangementRequest,
  RearrangementResult,
  LibraryMapData,
  ISBNLookupResult,
  CatalogueMatch,
  VisualLayout,
  MetadataFilters,
  MetadataOptions,
} from "./types";

export interface RestoreInspection {
  token: string;
  created_at: string;
  schema_version: number;
  counts: {
    bookcases: number;
    shelves: number;
    containers: number;
    books: number;
    covers: number;
  };
  filename: string;
  validated_at: string;
}

export interface BookQuery {
  bookId: string;
  status: string;
  search: string;
  sortBy: string;
  sortOrder: "asc" | "desc";
  bookcaseId: string;
  shelfId: string;
  containerId: string;
  dateField: string;
  dateFrom: string;
  dateTo: string;
  includeUnknownSelectedDates: boolean;
  includeUnknownSortDates: boolean;
  quickView: string;
  catalogueCheck: string;
  metadata: MetadataFilters;
}

const API_URL = import.meta.env.VITE_API_URL ?? "/api";

function appendMetadataFilters(params: URLSearchParams, filters: MetadataFilters) {
  const isbn = filters.isbn.replace(/[^0-9Xx]/g, "");
  if (isbn.length === 10 || isbn.length === 13) params.set("isbn", isbn);
  filters.languages.forEach((value) => params.append("language", value));
  filters.genres.forEach((value) => params.append("genre", value));
  filters.publishers.forEach((value) => params.append("publisher", value));
  filters.fictionCategories.forEach((value) => params.append("fiction_category", value));
  filters.bindings.forEach((value) => params.append("binding", value));
  filters.publicationTypes.forEach((value) => params.append("publication_type", value));
  filters.seriesNames.forEach((value) => params.append("series_name", value));
  if (filters.seriesState !== "ANY") params.set("series_state", filters.seriesState);
  if (filters.pageMin) params.set("page_min", filters.pageMin);
  if (filters.pageMax) params.set("page_max", filters.pageMax);
  const validYearMin = /^\d{4}$/.test(filters.publicationYearMin);
  const validYearMax = /^\d{4}$/.test(filters.publicationYearMax);
  if (validYearMin || validYearMax) {
    params.set("publication_year_field", filters.publicationYearField);
    if (validYearMin) {
      params.set("publication_year_min", filters.publicationYearMin);
    }
    if (validYearMax) {
      params.set("publication_year_max", filters.publicationYearMax);
    }
  }
}

export class ApiError extends Error {
  code?: string;
  detail?: Record<string, unknown>;

  constructor(message: string, detail?: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.detail = detail;
    this.code = typeof detail?.code === "string" ? detail.code : undefined;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData;
  const response = await fetch(`${API_URL}${path}`, {
    headers: isFormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail =
      error.detail && typeof error.detail === "object"
        ? error.detail as Record<string, unknown>
        : undefined;
    const message =
      typeof error.detail === "string"
        ? error.detail
        : typeof detail?.message === "string"
          ? detail.message
          : "Something went wrong";
    throw new ApiError(message, detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  downloadUrl: (path: string) => `${API_URL}${path}`,
  coverUrl: (filename: string) => `${API_URL}/covers/${filename}`,
  books: (query: BookQuery) => {
    const params = new URLSearchParams();
    if (query.bookId) params.set("book_id", query.bookId);
    if (query.status !== "ALL") params.set("status", query.status);
    if (query.search.trim()) params.set("search", query.search.trim());
    params.set("sort_by", query.sortBy);
    params.set("sort_order", query.sortOrder);
    if (query.bookcaseId) params.set("bookcase_id", query.bookcaseId);
    if (query.shelfId) params.set("shelf_id", query.shelfId);
    if (query.containerId) params.set("container_id", query.containerId);
    if (query.dateFrom || query.dateTo) {
      params.set("date_field", query.dateField);
      if (query.dateFrom) params.set("date_from", query.dateFrom);
      if (query.dateTo) params.set("date_to", query.dateTo);
    }
    if (query.includeUnknownSelectedDates) {
      params.set("include_unknown_dates", "true");
    }
    if (query.includeUnknownSortDates) {
      params.set("include_unknown_sort_dates", "true");
    }
    if (query.quickView) params.set("quick_view", query.quickView);
    if (query.catalogueCheck) params.set("catalogue_check", query.catalogueCheck);
    appendMetadataFilters(params, query.metadata);
    return request<Book[]>(`/books?${params}`);
  },
  stats: () => request<Stats>("/stats"),
  metadataOptions: () => request<MetadataOptions>("/metadata-options"),
  statistics: (year: number | null, metadata: MetadataFilters) => {
    const params = new URLSearchParams();
    if (year !== null) params.set("year", String(year));
    appendMetadataFilters(params, metadata);
    return request<CatalogueStatistics>(`/statistics?${params}`);
  },
  readingSuggestion: (
    mode: "random" | "oldest" | "waiting",
    minimumDays: number,
    excludeIds: number[],
  ) => {
    const params = new URLSearchParams({
      mode,
      minimum_days: String(minimumDays),
    });
    excludeIds.forEach((id) => params.append("exclude_id", String(id)));
    return request<ReadingSuggestion>(`/suggestions?${params}`);
  },
  library: () => request<Bookcase[]>("/library"),
  libraryMap: () => request<LibraryMapData>("/library-map"),
  lookupIsbn: (isbn: string) => {
    const params = new URLSearchParams({ isbn });
    return request<ISBNLookupResult>(`/bibliography/isbn?${params}`);
  },
  matchBibliography: (title: string, authors: string[]) =>
    request<CatalogueMatch[]>("/bibliography/matches", {
      method: "POST",
      body: JSON.stringify({ title, authors }),
    }),
  previewRearrangement: (payload: RearrangementRequest) =>
    request<RearrangementResult>("/rearrangements/preview", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  applyRearrangement: (
    payload: RearrangementRequest,
    revision: string,
  ) =>
    request<RearrangementResult>("/rearrangements/apply", {
      method: "POST",
      body: JSON.stringify({ ...payload, revision }),
    }),
  updateVisualLayout: (layout: VisualLayout) =>
    request<VisualLayout>("/visual-layout", {
      method: "PUT",
      body: JSON.stringify(layout),
    }),
  createBook: (
    book: BookPayload,
    shiftExisting = false,
    shiftDirection: "UP" | "DOWN" = "UP",
  ) =>
    request<Book>("/books", {
      method: "POST",
      body: JSON.stringify({
        ...book,
        shift_existing: shiftExisting,
        shift_direction: shiftDirection,
      }),
    }),
  updateBook: (id: number, book: BookPayload) =>
    request<Book>(`/books/${id}`, {
      method: "PATCH",
      body: JSON.stringify(book),
    }),
  updateBookStatus: (id: number, status: BookStatus) =>
    request<Book>(`/books/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  deleteBook: (id: number) =>
    request<void>(`/books/${id}`, { method: "DELETE" }),
  uploadCover: (id: number, cover: File) => {
    const body = new FormData();
    body.append("cover", cover);
    return request<Book>(`/books/${id}/cover`, { method: "POST", body });
  },
  deleteCover: (id: number) =>
    request<Book>(`/books/${id}/cover`, { method: "DELETE" }),
  moveBook: (id: number, containerId: number, position: number) =>
    request<Book>(`/books/${id}/move`, {
      method: "POST",
      body: JSON.stringify({
        container_id: containerId,
        position,
        swap_if_occupied: true,
      }),
    }),
  createBookcase: (name: string, description: string) =>
    request("/bookcases", {
      method: "POST",
      body: JSON.stringify({ name, description: description || null }),
    }),
  updateBookcase: (id: number, name: string, description: string) =>
    request(`/bookcases/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name, description: description || null }),
    }),
  createShelf: (bookcaseId: number, shelfNumber: number) =>
    request("/shelves", {
      method: "POST",
      body: JSON.stringify({
        bookcase_id: bookcaseId,
        shelf_number: shelfNumber,
      }),
    }),
  updateShelf: (id: number, shelfNumber: number) =>
    request(`/shelves/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ shelf_number: shelfNumber }),
    }),
  createContainer: (
    shelfId: number,
    containerType: ContainerType,
    layer: Layer,
    containerNumber: number,
  ) =>
    request("/containers", {
      method: "POST",
      body: JSON.stringify({
        shelf_id: shelfId,
        container_type: containerType,
        layer,
        container_number: containerNumber,
      }),
    }),
  updateContainer: (id: number, containerNumber: number) =>
    request(`/containers/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ container_number: containerNumber }),
    }),
  deleteShelf: (id: number) =>
    request<void>(`/shelves/${id}`, { method: "DELETE" }),
  deleteContainer: (id: number) =>
    request<void>(`/containers/${id}`, { method: "DELETE" }),
  inspectRestore: (backup: File) => {
    const body = new FormData();
    body.append("backup", backup);
    return request<RestoreInspection>("/restore/inspect", {
      method: "POST",
      body,
    });
  },
  confirmRestore: (token: string) =>
    request<RestoreInspection & {
      safety_backup: string;
      restored_at: string;
    }>(`/restore/${token}`, { method: "POST" }),
};
