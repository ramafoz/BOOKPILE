import { type CSSProperties, type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  KeyRound,
  Layers3,
  LibraryBig,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Mail,
  Map,
  Plus,
  Settings2,
  ShieldCheck,
  Users,
  UserRound,
} from "lucide-react";
import {
  type CurrentUser,
  type LibraryMember,
  type LibraryMemberSummary,
  type LibrarySummary,
  type ReadingPerspective,
  ServerApiError,
  serverApi,
} from "./serverApi";
import CatalogueWorkspace from "./CatalogueWorkspace";
import PhysicalLibraryWorkspace from "./PhysicalLibraryWorkspace";
import ServerLibraryMap from "./ServerLibraryMap";
import {
  workspacePerspectiveLabel,
} from "./workspacePresentation";
import TimedNoticeStack from "./TimedNoticeStack";
import { useTimedNotices } from "./timedNotices";

type Route =
  | "login"
  | "register"
  | "verify-email"
  | "resend-verification"
  | "forgot-password"
  | "reset-password";

interface PendingMemberChange {
  member: LibraryMember;
  action: "CHANGE_VIEWER_SCOPE" | "PROMOTE_TO_OWNER" | "DOWNGRADE_TO_VIEWER" | "REMOVE";
  title: string;
  explanation: string;
  viewerScope: "CATALOG_ONLY" | "CATALOG_AND_MAP" | null;
}

