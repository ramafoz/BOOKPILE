const API_URL = import.meta.env.VITE_SERVER_API_URL ?? "/api/v1";

export interface CurrentUser {
  user_id: string;
  username: string;
}

export interface RegistrationResult extends CurrentUser {
  state: string;
  verification_email_sent: boolean;
}

export interface LoginResult extends CurrentUser {
  expires_at: string;
  absolute_expires_at: string;
}

export interface LibrarySummary {
  library_id: string;
  name: string;
  slug: string;
  role: "OWNER" | "VIEWER";
  viewer_scope: "CATALOG_ONLY" | "CATALOG_AND_MAP" | null;
  selected_reading_user_id: string | null;
  can_view_map: boolean;
}

export interface LibraryMember {
  user_id: string;
  username: string;
  role: "OWNER" | "VIEWER";
  viewer_scope: "CATALOG_ONLY" | "CATALOG_AND_MAP" | null;
  selected_reading_user_id: string | null;
  created_at: string;
}

export interface ReadingPerspective {
  user_id: string;
  username: string;
  selected: boolean;
  writable: boolean;
}

export interface CreatedLibraryInvitation {
  invitation_id: string;
  invitation_token: string;
  expires_at: string;
}

export interface Contributor {
  id?: string;
  role_code: string;
  role_label?: string;
  position?: number;
  name: string;
}

export interface ContributorRole {
  code: string;
  label: string;
  sort_order: number;
}

export interface CoverMetadata {
  width_px: number;
  height_px: number;
  byte_size: number;
  updated_at: string;
}

export interface ServerBookSummary {
  id: string;
  title: string;
  author: string;
  display_author: string;
  subtitle: string | null;
  page_count: number | null;
  publisher: string | null;
  current_ed_year: number | null;
  language: string | null;
  fiction_category: string | null;
  binding: string | null;
  publication_type: string | null;
  genre_text: string | null;
  series_name: string | null;
  series_volume: string | null;
  contributors: Contributor[];
  cover: CoverMetadata | null;
  created_at: string;
  updated_at: string;
}

export interface ServerBook extends ServerBookSummary {
  library_id: string;
  isbn_10: string | null;
  isbn_13: string | null;
  original_publication_year: number | null;
  original_language: string | null;
  translation_status: "UNKNOWN" | "ORIGINAL" | "TRANSLATED";
  edition_number: number | null;
  notes: string | null;
  acquisition_date: string | null;
  is_original_collection: boolean;
  height_mm: number | null;
  width_mm: number | null;
  thickness_mm: number | null;
}

export type ServerBookWrite = Omit<
  ServerBook,
  "id" | "library_id" | "display_author" | "cover" | "created_at" | "updated_at"
> & { contributors: Array<{ role_code: string; name: string }> };

export interface CataloguePage {
  library_id: string;
  role: "OWNER" | "VIEWER";
  can_edit: boolean;
  total: number;
  limit: number;
  offset: number;
  books: ServerBookSummary[];
}

export interface CatalogueMetadataOptions {
  languages: string[];
  original_languages: string[];
  publishers: string[];
  genres: string[];
  series_names: string[];
  contributor_roles: ContributorRole[];
}

export interface CatalogueQuery {
  search?: string;
  isbn?: string;
  language?: string[];
  original_language?: string[];
  translation_status?: string[];
  genre?: string[];
  publisher?: string[];
  fiction_category?: string[];
  binding?: string[];
  publication_type?: string[];
  series_name?: string[];
  series_state?: "ANY" | "YES" | "NO";
  author_structure?: "ANY" | "SINGLE" | "MULTIPLE";
  page_min?: number;
  page_max?: number;
  year_field?: "current_ed_year" | "original_publication_year";
  year_min?: number;
  year_max?: number;
  sort_by?: string;
  sort_order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export class ServerApiError extends Error {
  status: number;
  retryAfter: number | null;

  constructor(message: string, status: number, retryAfter: number | null) {
    super(message);
    this.name = "ServerApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export function cookieValue(cookieHeader: string, name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = cookieHeader
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  csrf = false,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (csrf) {
    const token = cookieValue(document.cookie, "bookpile_csrf");
    if (token) headers.set("X-CSRF-Token", token);
  }
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: unknown };
    const validationMessage = Array.isArray(body.detail)
      ? body.detail.map((item) => {
        if (!item || typeof item !== "object") return "";
        const message = "msg" in item ? String(item.msg) : "";
        return message.replace(/^Value error, /, "");
      }).filter(Boolean).join(" ")
      : "";
    const message = typeof body.detail === "string"
      ? body.detail
      : validationMessage || "BOOKPILE could not complete that request.";
    const retryHeader = response.headers.get("Retry-After");
    const retryAfter = retryHeader ? Number.parseInt(retryHeader, 10) : null;
    throw new ServerApiError(
      message,
      response.status,
      Number.isFinite(retryAfter) ? retryAfter : null,
    );
  }
  const responseText = await response.text();
  if (!responseText) return undefined as T;
  return JSON.parse(responseText) as T;
}

