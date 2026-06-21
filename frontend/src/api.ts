import type {
  Book,
  BookPayload,
  Bookcase,
  ContainerType,
  Layer,
  Stats,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail ?? "Something went wrong");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  books: (status: string, search: string) => {
    const params = new URLSearchParams();
    if (status !== "ALL") params.set("status", status);
    if (search.trim()) params.set("search", search.trim());
    return request<Book[]>(`/books?${params}`);
  },
  stats: () => request<Stats>("/stats"),
  library: () => request<Bookcase[]>("/library"),
  createBook: (book: BookPayload) =>
    request<Book>("/books", { method: "POST", body: JSON.stringify(book) }),
  updateBook: (id: number, book: BookPayload) =>
    request<Book>(`/books/${id}`, {
      method: "PATCH",
      body: JSON.stringify(book),
    }),
  deleteBook: (id: number) =>
    request<void>(`/books/${id}`, { method: "DELETE" }),
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
};
