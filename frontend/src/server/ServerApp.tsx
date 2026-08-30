import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  KeyRound,
  LibraryBig,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Mail,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import {
  type CurrentUser,
  ServerApiError,
  serverApi,
} from "./serverApi";

type Route =
  | "login"
  | "register"
  | "verify-email"
  | "resend-verification"
  | "forgot-password"
  | "reset-password";

function routeFromPath(pathname: string): Route {
  const route = pathname.replace(/^\/+|\/+$/g, "");
  if (
    route === "register"
    || route === "verify-email"
    || route === "resend-verification"
    || route === "forgot-password"
    || route === "reset-password"
  ) return route;
  return "login";
}

function friendlyError(error: unknown): string {
  if (error instanceof ServerApiError) {
    if (error.status === 429) {
      const minutes = error.retryAfter
        ? Math.max(1, Math.ceil(error.retryAfter / 60))
        : null;
      return minutes
        ? `Too many attempts. Please try again in about ${minutes} minute${minutes === 1 ? "" : "s"}.`
        : "Too many attempts. Please wait before trying again.";
    }
    return error.message;
  }
  return "BOOKPILE could not reach the server. Please try again.";
}

function AuthShell({ children }: { children: ReactNode }) {
  return (
    <main className="server-shell">
      <section className="server-story" aria-label="BOOKPILE introduction">
        <a className="server-brand" href="/login">
          <span className="server-brand-mark"><LibraryBig size={24} /></span>
          <span>BOOKPILE</span>
        </a>
        <div className="server-story-copy">
          <p className="server-eyebrow">Your personal library, securely mapped</p>
          <h1>Every book<br />has its place.</h1>
          <p>
            The hosted BOOKPILE is being built as a private, invitation-only
            service. Your account is the first boundary around your library.
          </p>
        </div>
        <div className="server-books" aria-hidden="true">
          <i /><i /><i /><i /><i /><i />
          <span />
        </div>
      </section>
      <section className="server-auth-column">
        {children}
        <p className="server-phase-note">
          Server preview · Accounts are separate from BOOKPILE Local v1
        </p>
      </section>
    </main>
  );
}

function AuthCard({
  eyebrow,
  title,
  intro,
  children,
}: {
  eyebrow: string;
  title: string;
  intro: string;
  children: ReactNode;
}) {
  return (
    <div className="server-auth-card">
      <p className="server-card-eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p className="server-card-intro">{intro}</p>
      {children}
    </div>
  );
}

function Field({
  label,
  icon,
  required = true,
  ...inputProps
}: {
  label: string;
  icon: ReactNode;
  required?: boolean;
} & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="server-field">
      <span>{label}{required && <b aria-hidden="true"> *</b>}</span>
      <span className="server-input-wrap">
        {icon}
        <input required={required} {...inputProps} />
      </span>
    </label>
  );
}

function SubmitButton({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <button className="server-submit" type="submit" disabled={busy}>
      {busy ? <LoaderCircle className="server-spinner" size={19} /> : children}
    </button>
  );
}