export const serverApi = {
  me: () => request<CurrentUser>("/auth/me"),
  login: (identifier: string, password: string, rememberMe: boolean) =>
    request<LoginResult>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password, remember_me: rememberMe }),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }, true),
  revokeAll: () => request<void>(
    "/auth/sessions/revoke-all",
    { method: "POST" },
    true,
  ),
  register: (payload: {
    invitation_token: string;
    email: string;
    username: string;
    password: string;
    password_confirmation: string;
  }) => request<RegistrationResult>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  verifyEmail: (token: string) => request<void>(
    "/auth/verification/confirm",
    { method: "POST", body: JSON.stringify({ token }) },
  ),
  resendVerification: (email: string) => request<void>(
    "/auth/verification/resend",
    { method: "POST", body: JSON.stringify({ email }) },
  ),
  requestPasswordReset: (email: string) => request<void>(
    "/auth/password-reset/request",
    { method: "POST", body: JSON.stringify({ email }) },
  ),
  resetPassword: (token: string, password: string, confirmation: string) =>
    request<void>("/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({
        token,
        password,
        password_confirmation: confirmation,
      }),
    }),
  libraries: () => request<LibrarySummary[]>("/libraries"),
  createLibrary: (name: string) => request<LibrarySummary>(
    "/libraries",
    { method: "POST", body: JSON.stringify({ name }) },
    true,
  ),
  libraryMembers: (libraryId: string) =>
    request<LibraryMember[]>(`/libraries/${libraryId}/members`),
  createLibraryInvitation: (
    libraryId: string,
    role: "OWNER" | "VIEWER",
    viewerScope: "CATALOG_ONLY" | "CATALOG_AND_MAP" | null,
    acknowledgeEqualOwnerPower: boolean,
  ) => request<CreatedLibraryInvitation>(
    `/libraries/${libraryId}/invitations`,
    {
      method: "POST",
      body: JSON.stringify({
        role,
        viewer_scope: viewerScope,
        acknowledge_equal_owner_power: acknowledgeEqualOwnerPower,
      }),
    },
    true,
  ),
  acceptLibraryInvitation: (invitationToken: string) =>
    request<LibrarySummary>(
      "/library-invitations/accept",
      {
        method: "POST",
        body: JSON.stringify({ invitation_token: invitationToken }),
      },
      true,
    ),
  changeLibraryMember: (
    libraryId: string,
    userId: string,
    payload: {
      action: string;
      viewer_scope?: "CATALOG_ONLY" | "CATALOG_AND_MAP" | null;
      current_password: string;
      acknowledge_equal_owner_power?: boolean;
    },
  ) => request<LibraryMember | null>(
    `/libraries/${libraryId}/members/${userId}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    true,
  ),
  readingPerspectives: (libraryId: string) =>
    request<ReadingPerspective[]>(
      `/libraries/${libraryId}/reading-perspectives`,
    ),
  selectReadingPerspective: (libraryId: string, userId: string) =>
    request<ReadingPerspective[]>(
      `/libraries/${libraryId}/reading-perspective`,
      { method: "PUT", body: JSON.stringify({ user_id: userId }) },
      true,
    ),
  catalogue: (libraryId: string, query: CatalogueQuery = {}) => {
    const parameters = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      if (Array.isArray(value)) value.forEach((item) => parameters.append(key, item));
      else parameters.set(key, String(value));
    });
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    return request<CataloguePage>(`/libraries/${libraryId}/catalogue${suffix}`);
  },
  catalogueOptions: (libraryId: string) =>
    request<CatalogueMetadataOptions>(
      `/libraries/${libraryId}/catalogue/metadata-options`,
    ),
  book: (libraryId: string, bookId: string) =>
    request<ServerBook>(`/libraries/${libraryId}/catalogue/${bookId}`),
  createBook: (libraryId: string, book: ServerBookWrite) =>
    request<ServerBook>(
      `/libraries/${libraryId}/catalogue`,
      { method: "POST", body: JSON.stringify(book) },
      true,
    ),
  updateBook: (libraryId: string, bookId: string, book: ServerBookWrite) =>
    request<ServerBook>(
      `/libraries/${libraryId}/catalogue/${bookId}`,
      { method: "PUT", body: JSON.stringify(book) },
      true,
    ),
  deleteBook: (libraryId: string, bookId: string, title: string) =>
    request<void>(
      `/libraries/${libraryId}/catalogue/${bookId}`,
      { method: "DELETE", body: JSON.stringify({ confirmation_title: title }) },
      true,
    ),
  coverUrl: (libraryId: string, bookId: string, version?: string) =>
    `${API_URL}/libraries/${libraryId}/catalogue/${bookId}/cover${version ? `?v=${encodeURIComponent(version)}` : ""}`,
  uploadCover: (libraryId: string, bookId: string, cover: File) => {
    const body = new FormData();
    body.append("cover", cover);
    return request<CoverMetadata>(
      `/libraries/${libraryId}/catalogue/${bookId}/cover`,
      { method: "PUT", body },
      true,
    );
  },
  deleteCover: (libraryId: string, bookId: string) => request<void>(
    `/libraries/${libraryId}/catalogue/${bookId}/cover`,
    { method: "DELETE" },
    true,
  ),
};
