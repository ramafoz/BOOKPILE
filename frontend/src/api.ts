import type {
  Book,
  BookPayload,
  Bookcase,
  ContainerType,
  Layer,
  Stats,
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
}

const API_URL = import.meta.env.VITE_API_URL ?? "/api";

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
    return request<Book[]>(`/books?${params}`);
  },
  stats: () => request<Stats>("/stats"),
  library: () => request<Bookcase[]>("/library"),
  createBook: (book: BookPayload, shiftExisting = false) =>
    request<Book>("/books", {
      method: "POST",
      body: JSON.stringify({ ...book, shift_existing: shiftExisting }),
    }),
  updateBook: (id: number, book: BookPayload) =>
    request<Book>(`/books/${id}`, {
      method: "PATCH",
      body: JSON.stringify(book),
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
  createShelf: (bookcaseId: number, shelfNumber: number) =>
    request("/shelves", {
      method: "POST",
      body: JSON.stringify({
        bookcase_id: bookcaseId,
        shelf_number: shelfNumber,
      }),
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
