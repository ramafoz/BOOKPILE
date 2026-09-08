const API_URL = import.meta.env.VITE_SERVER_API_URL ?? "/api/v1";

export interface CurrentUser {
  user_id: string;
  username: string;
}

export type ProfileVisibility = "PRIVATE" | "SHARED_LIBRARY_MEMBERS" | "AUTHENTICATED";
export type ProfileGender = "UNSPECIFIED" | "MALE" | "FEMALE" | "CUSTOM";
export type ProfilePronoun = "MALE" | "FEMALE" | "NEUTRAL";

export interface AccountProfile {
  user_id: string;
  username: string;
  display_name: string | null;
  timezone: string | null;
  gender: ProfileGender | null;
  custom_gender: string | null;
  preferred_pronoun: ProfilePronoun | null;
  neutral_pronoun: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  date_of_birth: string | null;
  profile_image_visible: boolean;
  visibilities: Record<string, ProfileVisibility> | null;
}

export interface PrivateAccount {
  user_id: string;
  username: string;
  email: string;
  created_at: string;
  password_protected: boolean;
}

export interface StorageOverview {
  libraries: Array<{
    library_id: string;
    name: string;
    colour_key: number;
    share_of_used: number;
    share_of_entitlement: number;
  }>;
  account_data_share_of_used: number;
  account_data_share_of_entitlement: number;
  used_share_of_entitlement: number;
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

export interface RecoverableLibrary {
  deletion_id: string;
  library_id: string;
  name: string;
  deleted_at: string;
  recover_until: string;
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

export type PersonalReadingState = "PENDING" | "READING" | "REREADING" | "READ";

export interface ReadingSession {
  id: string;
  state: "ACTIVE" | "COMPLETED";
  started_date: string | null;
  finished_date: string | null;
  dates_unknown: boolean;
  created_at: string;
  updated_at: string;
}

export interface BookReading {
  library_id: string;
  book_id: string;
  perspective_user_id: string;
  state: PersonalReadingState;
  active_reader_present: boolean;
  writable: boolean;
  total_sessions: number;
  limit: number;
  offset: number;
  sessions: ReadingSession[];
}

export interface ReadingCatalogueOverview {
  perspective_user_id: string;
  writable: boolean;
  pending: number;
  reading: number;
  rereading: number;
  read: number;
  active_display: string;
  items: Array<{
    book_id: string;
    state: PersonalReadingState;
    active_reader_present: boolean;
    goodreads_url: string | null;
    started_date: string | null;
    finished_date: string | null;
    dates_unknown: boolean;
  }>;
}

export interface ReadingStatistics {
  perspective_user_id: string;
  total_catalogue_books: number;
  unique_books_read: number;
  completed_readings: number;
  dated_readings: number;
  rereadings: number;
  pages_read: number;
  average_pages_per_day: number | null;
  median_pages_per_day: number | null;
  pages_per_week: number | null;
  pages_per_month: number | null;
  active_readings: number;
  pending_duration: ReadingDurationStatistic;
  reading_duration: ReadingDurationStatistic;
  books: Array<{
    book_id: string;
    title: string;
    author: string;
    reading_events: number;
    pages_read: number;
    average_pages_per_day: number | null;
    latest_finished_date: string | null;
  }>;
  years: Array<{ year: number; reading_events: number; books_read: number; pages_read: number }>;
}

export interface ReadingDurationStatistic {
  average_days: number | null;
  median_days: number | null;
  sample_size: number;
  excluded: number;
}

export interface GoodreadsReview {
  user_id: string;
  username: string;
  url: string;
}

export interface LoanWrite {
  loaned_to: string;
  notes: string | null;
  loaned_date: string | null;
  expected_return_date: string | null;
}

export interface LoanRecord {
  id: string;
  book_id: string;
  state: "ACTIVE" | "RETURNED";
  loaned_date: string | null;
  expected_return_date: string | null;
  returned_date: string | null;
  created_at: string;
  updated_at: string;
  overdue: boolean;
  loaned_to?: string;
  notes?: string | null;
}

export interface LoanOverview {
  access: "OWNER" | "VIEWER";
  library_id: string;
  writable: boolean;
  total_active: number;
  total_overdue: number;
  loans: LoanRecord[];
}

export interface BookLoans {
  access: "OWNER" | "VIEWER";
  library_id: string;
  book_id: string;
  writable: boolean;
  total_loans: number;
  loans: LoanRecord[];
}

export interface LoanStatistics {
  active: number;
  overdue: number;
  completed: number;
  unknown_loan_dates: number;
  unknown_return_dates: number;
  books: Array<{ book_id: string; title: string; author: string; loans: number }>;
  years: Array<{ year: number; loans: number; returns: number }>;
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

export interface LibraryMemberSummary {
  user_id: string;
  username: string;
  role: "OWNER" | "VIEWER";
  viewer_scope: "CATALOG_ONLY" | "CATALOG_AND_MAP" | null;
}

export interface PhysicalContainer {
  id: string;
  shelf_id: string;
  container_type: "ROW" | "PILE";
  layer: "BACKGROUND" | "FOREGROUND";
  container_number: number;
  book_count: number;
  created_at: string;
  updated_at: string;
}

export interface PhysicalShelf {
  id: string;
  bookcase_id: string;
  shelf_number: number;
  usable_height_mm: number | null;
  usable_width_mm: number | null;
  usable_depth_mm: number | null;
  book_count: number;
  containers: PhysicalContainer[];
  created_at: string;
  updated_at: string;
}

export interface PhysicalBookcase {
  id: string;
  name: string;
  description: string | null;
  height_mm: number | null;
  width_mm: number | null;
  depth_mm: number | null;
  book_count: number;
  shelves: PhysicalShelf[];
  created_at: string;
  updated_at: string;
}

export interface PhysicalBook {
  id: string;
  title: string;
  author: string;
  page_count: number | null;
  publisher?: string | null;
  current_ed_year?: number | null;
  original_publication_year?: number | null;
  language?: string | null;
  original_language?: string | null;
  translation_status?: "UNKNOWN" | "ORIGINAL" | "TRANSLATED";
  fiction_category?: string | null;
  binding?: string | null;
  publication_type?: string | null;
  genre_text?: string | null;
  acquisition_date?: string | null;
  is_original_collection?: boolean;
  height_mm: number | null;
  width_mm: number | null;
  thickness_mm: number | null;
  container_id: string | null;
  position: number | null;
}

export interface VisualBookcaseLayout {
  bookcase_id: string;
  x_mm: number;
  floor_y_mm: number;
  width_mm: number;
  height_mm: number;
  shelf_direction: "TOP_TO_BOTTOM" | "BOTTOM_TO_TOP" | "LEFT_TO_RIGHT" | "RIGHT_TO_LEFT";
  homogeneous_structure: boolean;
  frame_left_mm: number;
  frame_right_mm: number;
  top_closure_mm: number;
  bottom_closure_mm: number;
  separator_thickness_mm: number;
}

export interface VisualShelfLayout {
  shelf_id: string;
  height_weight: number;
  x_mm: number;
  floor_y_mm: number;
  width_mm: number;
  height_mm: number;
  alignment: "LEFT" | "CENTER" | "RIGHT";
  offset_mm: number;
  width_source: "ENTERED" | "FALLBACK" | "DERIVED";
  height_source: "ENTERED" | "FALLBACK" | "DERIVED";
  open_top: boolean;
  left_frame_mm: number;
  right_frame_mm: number;
  top_closure_mm: number;
  bottom_board_mm: number;
  separator_after_mm: number | null;
  separator_anchor: "TOP" | "BOTTOM";
  separator_height_mm: number | null;
  separator_source: "ENTERED" | "FALLBACK" | "DERIVED" | null;
}

export interface VisualContainerLayout {
  container_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  row_anchor: "LEFT" | "RIGHT";
  support_kind: "SHELF" | "CONTAINER";
  support_container_id: string | null;
  pile_alignment: "LEFT" | "CENTER" | "RIGHT";
}

export interface VisualOutsideArea {
  area_kind: "READING" | "LOANED";
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
}

export interface VisualLayout {
  revision: string;
  geometry_mode: "MANUAL" | "PHYSICAL";
  coordinate_system_version: number;
  refresh_shelves_from_physical?: boolean;
  bookcases: VisualBookcaseLayout[];
  shelves: VisualShelfLayout[];
  containers: VisualContainerLayout[];
  outside_areas: VisualOutsideArea[];
  diagnostics: GeometryDiagnostic[];
}

export interface GeometryDiagnostic {
  entity_kind: "LIBRARY" | "BOOKCASE" | "SHELF" | "CONTAINER" | "BOOK";
  entity_id: string | null;
  severity: "INFO" | "WARNING" | "ERROR";
  code: string;
  message: string;
}

export interface PhysicalLibrary {
  library_id: string;
  role: "OWNER" | "VIEWER";
  can_edit: boolean;
  bookcases: PhysicalBookcase[];
  books: PhysicalBook[];
  layout: VisualLayout;
}

export interface RearrangementStep {
  container_id: string;
  position: number;
  new_position_mode: "SQUEEZE" | "SWAP" | "CONTINUE";
}

export interface RearrangementOperation {
  book_id: string;
  old_position_mode: "COLLAPSE" | "LEAVE_GAP";
  release_shelf_space: boolean;
  steps: RearrangementStep[];
}

export interface RearrangementRequest extends RearrangementOperation {
  completed_operations: RearrangementOperation[];
}

export interface RearrangementResult {
  revision: string;
  valid_to_apply: boolean;
  complete: boolean;
  effective_old_position_mode: "COLLAPSE" | "LEAVE_GAP";
  next_active_book_id: string | null;
  placements: Array<{ book_id: string; container_id: string | null; position: number | null }>;
  gaps: Array<{ container_id: string; positions: number[] }>;
  movement_log: string[];
  movement_groups: string[][];
  warnings: string[];
  geometry_errors: string[];
  container_layouts: VisualContainerLayout[];
}

export interface BookcaseWrite {
  name: string;
  description: string | null;
  height_mm: number | null;
  width_mm: number | null;
  depth_mm: number | null;
}

export interface BookcaseCreate extends BookcaseWrite {
  shelf_direction: "TOP_TO_BOTTOM" | "BOTTOM_TO_TOP" | "LEFT_TO_RIGHT" | "RIGHT_TO_LEFT";
  homogeneous_structure: boolean;
}

export interface ShelfWrite {
  bookcase_id: string;
  shelf_number: number;
  usable_height_mm: number | null;
  usable_width_mm: number | null;
  usable_depth_mm: number | null;
}

export interface ContainerWrite {
  shelf_id: string;
  container_type: "ROW" | "PILE";
  layer: "BACKGROUND" | "FOREGROUND";
  container_number: number;
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
  perspective_user_id?: string;
  reading_state?: "ANY" | "PENDING" | "READING" | "REREADING" | "READ";
  rereading_state?: "ANY" | "YES" | "NO";
  reading_date_field?: "STARTED" | "FINISHED";
  reading_date_from?: string;
  reading_date_to?: string;
  available_only?: boolean;
  loan_scope?: "ANY" | "ACTIVE" | "OVERDUE" | "EVER" | "NEVER";
  loaned_to?: string;
  loan_date_field?: "LOANED" | "EXPECTED" | "RETURNED";
  loan_date_from?: string;
  loan_date_to?: string;
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
  accountProfile: () => request<AccountProfile>("/account/profile"),
  account: () => request<PrivateAccount>("/account"),
  profile: (userId: string) => request<AccountProfile>(`/profiles/${userId}`),
  updateAccountProfile: (payload: Omit<AccountProfile, "user_id" | "username" | "profile_image_visible">) =>
    request<AccountProfile>(
      "/account/profile",
      { method: "PUT", body: JSON.stringify(payload) },
      true,
    ),
  accountStorage: () => request<StorageOverview>("/account/storage"),
  changePassword: (payload: { current_password: string; new_password: string; confirmation: string }) =>
    request<void>("/account/password", { method: "PUT", body: JSON.stringify(payload) }, true),
  uploadProfileImage: (image: File) => {
    const form = new FormData();
    form.append("image", image);
    return request<void>("/account/profile/image", { method: "PUT", body: form }, true);
  },
  removeProfileImage: () => request<void>(
    "/account/profile/image",
    { method: "DELETE" },
    true,
  ),
  profileImageUrl: (userId: string, revision = "") =>
    `${API_URL}/profiles/${userId}/image${revision ? `?v=${encodeURIComponent(revision)}` : ""}`,
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
  deleteLibrary: (
    libraryId: string,
    payload: {
      current_password: string;
      confirmation_name: string;
      acknowledge_permanent_deletion: boolean;
    },
  ) => request<RecoverableLibrary>(
    `/libraries/${libraryId}`,
    { method: "DELETE", body: JSON.stringify(payload) },
    true,
  ),
  recoverableLibraries: () =>
    request<RecoverableLibrary[]>("/account/deleted-libraries"),
  restoreLibrary: (deletionId: string, currentPassword: string) =>
    request<LibrarySummary>(
      `/account/deleted-libraries/${deletionId}/restore`,
      { method: "POST", body: JSON.stringify({ current_password: currentPassword }) },
      true,
    ),
  libraryMembers: (libraryId: string) =>
    request<LibraryMember[]>(`/libraries/${libraryId}/members`),
  libraryMemberSummary: (libraryId: string) =>
    request<LibraryMemberSummary[]>(`/libraries/${libraryId}/member-summary`),
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
  bookReading: (libraryId: string, bookId: string, perspectiveUserId?: string) => {
    const query = new URLSearchParams();
    if (perspectiveUserId) query.set("perspective_user_id", perspectiveUserId);
    const suffix = query.size ? `?${query}` : "";
    return request<BookReading>(
      `/libraries/${libraryId}/catalogue/${bookId}/reading${suffix}`,
    );
  },
  readingOverview: (libraryId: string, perspectiveUserId: string) => {
    const query = new URLSearchParams({ perspective_user_id: perspectiveUserId });
    return request<ReadingCatalogueOverview>(
      `/libraries/${libraryId}/reading-overview?${query}`,
    );
  },
  readingStatistics: (
    libraryId: string,
    perspectiveUserId: string,
    filters: { language?: string; genre?: string; publisher?: string; reading_year?: number } = {},
  ) => {
    const query = new URLSearchParams({ perspective_user_id: perspectiveUserId });
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return request<ReadingStatistics>(`/libraries/${libraryId}/reading-overview/statistics?${query}`);
  },
  startReading: (libraryId: string, bookId: string, startedDate: string) =>
    request<ReadingSession>(
      `/libraries/${libraryId}/catalogue/${bookId}/reading/sessions/start`,
      { method: "POST", body: JSON.stringify({ started_date: startedDate }) },
      true,
    ),
  finishReading: (libraryId: string, bookId: string, sessionId: string, finishedDate: string) =>
    request<ReadingSession>(
      `/libraries/${libraryId}/catalogue/${bookId}/reading/sessions/${sessionId}/finish`,
      { method: "POST", body: JSON.stringify({ finished_date: finishedDate }) },
      true,
    ),
  cancelReading: (libraryId: string, bookId: string, sessionId: string) =>
    request<void>(
      `/libraries/${libraryId}/catalogue/${bookId}/reading/sessions/${sessionId}/cancel`,
      { method: "DELETE" },
      true,
    ),
  addHistoricalReading: (
    libraryId: string,
    bookId: string,
    payload: { started_date: string | null; finished_date: string | null; dates_unknown: boolean },
  ) => request<ReadingSession>(
    `/libraries/${libraryId}/catalogue/${bookId}/reading/sessions/historical`,
    { method: "POST", body: JSON.stringify(payload) },
    true,
  ),
  updateHistoricalReading: (
    libraryId: string,
    bookId: string,
    sessionId: string,
    payload: { started_date: string | null; finished_date: string | null; dates_unknown: boolean },
  ) => request<ReadingSession>(
    `/libraries/${libraryId}/catalogue/${bookId}/reading/sessions/${sessionId}`,
    { method: "PUT", body: JSON.stringify(payload) },
    true,
  ),
  deleteHistoricalReading: (libraryId: string, bookId: string, sessionId: string) =>
    request<void>(
      `/libraries/${libraryId}/catalogue/${bookId}/reading/sessions/${sessionId}`,
      { method: "DELETE" },
      true,
    ),
  goodreadsReviews: (libraryId: string, bookId: string) =>
    request<GoodreadsReview[]>(
      `/libraries/${libraryId}/catalogue/${bookId}/reading/goodreads`,
    ),
  setMyGoodreadsReview: (libraryId: string, bookId: string, url: string | null) =>
    request<GoodreadsReview | null>(
      `/libraries/${libraryId}/catalogue/${bookId}/reading/goodreads/me`,
      { method: "PUT", body: JSON.stringify({ url }) },
      true,
    ),
  loanOverview: (libraryId: string) =>
    request<LoanOverview>(`/libraries/${libraryId}/loan-overview`),
  loanStatistics: (libraryId: string, query: { language?: string; genre?: string; publisher?: string; loan_year?: number } = {}) => {
    const parameters = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => { if (value !== undefined) parameters.set(key, String(value)); });
    const suffix = parameters.size ? `?${parameters}` : "";
    return request<LoanStatistics>(`/libraries/${libraryId}/loan-overview/statistics${suffix}`);
  },
  bookLoans: (libraryId: string, bookId: string) =>
    request<BookLoans>(`/libraries/${libraryId}/catalogue/${bookId}/loans`),
  startLoan: (libraryId: string, bookId: string, payload: LoanWrite) =>
    request<LoanRecord>(
      `/libraries/${libraryId}/catalogue/${bookId}/loans/active`,
      { method: "POST", body: JSON.stringify(payload) }, true,
    ),
  returnLoan: (libraryId: string, bookId: string, returnedDate: string | null) =>
    request<LoanRecord>(
      `/libraries/${libraryId}/catalogue/${bookId}/loans/active/return`,
      { method: "POST", body: JSON.stringify({ returned_date: returnedDate }) }, true,
    ),
  cancelLoan: (libraryId: string, bookId: string) => request<void>(
    `/libraries/${libraryId}/catalogue/${bookId}/loans/active`,
    { method: "DELETE" }, true,
  ),
  addHistoricalLoan: (libraryId: string, bookId: string, payload: LoanWrite & { returned_date: string | null }) =>
    request<LoanRecord>(
      `/libraries/${libraryId}/catalogue/${bookId}/loans/history`,
      { method: "POST", body: JSON.stringify(payload) }, true,
    ),
  updateHistoricalLoan: (libraryId: string, bookId: string, loanId: string, payload: LoanWrite & { returned_date: string | null }) =>
    request<LoanRecord>(
      `/libraries/${libraryId}/catalogue/${bookId}/loans/${loanId}`,
      { method: "PUT", body: JSON.stringify(payload) }, true,
    ),
  deleteHistoricalLoan: (libraryId: string, bookId: string, loanId: string) => request<void>(
    `/libraries/${libraryId}/catalogue/${bookId}/loans/${loanId}`,
    { method: "DELETE" }, true,
  ),
  createBook: (libraryId: string, book: ServerBookWrite) =>
    request<ServerBook>(
      `/libraries/${libraryId}/catalogue`,
      { method: "POST", body: JSON.stringify(book) },
      true,
    ),
  createBookWithPlacement: (
    libraryId: string,
    book: ServerBookWrite,
    containerId: string | null,
    position: number | null,
  ) => request<ServerBook>(
    `/libraries/${libraryId}/catalogue/with-placement`,
    { method: "POST", body: JSON.stringify({ book, placement: { container_id: containerId, position } }) },
    true,
  ),
  createBookWithPlacementAndLoan: (
    libraryId: string,
    book: ServerBookWrite,
    containerId: string | null,
    position: number | null,
    loan: LoanWrite,
  ) => request<ServerBook>(
    `/libraries/${libraryId}/catalogue/with-placement-and-loan`,
    { method: "POST", body: JSON.stringify({ book, placement: { container_id: containerId, position }, loan }) },
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
  physicalLibrary: (libraryId: string) => request<PhysicalLibrary>(
    `/libraries/${libraryId}/physical-library`,
  ),
  updateBookPlacement: (
    libraryId: string,
    bookId: string,
    containerId: string | null,
    position: number | null,
  ) => request<PhysicalLibrary>(
    `/libraries/${libraryId}/physical-library/books/${bookId}/placement`,
    {
      method: "PUT",
      body: JSON.stringify({ container_id: containerId, position }),
    },
    true,
  ),
  previewRearrangement: (libraryId: string, payload: RearrangementRequest) =>
    request<RearrangementResult>(
      `/libraries/${libraryId}/physical-library/rearrangements/preview`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  applyRearrangement: (libraryId: string, payload: RearrangementRequest, revision: string) =>
    request<RearrangementResult>(
      `/libraries/${libraryId}/physical-library/rearrangements/apply`,
      { method: "POST", body: JSON.stringify({ ...payload, revision }) },
      true,
    ),
  updateBookWithPlacement: (
    libraryId: string,
    bookId: string,
    book: ServerBookWrite,
    containerId: string | null,
    position: number | null,
  ) => request<ServerBook>(
    `/libraries/${libraryId}/catalogue/${bookId}/with-placement`,
    { method: "PUT", body: JSON.stringify({ book, placement: { container_id: containerId, position } }) },
    true,
  ),
  updateVisualLayout: (libraryId: string, layout: VisualLayout) =>
    request<PhysicalLibrary>(
      `/libraries/${libraryId}/physical-library/layout`,
      { method: "PUT", body: JSON.stringify(layout) },
      true,
    ),
  createBookcase: (libraryId: string, payload: BookcaseCreate) =>
    request<PhysicalLibrary>(
      `/libraries/${libraryId}/physical-library/bookcases`,
      { method: "POST", body: JSON.stringify(payload) },
      true,
    ),
  updateBookcase: (libraryId: string, bookcaseId: string, payload: BookcaseWrite) =>
    request<PhysicalLibrary>(
      `/libraries/${libraryId}/physical-library/bookcases/${bookcaseId}`,
      { method: "PUT", body: JSON.stringify(payload) },
      true,
    ),
  deleteBookcase: (libraryId: string, bookcaseId: string) => request<void>(
    `/libraries/${libraryId}/physical-library/bookcases/${bookcaseId}`,
    { method: "DELETE", body: JSON.stringify({ confirmed: true }) },
    true,
  ),
  createShelf: (libraryId: string, payload: ShelfWrite) => request<PhysicalLibrary>(
    `/libraries/${libraryId}/physical-library/shelves`,
    { method: "POST", body: JSON.stringify(payload) },
    true,
  ),
  updateShelf: (
    libraryId: string,
    shelfId: string,
    payload: Omit<ShelfWrite, "bookcase_id">,
  ) => request<PhysicalLibrary>(
    `/libraries/${libraryId}/physical-library/shelves/${shelfId}`,
    { method: "PUT", body: JSON.stringify(payload) },
    true,
  ),
  deleteShelf: (libraryId: string, shelfId: string) => request<void>(
    `/libraries/${libraryId}/physical-library/shelves/${shelfId}`,
    { method: "DELETE", body: JSON.stringify({ confirmed: true }) },
    true,
  ),
  createContainer: (libraryId: string, payload: ContainerWrite) =>
    request<PhysicalLibrary>(
      `/libraries/${libraryId}/physical-library/containers`,
      { method: "POST", body: JSON.stringify(payload) },
      true,
    ),
  updateContainer: (libraryId: string, containerId: string, containerNumber: number) =>
    request<PhysicalLibrary>(
      `/libraries/${libraryId}/physical-library/containers/${containerId}`,
      { method: "PUT", body: JSON.stringify({ container_number: containerNumber }) },
      true,
    ),
  deleteContainer: (libraryId: string, containerId: string) => request<void>(
    `/libraries/${libraryId}/physical-library/containers/${containerId}`,
    { method: "DELETE", body: JSON.stringify({ confirmed: true }) },
    true,
  ),
};