function Message({ kind, children }: { kind: "error" | "success"; children: ReactNode }) {
  return <div className={`server-message ${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div>;
}

function LoginPage({
  navigate,
  onLogin,
}: {
  navigate: (route: Route) => void;
  onLogin: (user: CurrentUser) => void;
}) {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(await serverApi.login(identifier, password, rememberMe));
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      eyebrow="Welcome back"
      title="Sign in"
      intro="Enter the private account created from your beta invitation."
    >
      <form className="server-form" onSubmit={submit}>
        <Field
          label="Username or email"
          icon={<UserRound size={18} />}
          value={identifier}
          onChange={(event) => setIdentifier(event.target.value)}
          autoComplete="username"
          autoFocus
        />
        <Field
          label="Password"
          icon={<LockKeyhole size={18} />}
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
        />
        <label className="server-check">
          <input
            type="checkbox"
            checked={rememberMe}
            onChange={(event) => setRememberMe(event.target.checked)}
          />
          Keep me signed in on this device
        </label>
        {error && <Message kind="error">{error}</Message>}
        <SubmitButton busy={busy}>Sign in <ArrowRight size={18} /></SubmitButton>
      </form>
      <div className="server-card-links">
        <button type="button" onClick={() => navigate("forgot-password")}>Forgot password?</button>
        <button type="button" onClick={() => navigate("resend-verification")}>Verify account</button>
        <button type="button" onClick={() => navigate("register")}>Use an invitation</button>
      </div>
    </AuthCard>
  );
}

function RegisterPage({ navigate }: { navigate: (route: Route) => void }) {
  const inviteFromUrl = new URLSearchParams(window.location.search).get("invite") ?? "";
  const [invite, setInvite] = useState(inviteFromUrl);
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [complete, setComplete] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await serverApi.register({
        invitation_token: invite.trim(),
        email,
        username,
        password,
        password_confirmation: confirmation,
      });
      window.history.replaceState({}, "", "/register");
      setComplete(result.verification_email_sent
        ? "Your account was created. Check your email to verify it before signing in."
        : "Your account was created, but the verification email could not be sent. Use Verify account to request another link.");
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      eyebrow="Invitation-only beta"
      title="Create your account"
      intro="All fields are required. Your invitation is single-use and expires after seven days."
    >
      {complete ? (
        <div className="server-complete">
          <CheckCircle2 size={38} />
          <p>{complete}</p>
          <button className="server-submit" type="button" onClick={() => navigate("login")}>Continue to sign in</button>
        </div>
      ) : (
        <form className="server-form" onSubmit={submit}>
          <Field label="Invitation token" icon={<KeyRound size={18} />} value={invite} onChange={(event) => setInvite(event.target.value)} autoComplete="off" />
          <Field label="Email" icon={<Mail size={18} />} type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
          <Field label="Username" icon={<UserRound size={18} />} value={username} onChange={(event) => setUsername(event.target.value)} minLength={3} maxLength={30} pattern="[A-Za-z0-9_]+" autoComplete="username" />
          <Field label="Password" icon={<LockKeyhole size={18} />} type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} maxLength={128} autoComplete="new-password" />
          <Field label="Confirm password" icon={<LockKeyhole size={18} />} type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={12} maxLength={128} autoComplete="new-password" />
          <p className="server-help">Use 12–128 characters. Spaces and Unicode characters are welcome.</p>
          {error && <Message kind="error">{error}</Message>}
          <SubmitButton busy={busy}>Create account <ArrowRight size={18} /></SubmitButton>
        </form>
      )}
      <div className="server-card-links single">
        <button type="button" onClick={() => navigate("login")}>Back to sign in</button>
      </div>
    </AuthCard>
  );
}

function EmailRequestPage({
  mode,
  navigate,
}: {
  mode: "verification" | "reset";
  navigate: (route: Route) => void;
}) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);
  const verification = mode === "verification";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (verification) await serverApi.resendVerification(email);
      else await serverApi.requestPasswordReset(email);
      setComplete(true);
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      eyebrow={verification ? "Account verification" : "Account recovery"}
      title={verification ? "Request a new link" : "Reset your password"}
      intro={verification
        ? "We will send a fresh verification link if the account is eligible."
        : "We will send a password-reset link if the account exists and is active."}
    >
      {complete ? (
        <Message kind="success">
          If that email belongs to an eligible BOOKPILE account, a message is on its way.
        </Message>
      ) : (
        <form className="server-form" onSubmit={submit}>
          <Field label="Email" icon={<Mail size={18} />} type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" autoFocus />
          {error && <Message kind="error">{error}</Message>}
          <SubmitButton busy={busy}>Send link <ArrowRight size={18} /></SubmitButton>
        </form>
      )}
      <div className="server-card-links single">
        <button type="button" onClick={() => navigate("login")}>Back to sign in</button>
      </div>
    </AuthCard>
  );
}

function TokenActionPage({
  mode,
  navigate,
}: {
  mode: "verification" | "reset";
  navigate: (route: Route) => void;
}) {
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);
  const verification = mode === "verification";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) {
      setError("This link does not contain a valid token.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (verification) await serverApi.verifyEmail(token);
      else await serverApi.resetPassword(token, password, confirmation);
      window.history.replaceState({}, "", verification ? "/verify-email" : "/reset-password");
      setComplete(true);
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      eyebrow={verification ? "Confirm your address" : "Choose a new password"}
      title={verification ? "Verify email" : "Reset password"}
      intro={verification
        ? "Confirm this one-time link to activate your BOOKPILE account."
        : "Reset links expire after 30 minutes and can only be used once."}
    >
      {complete ? (
        <div className="server-complete">
          <CheckCircle2 size={38} />
          <p>{verification ? "Your email is verified. You can now sign in." : "Your password has been changed and all previous sessions were signed out."}</p>
          <button className="server-submit" type="button" onClick={() => navigate("login")}>Continue to sign in</button>
        </div>
      ) : (
        <form className="server-form" onSubmit={submit}>
          {!verification && (
            <>
              <Field label="New password" icon={<LockKeyhole size={18} />} type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} maxLength={128} autoComplete="new-password" autoFocus />
              <Field label="Confirm new password" icon={<LockKeyhole size={18} />} type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={12} maxLength={128} autoComplete="new-password" />
            </>
          )}
          {error && <Message kind="error">{error}</Message>}
          <SubmitButton busy={busy}>{verification ? "Verify my email" : "Change password"} <ArrowRight size={18} /></SubmitButton>
        </form>
      )}
      <div className="server-card-links single">
        <button type="button" onClick={() => navigate("login")}>Back to sign in</button>
      </div>
    </AuthCard>
  );
}

function AccountHome({ user, onSignedOut }: { user: CurrentUser; onSignedOut: () => void }) {
  const [busy, setBusy] = useState<"logout" | "all" | null>(null);
  const [error, setError] = useState("");

  async function signOut(all: boolean) {
    setBusy(all ? "all" : "logout");
    setError("");
    try {
      if (all) await serverApi.revokeAll();
      else await serverApi.logout();
      onSignedOut();
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="server-account-shell">
      <header className="server-account-header">
        <a className="server-brand" href="/">
          <span className="server-brand-mark"><LibraryBig size={24} /></span>
          <span>BOOKPILE</span>
        </a>
        <button type="button" onClick={() => void signOut(false)} disabled={busy !== null}>
          <LogOut size={18} /> Sign out
        </button>
      </header>
      <section className="server-account-card">
        <span className="server-account-icon"><BookOpen size={34} /></span>
        <p className="server-card-eyebrow">Identity foundation complete</p>
        <h1>Welcome, {user.username}.</h1>
        <p>
          Your verified session is working. Libraries and memberships arrive in
          Phase 3; no Local catalogue has been imported or modified.
        </p>
        <div className="server-account-status">
          <ShieldCheck size={22} />
          <span><b>Private session active</b><small>Opaque cookie · CSRF protected</small></span>
        </div>
        {error && <Message kind="error">{error}</Message>}
        <button className="server-danger-link" type="button" onClick={() => void signOut(true)} disabled={busy !== null}>
          Sign out from every device
        </button>
      </section>
    </main>
  );
}

export default function ServerApp() {
  const [route, setRoute] = useState<Route>(() => routeFromPath(window.location.pathname));
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootError, setBootError] = useState("");

  const navigate = useCallback((next: Route) => {
    window.history.pushState({}, "", `/${next}`);
    setRoute(next);
  }, []);

  useEffect(() => {
    const pop = () => setRoute(routeFromPath(window.location.pathname));
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);

  useEffect(() => {
    let active = true;
    void serverApi.me()
      .then((current) => { if (active) setUser(current); })
      .catch((error: unknown) => {
        if (active && (!(error instanceof ServerApiError) || error.status !== 401)) {
          setBootError(friendlyError(error));
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  if (loading) {
    return <div className="server-loading"><LibraryBig size={38} /><LoaderCircle className="server-spinner" size={24} /><span>Opening BOOKPILE…</span></div>;
  }
  if (bootError) {
    return <div className="server-loading error"><LibraryBig size={38} /><p>{bootError}</p><button type="button" onClick={() => window.location.reload()}>Try again</button></div>;
  }
  if (user && route !== "verify-email" && route !== "reset-password") {
    return <AccountHome user={user} onSignedOut={() => { setUser(null); navigate("login"); }} />;
  }

  let page: ReactNode;
  if (route === "register") page = <RegisterPage navigate={navigate} />;
  else if (route === "verify-email") page = <TokenActionPage mode="verification" navigate={navigate} />;
  else if (route === "resend-verification") page = <EmailRequestPage mode="verification" navigate={navigate} />;
  else if (route === "forgot-password") page = <EmailRequestPage mode="reset" navigate={navigate} />;
  else if (route === "reset-password") page = <TokenActionPage mode="reset" navigate={navigate} />;
  else page = <LoginPage navigate={navigate} onLogin={setUser} />;

  return <AuthShell>{page}</AuthShell>;
}