interface PanelAnchor {
  left: number;
  right: number;
  top: number;
}

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
  const { notices, pushNotice, dismissNotice } = useTimedNotices();
  const [libraries, setLibraries] = useState<LibrarySummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [members, setMembers] = useState<LibraryMember[]>([]);
  const [memberSummary, setMemberSummary] = useState<LibraryMemberSummary[]>([]);
  const [perspectives, setPerspectives] = useState<ReadingPerspective[]>([]);
  const [libraryName, setLibraryName] = useState("");
  const [invitationToken, setInvitationToken] = useState(
    () => new URLSearchParams(window.location.search).get("library-invite") ?? "",
  );
  const [inviteRole, setInviteRole] = useState<"OWNER" | "VIEWER">("VIEWER");
  const [inviteScope, setInviteScope] = useState<"CATALOG_ONLY" | "CATALOG_AND_MAP">("CATALOG_ONLY");
  const [ownerWarning, setOwnerWarning] = useState(false);
  const [generatedLink, setGeneratedLink] = useState("");
  const [generatedToken, setGeneratedToken] = useState("");
  const [dataBusy, setDataBusy] = useState(false);
  const [pendingMemberChange, setPendingMemberChange] = useState<PendingMemberChange | null>(null);
  const [memberChangePassword, setMemberChangePassword] = useState("");
  const [workspace, setWorkspace] = useState<"CATALOGUE" | "MAP" | "LAYOUT">("CATALOGUE");
  const [controlsPanel, setControlsPanel] = useState<"LIBRARIES" | "VIEW" | "SETTINGS" | null>(null);
  const [panelAnchor, setPanelAnchor] = useState<PanelAnchor | null>(null);

  const selected = libraries.find((library) => library.library_id === selectedId) ?? null;

  function toggleControlsPanel(panel: NonNullable<typeof controlsPanel>, button: HTMLButtonElement) {
    if (controlsPanel === panel) {
      setControlsPanel(null);
      return;
    }
    const bounds = button.getBoundingClientRect();
    setPanelAnchor({ left: bounds.left, right: window.innerWidth - bounds.right, top: bounds.bottom + 8 });
    setControlsPanel(panel);
  }

  function anchoredPanelStyle(preferredWidth: number, align: "left" | "right"): CSSProperties | undefined {
    if (!panelAnchor) return undefined;
    const viewportWidth = document.documentElement.clientWidth;
    const width = Math.min(preferredWidth, viewportWidth - 16);
    const candidate = align === "left" ? panelAnchor.left : viewportWidth - panelAnchor.right - width;
    return {
      top: panelAnchor.top,
      left: Math.max(8, Math.min(candidate, viewportWidth - width - 8)),
      width,
    };
  }

  const reloadLibraries = useCallback(async (preferredId?: string) => {
    const result = await serverApi.libraries();
    setLibraries(result);
    setSelectedId((current) => {
      const wanted = preferredId ?? current;
      return result.some((item) => item.library_id === wanted)
        ? wanted
        : (result[0]?.library_id ?? "");
    });
  }, []);

  useEffect(() => {
    void reloadLibraries().catch((caught) => setError(friendlyError(caught)));
  }, [reloadLibraries]);

  useEffect(() => {
    if (!selected) {
      setMembers([]);
      setMemberSummary([]);
      setPerspectives([]);
      return;
    }
    let active = true;
    Promise.all([
      serverApi.readingPerspectives(selected.library_id),
      serverApi.libraryMemberSummary(selected.library_id),
      selected.role === "OWNER"
        ? serverApi.libraryMembers(selected.library_id)
        : Promise.resolve([]),
    ]).then(([nextPerspectives, nextMemberSummary, nextMembers]) => {
      if (active) {
        setPerspectives(nextPerspectives);
        setMemberSummary(nextMemberSummary);
        setMembers(nextMembers);
      }
    }).catch((caught) => {
      if (active) setError(friendlyError(caught));
    });
    return () => { active = false; };
  }, [selected]);

  useEffect(() => {
    if (!controlsPanel) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setControlsPanel(null);
    };
    const closeOutside = (event: PointerEvent) => {
      const target = event.target as Element | null;
      if (!target?.closest(".server-compact-navigation, .server-library-sidebar, .server-floating-control-panel, .server-members-control-stack")) {
        setControlsPanel(null);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    window.addEventListener("pointerdown", closeOutside);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("pointerdown", closeOutside);
    };
  }, [controlsPanel]);

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

  async function createLibrary(event: FormEvent) {
    event.preventDefault();
    setDataBusy(true);
    setError("");
    try {
      const created = await serverApi.createLibrary(libraryName);
      setLibraryName("");
      await reloadLibraries(created.library_id);
      pushNotice(`“${created.name}” was created. You are its first Owner.`);
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
    }
  }

  async function acceptInvitation(event: FormEvent) {
    event.preventDefault();
    setDataBusy(true);
    setError("");
    try {
      const accepted = await serverApi.acceptLibraryInvitation(invitationToken.trim());
      setInvitationToken("");
      window.history.replaceState({}, "", "/");
      await reloadLibraries(accepted.library_id);
      pushNotice(`You joined “${accepted.name}” as ${accepted.role === "OWNER" ? "an Owner" : "a Viewer"}.`);
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
    }
  }

  async function createInvitation(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setDataBusy(true);
    setError("");
    try {
      const result = await serverApi.createLibraryInvitation(
        selected.library_id,
        inviteRole,
        inviteRole === "VIEWER" ? inviteScope : null,
        ownerWarning,
      );
      const url = new URL("/login", window.location.origin);
      url.searchParams.set("library-invite", result.invitation_token);
      setGeneratedLink(url.toString());
      setGeneratedToken(result.invitation_token);
      pushNotice("The single-use library invitation is ready. It expires in seven days.");
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
    }
  }

  async function copyInvitation(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setError("");
      pushNotice(`${label} copied to the clipboard.`);
    } catch {
      setError("BOOKPILE could not access the clipboard. Select and copy the visible value manually.");
    }
  }

  async function selectPerspective(userId: string) {
    if (!selected) return;
    setDataBusy(true);
    try {
      setPerspectives(await serverApi.selectReadingPerspective(selected.library_id, userId));
      await reloadLibraries(selected.library_id);
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
    }
  }

  function requestMemberChange(
    member: LibraryMember,
    action: PendingMemberChange["action"],
  ) {
    let title = "Update membership";
    let explanation = "Confirm this change to the member's library access.";
    let viewerScope: PendingMemberChange["viewerScope"] = member.viewer_scope;
    if (action === "CHANGE_VIEWER_SCOPE") {
      const grantingMap = member.viewer_scope === "CATALOG_ONLY";
      viewerScope = grantingMap ? "CATALOG_AND_MAP" : "CATALOG_ONLY";
      title = grantingMap ? `Give ${member.username} map access?` : `Remove ${member.username}'s map access?`;
      explanation = grantingMap
        ? "This Viewer will be able to see the physical Library Map and saved book locations, in addition to the catalogue. Access remains read-only."
        : "This Viewer will retain read-only catalogue access, but physical locations and the Library Map will no longer be available.";
    } else if (action === "PROMOTE_TO_OWNER") {
      viewerScope = null;
      title = `Make ${member.username} an equal co-Owner?`;
      explanation = "A co-Owner receives the same authority as you: they can edit the catalogue and layout, manage members and loans, remove your own membership, export or restore data, and initiate deletion of the entire library. Only grant this role to someone you fully trust.";
    } else if (action === "DOWNGRADE_TO_VIEWER") {
      viewerScope = "CATALOG_ONLY";
      title = `Change ${member.username} from Owner to Viewer?`;
      explanation = "This person will lose all editing and member-management powers. Choose whether their remaining read-only access includes the physical Library Map.";
    } else if (action === "REMOVE") {
      viewerScope = null;
      title = `Remove ${member.username} from this library?`;
      explanation = "This immediately removes their access to the catalogue, map, covers, reading perspectives, and library membership. Their BOOKPILE account is not deleted.";
    }
    setMemberChangePassword("");
    setPendingMemberChange({ member, action, title, explanation, viewerScope });
  }

  async function confirmMemberChange(event: FormEvent) {
    event.preventDefault();
    if (!selected || !pendingMemberChange) return;
    const { member, action, viewerScope } = pendingMemberChange;
    setDataBusy(true);
    setError("");
    try {
      await serverApi.changeLibraryMember(selected.library_id, member.user_id, {
        action,
        viewer_scope: viewerScope,
        current_password: memberChangePassword,
        acknowledge_equal_owner_power: action === "PROMOTE_TO_OWNER",
      });
      setMembers(await serverApi.libraryMembers(selected.library_id));
      setMemberSummary(await serverApi.libraryMemberSummary(selected.library_id));
      setPerspectives(await serverApi.readingPerspectives(selected.library_id));
      pushNotice(`${member.username}'s membership was updated.`);
      setPendingMemberChange(null);
      setMemberChangePassword("");
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
    }
  }

  return (
    <main className={`server-account-shell ${workspace === "MAP" ? "map-active" : ""}`}>
      <header className="server-account-header">
        <a className="server-brand" href="/">
          <span className="server-brand-mark"><LibraryBig size={24} /></span>
          <span>BOOKPILE</span>
        </a>
        <nav className="server-compact-navigation" aria-label="BOOKPILE workspace controls">
          <button type="button" className={controlsPanel === "LIBRARIES" ? "active" : ""} onClick={(event) => toggleControlsPanel("LIBRARIES", event.currentTarget)}>
            <LibraryBig size={17} /><span><b>{selected?.name ?? "Choose library"}</b>{selected && <small>{selected.role === "OWNER" ? "Owner" : "Viewer"}</small>}</span><ChevronDown size={15} />
          </button>
          {selected && <button type="button" className={controlsPanel === "VIEW" ? "active" : ""} onClick={(event) => toggleControlsPanel("VIEW", event.currentTarget)}>
            {workspace === "MAP" ? <Map size={17} /> : workspace === "LAYOUT" ? <Layers3 size={17} /> : <BookOpen size={17} />}
            <span><b>{workspace === "LAYOUT" ? "Customize layout" : workspacePerspectiveLabel(workspace, user.user_id, perspectives)}</b><small>{selected.can_view_map ? "Catalogue and map" : "Catalogue only"}</small></span><ChevronDown size={15} />
          </button>}
          <span className="server-compact-identity" title="Session protected; membership checked per request"><ShieldCheck size={18} /><span><b>{user.username}</b><small>Protected session</small></span></span>
          <button type="button" className={`server-settings-trigger ${controlsPanel === "SETTINGS" ? "active" : ""}`} aria-label="Settings" title="Settings" onClick={(event) => toggleControlsPanel("SETTINGS", event.currentTarget)}><Settings2 size={19} /></button>
        </nav>
      </header>
      <section className="server-library-dashboard">
        {error && <Message kind="error">{error}</Message>}
        <TimedNoticeStack notices={notices} onDismiss={dismissNotice} />

        <div className="server-dashboard-grid">
          <aside className={`server-library-sidebar ${controlsPanel === "LIBRARIES" ? "open" : ""}`} style={anchoredPanelStyle(360, "left")}>
            <header><h2>Your libraries</h2><button type="button" onClick={() => setControlsPanel(null)} aria-label="Close libraries panel">×</button></header>
            <div className="server-library-list">
              {libraries.map((library) => (
                <button className={library.library_id === selectedId ? "active" : ""} type="button" key={library.library_id} onClick={() => { setSelectedId(library.library_id); setWorkspace("CATALOGUE"); setControlsPanel(null); }}>
                  <LibraryBig size={18} /><span><b>{library.name}</b><small>{library.role === "OWNER" ? "Owner" : library.viewer_scope === "CATALOG_AND_MAP" ? "Viewer · catalogue + map" : "Viewer · catalogue"}</small></span>
                </button>
              ))}
              {!libraries.length && <p>No libraries yet. Create your first one below.</p>}
            </div>
            <form className="server-compact-form" onSubmit={createLibrary}>
              <label>New library name<input value={libraryName} onChange={(event) => setLibraryName(event.target.value)} maxLength={160} required /></label>
              <button type="submit" disabled={dataBusy}><Plus size={17} /> Create library</button>
            </form>
            <form className="server-compact-form" onSubmit={acceptInvitation}>
              <label>Library invitation link or token<input value={invitationToken} onChange={(event) => setInvitationToken(event.target.value)} minLength={32} required /></label>
              <button type="submit" disabled={dataBusy}><Users size={17} /> Join library</button>
            </form>
          </aside>

          <div className="server-library-main">
            {selected ? <>
              {workspace === "MAP" && selected.can_view_map
                ? <ServerLibraryMap libraryId={selected.library_id} onBack={() => setWorkspace("CATALOGUE")} />
                : workspace === "LAYOUT" && selected.role === "OWNER"
                  ? <PhysicalLibraryWorkspace libraryId={selected.library_id} />
                  : <CatalogueWorkspace library={selected} memberSummary={memberSummary} signedInUserId={user.user_id} perspectives={perspectives} />}
              <section className={`server-dashboard-panel server-floating-control-panel ${controlsPanel === "VIEW" ? "open" : ""}`} style={anchoredPanelStyle(560, "right")}>
                <button className="server-floating-panel-close" type="button" onClick={() => setControlsPanel(null)} aria-label="Close view and perspective panel">×</button>
                <h3>View and reading perspective</h3>
                <nav className="server-view-choices" aria-label="Library view">
                  <button type="button" className={workspace === "CATALOGUE" ? "active" : ""} onClick={() => { setWorkspace("CATALOGUE"); setControlsPanel(null); }}><BookOpen size={17} /> Catalogue</button>
                  {selected.can_view_map && <button type="button" className={workspace === "MAP" ? "active" : ""} onClick={() => { setWorkspace("MAP"); setControlsPanel(null); }}><Map size={17} /> Library Map</button>}
                </nav>
                <p>Choose whose personal reading data is represented. Other members' perspectives are read-only.</p>
                <select value={perspectives.find((item) => item.selected)?.user_id ?? ""} onChange={(event) => void selectPerspective(event.target.value)} disabled={dataBusy}>
                  {perspectives.map((item) => <option key={item.user_id} value={item.user_id}>{item.username}{item.writable ? " · your editable perspective" : " · read only"}</option>)}
                </select>
              </section>

              <div className={`server-members-control-stack ${controlsPanel === "SETTINGS" ? "open" : ""}`} style={anchoredPanelStyle(620, "right")}>
                <button className="server-floating-panel-close" type="button" onClick={() => setControlsPanel(null)} aria-label="Close settings panel">×</button>
                <section className="server-dashboard-panel server-settings-menu">
                  <h3>Settings</h3>
                  {selected.role === "OWNER" && <button type="button" onClick={() => { setWorkspace("LAYOUT"); setControlsPanel(null); }}><Layers3 size={17} /> Customize library layout</button>}
                  <button type="button" onClick={() => void signOut(false)} disabled={busy !== null}><LogOut size={17} /> Sign out</button>
                  <button type="button" onClick={() => void signOut(true)} disabled={busy !== null}><LogOut size={17} /> Sign out from every device</button>
                </section>
                {selected.role === "OWNER" && <>
                <section className="server-dashboard-panel server-members-panel">
                  <h3>Members</h3>
                  <div className="server-member-list">{members.map((member) => <div key={member.user_id}><span><b>{member.username}</b><small>{member.role === "OWNER" ? "Equal co-Owner" : member.viewer_scope === "CATALOG_AND_MAP" ? "Viewer · catalogue + map" : "Viewer · catalogue only"}</small></span><span className="server-member-actions">{member.role === "VIEWER" ? <><button type="button" onClick={() => requestMemberChange(member, "CHANGE_VIEWER_SCOPE")}>{member.viewer_scope === "CATALOG_ONLY" ? "Give map access" : "Remove map access"}</button><button type="button" onClick={() => requestMemberChange(member, "PROMOTE_TO_OWNER")}>Make co-Owner</button></> : member.user_id !== user.user_id && <button type="button" onClick={() => requestMemberChange(member, "DOWNGRADE_TO_VIEWER")}>Make Viewer</button>}<button type="button" onClick={() => requestMemberChange(member, "REMOVE")}>Remove</button></span></div>)}</div>
                </section>
                <section className="server-dashboard-panel server-invite-panel">
                  <h3>Invite a member</h3>
                  <form className="server-invite-form" onSubmit={createInvitation}>
                    <label>Role<select value={inviteRole} onChange={(event) => { setInviteRole(event.target.value as "OWNER" | "VIEWER"); setOwnerWarning(false); }}><option value="VIEWER">Viewer</option><option value="OWNER">Equal co-Owner</option></select></label>
                    {inviteRole === "VIEWER" && <label>Access<select value={inviteScope} onChange={(event) => setInviteScope(event.target.value as typeof inviteScope)}><option value="CATALOG_ONLY">Catalogue only</option><option value="CATALOG_AND_MAP">Catalogue and map</option></select></label>}
                    {inviteRole === "OWNER" && <label className="server-check"><input type="checkbox" checked={ownerWarning} onChange={(event) => setOwnerWarning(event.target.checked)} /> I understand this person receives equal authority and may remove me.</label>}
                    <button type="submit" disabled={dataBusy}>Generate invitation</button>
                  </form>
                  {generatedLink && <div className="server-generated-invitation">
                    <label>Invitation link<span><input readOnly value={generatedLink} onFocus={(event) => event.currentTarget.select()} /><button type="button" onClick={() => void copyInvitation(generatedLink, "Invitation link")}>Copy link</button></span></label>
                    <label>Token only<span><input readOnly value={generatedToken} onFocus={(event) => event.currentTarget.select()} /><button type="button" onClick={() => void copyInvitation(generatedToken, "Invitation token")}>Copy token</button></span></label>
                  </div>}
                </section>
                </>}
              </div>
            </> : <div className="server-empty-library"><LibraryBig size={48} /><h2>Create or join a library</h2><p>Accounts and libraries are separate: an account may own or view several libraries.</p></div>}
          </div>
        </div>
      </section>
      {pendingMemberChange && <div className="server-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !dataBusy) setPendingMemberChange(null); }}>
        <section className="server-permission-dialog" role="dialog" aria-modal="true" aria-labelledby="permission-dialog-title">
          <p className="server-card-eyebrow">Permission change</p>
          <h2 id="permission-dialog-title">{pendingMemberChange.title}</h2>
          <p>{pendingMemberChange.explanation}</p>
          <form onSubmit={confirmMemberChange}>
            {pendingMemberChange.action === "DOWNGRADE_TO_VIEWER" && <label className="server-field">Viewer access<select value={pendingMemberChange.viewerScope ?? "CATALOG_ONLY"} onChange={(event) => setPendingMemberChange({ ...pendingMemberChange, viewerScope: event.target.value as "CATALOG_ONLY" | "CATALOG_AND_MAP" })}><option value="CATALOG_ONLY">Catalogue only</option><option value="CATALOG_AND_MAP">Catalogue and map</option></select></label>}
            <Field label="Your current password" icon={<LockKeyhole size={18} />} type="password" value={memberChangePassword} onChange={(event) => setMemberChangePassword(event.target.value)} autoComplete="current-password" autoFocus />
            <div className="server-dialog-actions"><button type="button" onClick={() => setPendingMemberChange(null)} disabled={dataBusy}>Cancel</button><button className={pendingMemberChange.action === "REMOVE" ? "danger" : "confirm"} type="submit" disabled={dataBusy || !memberChangePassword}>{dataBusy ? "Applying…" : "Confirm change"}</button></div>
          </form>
        </section>
      </div>}
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
