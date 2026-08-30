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
  if (options.body) headers.set("Content-Type", "application/json");
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
    const message = typeof body.detail === "string"
      ? body.detail
      : "BOOKPILE could not complete that request.";
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
};
