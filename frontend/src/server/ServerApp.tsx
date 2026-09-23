import { type CSSProperties, type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Download,
  KeyRound,
  Layers3,
  LibraryBig,
  LoaderCircle,
  LockKeyhole,
  Mail,
  Map,
  Plus,
  ShieldCheck,
  Trash2,
  Upload,
  Users,
  UserRound,
} from "lucide-react";
import {
  type CurrentUser,
  type LibraryMember,
  type LibraryMemberSummary,
  type LibrarySummary,
  type LocalImportJob,
  type LocalImportWarning,
  type ReadingPerspective,
  ServerApiError,
  serverApi,
} from "./serverApi";
import CatalogueWorkspace from "./CatalogueWorkspace";
import PhysicalLibraryWorkspace from "./PhysicalLibraryWorkspace";
import ServerLibraryMap from "./ServerLibraryMap";
import StatisticsWorkspace from "./StatisticsWorkspace";
import AccountWorkspace from "./AccountWorkspace";
import ProfileDialog from "./ProfileDialog";
import TimedNoticeStack from "./TimedNoticeStack";
import { useTimedNotices } from "./timedNotices";
import LocaleProvider from "./LocaleProvider";
import { type LocaleContextValue, useLocale } from "./LocaleContext";
import { availableLocales, localeNames } from "./locale";
import { libraryInvitationMessage } from "./invitationCopy";
import { authenticatedCopy } from "./authenticatedCopy";
import { type LibraryAdminCopy, libraryAdminCopy } from "./libraryAdminCopy";

type Route =
  | "login"
  | "register"
  | "verify-email"
  | "resend-verification"
  | "forgot-password"
  | "reset-password"
  | "restore-account";

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
    || route === "restore-account"
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

function localizedImportWarning(warning: LocalImportWarning, copy: LibraryAdminCopy): string {
  if (warning.code === "REPEATED_ARCHIVE") return copy("warningRepeated");
  if (warning.code === "DUPLICATE_ISBN_CANDIDATES") return copy("warningDuplicateIsbn", { count: warning.count ?? 0 });
  if (warning.code === "DUPLICATE_TITLE_AUTHOR_CANDIDATES") return copy("warningDuplicateTitle", { count: warning.count ?? 0 });
  if (warning.code === "INSUFFICIENT_SHARED_CAPACITY") return copy("warningCapacity");
  if (warning.code === "INCOMPATIBLE_MAP_COORDINATES") return copy("warningCoordinates");
  if (warning.code === "FURNITURE_NAME_CONFLICT") return copy("warningFurniture");
  if (warning.code === "OUTSIDE_AREAS_RETAINED") return copy("warningOutsideAreas");
  return copy("warningGeneric", { code: warning.code });
}

function authFriendlyError(error: unknown, t: LocaleContextValue["t"]): string {
  if (error instanceof ServerApiError) {
    if (error.status === 429) {
      const minutes = error.retryAfter ? Math.max(1, Math.ceil(error.retryAfter / 60)) : null;
      return minutes
        ? t(minutes === 1 ? "tooManyAttemptsMinutesOne" : "tooManyAttemptsMinutesMany", { minutes })
        : t("tooManyAttempts");
    }
    return t(error.status === 401 ? "invalidCredentials" : "actionFailed");
  }
  return t("serverUnavailable");
}

function AuthShell({ children }: { children: ReactNode }) {
  const { locale, setLocale, t } = useLocale();
  return (
    <main className="server-shell">
      <section className="server-story" aria-label={t("storyLabel")}>
        <a className="server-brand" href="/login">
          <span className="server-brand-mark"><LibraryBig size={24} /></span>
          <span>BOOKPILE</span>
        </a>
        <label className="server-locale-choice">
          <span>{t("languageLabel")}</span>
          <select value={locale} onChange={(event) => setLocale(event.target.value as typeof locale)}>
            {availableLocales.map((code) => <option value={code} key={code}>{localeNames[code]}</option>)}
          </select>
        </label>
        <div className="server-story-copy">
          <p className="server-eyebrow">{t("storyEyebrow")}</p>
          <h1>{t("storyTitle")}</h1>
          <p>{t("storyDescription")}</p>
        </div>
        <div className="server-books" aria-hidden="true">
          <i /><i /><i /><i /><i /><i />
          <span />
        </div>
      </section>
      <section className="server-auth-column">
        {children}
        <p className="server-phase-note">
          {t("previewNote")}
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
  const { t } = useLocale();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await serverApi.login(identifier, password, rememberMe));
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      eyebrow={t("welcomeBack")}
      title={t("signIn")}
      intro={t("loginIntro")}
    >
      <form className="server-form" onSubmit={submit}>
        <Field
          label={t("usernameOrEmail")}
          icon={<UserRound size={18} />}
          value={identifier}
          onChange={(event) => setIdentifier(event.target.value)}
          autoComplete="username"
          autoFocus
        />
        <Field
          label={t("password")}
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
          {t("keepSignedIn")}
        </label>
        {error !== null && <Message kind="error">{authFriendlyError(error, t)}</Message>}
        <SubmitButton busy={busy}>{t("signIn")} <ArrowRight size={18} /></SubmitButton>
      </form>
      <div className="server-card-links">
        <button type="button" onClick={() => navigate("forgot-password")}>{t("forgotPassword")}</button>
        <button type="button" onClick={() => navigate("resend-verification")}>{t("verifyAccount")}</button>
        <button type="button" onClick={() => navigate("register")}>{t("useInvitation")}</button>
      </div>
    </AuthCard>
  );
}

function RestoreAccountPage({
  navigate,
}: {
  navigate: (route: Route) => void;
}) {
  const { t } = useLocale();
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown | null>(null);
  const [restored, setRestored] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await serverApi.restoreAccount(token);
      window.history.replaceState({}, "", "/restore-account");
      setRestored(true);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return <AuthCard eyebrow={t("recoveryWindow")} title={t("restoreAccount")} intro={t("restoreIntro")}>
    {restored ? <>
      <Message kind="success">{t("accountRestored")}</Message>
      <button className="server-submit" type="button" onClick={() => navigate("login")}>{t("continueToSignIn")} <ArrowRight size={18} /></button>
    </> : token ? <form className="server-form" onSubmit={submit}>
      <p className="server-help">{t("restoreHelp")}</p>
      {error !== null && <Message kind="error">{authFriendlyError(error, t)}</Message>}
      <SubmitButton busy={busy}>{t("restoreAccount")} <ArrowRight size={18} /></SubmitButton>
      <div className="server-card-links single"><button type="button" onClick={() => navigate("login")}>{t("keepDeletion")}</button></div>
    </form> : <>
      <Message kind="error">{t("incompleteRecoveryLink")}</Message>
      <button className="server-submit" type="button" onClick={() => navigate("login")}>{t("returnToSignIn")}</button>
    </>}
  </AuthCard>;
}

function RegisterPage({ navigate }: { navigate: (route: Route) => void }) {
  const { locale, t } = useLocale();
  const inviteFromUrl = new URLSearchParams(window.location.search).get("invite") ?? "";
  const [invite, setInvite] = useState(inviteFromUrl);
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown | null>(null);
  const [complete, setComplete] = useState<"registrationEmailSent" | "registrationEmailFailed" | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await serverApi.register({
        invitation_token: invite.trim(),
        email,
        username,
        password,
        password_confirmation: confirmation,
        preferred_locale: locale,
      });
      window.history.replaceState({}, "", "/register");
      setComplete(result.verification_email_sent ? "registrationEmailSent" : "registrationEmailFailed");
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      eyebrow={t("invitationBeta")}
      title={t("createAccount")}
      intro={t("registrationIntro")}
    >
      {complete ? (
        <div className="server-complete">
          <CheckCircle2 size={38} />
          <p>{t(complete)}</p>
          <button className="server-submit" type="button" onClick={() => navigate("login")}>{t("continueToSignIn")}</button>
        </div>
      ) : (
        <form className="server-form" onSubmit={submit}>
          <Field label={t("invitationToken")} icon={<KeyRound size={18} />} value={invite} onChange={(event) => setInvite(event.target.value)} autoComplete="off" />
          <Field label={t("email")} icon={<Mail size={18} />} type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
          <Field label={t("username")} icon={<UserRound size={18} />} value={username} onChange={(event) => setUsername(event.target.value)} minLength={3} maxLength={30} pattern="[A-Za-z0-9_]+" autoComplete="username" />
          <Field label={t("password")} icon={<LockKeyhole size={18} />} type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} maxLength={128} autoComplete="new-password" />
          <Field label={t("confirmPassword")} icon={<LockKeyhole size={18} />} type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={12} maxLength={128} autoComplete="new-password" />
          <p className="server-help">{t("passwordHelp")}</p>
          {error !== null && <Message kind="error">{authFriendlyError(error, t)}</Message>}
          <SubmitButton busy={busy}>{t("createAccount")} <ArrowRight size={18} /></SubmitButton>
        </form>
      )}
      <div className="server-card-links single">
        <button type="button" onClick={() => navigate("login")}>{t("backToSignIn")}</button>
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
  const { t } = useLocale();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown | null>(null);
  const [complete, setComplete] = useState(false);
  const verification = mode === "verification";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (verification) await serverApi.resendVerification(email);
      else await serverApi.requestPasswordReset(email);
      setComplete(true);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      eyebrow={t(verification ? "accountVerification" : "accountRecovery")}
      title={t(verification ? "requestNewLink" : "resetYourPassword")}
      intro={verification
        ? t("verificationRequestIntro")
        : t("resetRequestIntro")}
    >
      {complete ? (
        <Message kind="success">
          {t("genericEmailResponse")}
        </Message>
      ) : (
        <form className="server-form" onSubmit={submit}>
          <Field label={t("email")} icon={<Mail size={18} />} type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" autoFocus />
          {error !== null && <Message kind="error">{authFriendlyError(error, t)}</Message>}
          <SubmitButton busy={busy}>{t("sendLink")} <ArrowRight size={18} /></SubmitButton>
        </form>
      )}
      <div className="server-card-links single">
        <button type="button" onClick={() => navigate("login")}>{t("backToSignIn")}</button>
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
  const { t } = useLocale();
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown | "invalidToken" | null>(null);
  const [complete, setComplete] = useState(false);
  const verification = mode === "verification";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) {
      setError("invalidToken");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (verification) await serverApi.verifyEmail(token);
      else await serverApi.resetPassword(token, password, confirmation);
      window.history.replaceState({}, "", verification ? "/verify-email" : "/reset-password");
      setComplete(true);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      eyebrow={t(verification ? "confirmAddress" : "chooseNewPassword")}
      title={t(verification ? "verifyEmail" : "resetPassword")}
      intro={verification
        ? t("verifyEmailIntro")
        : t("resetPasswordIntro")}
    >
      {complete ? (
        <div className="server-complete">
          <CheckCircle2 size={38} />
          <p>{t(verification ? "emailVerified" : "passwordChanged")}</p>
          <button className="server-submit" type="button" onClick={() => navigate("login")}>{t("continueToSignIn")}</button>
        </div>
      ) : (
        <form className="server-form" onSubmit={submit}>
          {!verification && (
            <>
              <Field label={t("newPassword")} icon={<LockKeyhole size={18} />} type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} maxLength={128} autoComplete="new-password" autoFocus />
              <Field label={t("confirmNewPassword")} icon={<LockKeyhole size={18} />} type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={12} maxLength={128} autoComplete="new-password" />
            </>
          )}
          {error !== null && <Message kind="error">{error === "invalidToken" ? t("invalidToken") : authFriendlyError(error, t)}</Message>}
          <SubmitButton busy={busy}>{t(verification ? "verifyMyEmail" : "changePassword")} <ArrowRight size={18} /></SubmitButton>
        </form>
      )}
      <div className="server-card-links single">
        <button type="button" onClick={() => navigate("login")}>{t("backToSignIn")}</button>
      </div>
    </AuthCard>
  );
}

function AccountHome({ user, onSignedOut }: { user: CurrentUser; onSignedOut: () => void }) {
  const { locale } = useLocale();
  const [, setBusy] = useState<"logout" | "all" | null>(null);
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
  const [invitationLocale, setInvitationLocale] = useState(locale);
  const [ownerWarning, setOwnerWarning] = useState(false);
  const [generatedInvitation, setGeneratedInvitation] = useState<{
    link: string;
    libraryName: string;
    role: "OWNER" | "VIEWER";
    scope: "CATALOG_ONLY" | "CATALOG_AND_MAP" | null;
  } | null>(null);
  const [dataBusy, setDataBusy] = useState(false);
  const [pendingMemberChange, setPendingMemberChange] = useState<PendingMemberChange | null>(null);
  const [memberChangePassword, setMemberChangePassword] = useState("");
  const [workspace, setWorkspace] = useState<"CATALOGUE" | "MAP" | "STATISTICS" | "LAYOUT" | "ACCOUNT">("CATALOGUE");
  const workspaceLocale = workspace === "ACCOUNT" || workspace === "CATALOGUE" || workspace === "STATISTICS" ? locale : "en";
  const copy = authenticatedCopy(workspaceLocale);
  const adminCopy = libraryAdminCopy(workspaceLocale);
  const [controlsPanel, setControlsPanel] = useState<"LIBRARIES" | "VIEW" | "LIBRARY_SETTINGS" | null>(null);
  const [panelAnchor, setPanelAnchor] = useState<PanelAnchor | null>(null);
  const [profileUserId, setProfileUserId] = useState<string | null>(null);
  const [settingsSection, setSettingsSection] = useState<"ROOT" | "MEMBERS" | "DATA">("ROOT");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importSourceKind, setImportSourceKind] = useState<"LOCAL" | "SERVER">("LOCAL");
  const [importReadingOwner, setImportReadingOwner] = useState("");
  const [importJob, setImportJob] = useState<LocalImportJob | null>(null);
  const [importMemberMapping, setImportMemberMapping] = useState<Record<string, string>>({});
  const [newImportSourceMember, setNewImportSourceMember] = useState("");
  const [allowUnmappedPersonalData, setAllowUnmappedPersonalData] = useState(false);
  const [allowRepeatedImport, setAllowRepeatedImport] = useState(false);
  const [newImportLibraryName, setNewImportLibraryName] = useState("");
  const [importOperation, setImportOperation] = useState<"" | "INSPECTING" | "IMPORTING" | "IMPORTING_NEW">("");
  const [libraryRevision, setLibraryRevision] = useState(0);
  const [deleteTarget, setDeleteTarget] = useState<LibrarySummary | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteAcknowledged, setDeleteAcknowledged] = useState(false);

  const selected = libraries.find((library) => library.library_id === selectedId) ?? null;
  const importPersonalMembers = importJob?.source_kind === "SERVER"
    ? importJob.source_members.filter((member) => member.reading_count > 0 || member.review_count > 0)
    : [];
  const hasUnmappedPersonalData = importPersonalMembers.some(
    (member) => !importMemberMapping[member.member_key],
  );
  const hasUnmappedPersonalDataForNewLibrary = importPersonalMembers.some(
    (member) => member.member_key !== newImportSourceMember,
  );
  const mappedOwnerIds = Object.values(importMemberMapping).filter(Boolean);
  const hasDuplicateMappedOwner = new Set(mappedOwnerIds).size !== mappedOwnerIds.length;
  const hasBlockingServerConflict = importJob?.warnings.some(
    (warning) => ["INCOMPATIBLE_MAP_COORDINATES", "FURNITURE_NAME_CONFLICT"].includes(warning.code),
  ) ?? false;

  useEffect(() => {
    document.documentElement.lang = workspaceLocale;
  }, [workspaceLocale]);

  function localizedWorkspaceLabel() {
    const view = workspace === "MAP"
      ? copy("libraryMap")
      : workspace === "STATISTICS"
        ? copy("statistics")
        : copy("catalogue");
    const perspective = perspectives.find((item) => item.selected) ?? perspectives[0];
    return !perspective || perspective.user_id === user.user_id
      ? `${view} — ${workspaceLocale === "gl" ? "eu" : "self"}`
      : `${view} — ${perspective.username}`;
  }

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
    setGeneratedInvitation(null);
    setImportFile(null);
    setImportJob(null);
    setImportMemberMapping({});
    setNewImportSourceMember("");
    setAllowUnmappedPersonalData(false);
    setAllowRepeatedImport(false);
    setImportReadingOwner("");
    setNewImportLibraryName("");
    setImportOperation("");
  }, [selected?.library_id]);

  useEffect(() => {
    if (importReadingOwner && members.some((item) => item.user_id === importReadingOwner && item.role === "OWNER")) return;
    setImportReadingOwner(
      members.find((item) => item.user_id === user.user_id && item.role === "OWNER")?.user_id
      ?? members.find((item) => item.role === "OWNER")?.user_id
      ?? "",
    );
  }, [members, importReadingOwner, user.user_id]);

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
      pushNotice(adminCopy("libraryCreated", { name: created.name }));
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
      pushNotice(adminCopy(accepted.role === "OWNER" ? "joinedOwner" : "joinedViewer", { name: accepted.name }));
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
      setGeneratedInvitation({
        link: url.toString(),
        libraryName: selected.name,
        role: inviteRole,
        scope: inviteRole === "VIEWER" ? inviteScope : null,
      });
      pushNotice(adminCopy("invitationReadyNotice"));
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
      pushNotice(adminCopy("copied", { label }));
    } catch {
      setError(adminCopy("clipboardFailed"));
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
    let title = adminCopy("updateMembership");
    let explanation = adminCopy("confirmAccessChange");
    let viewerScope: PendingMemberChange["viewerScope"] = member.viewer_scope;
    if (action === "CHANGE_VIEWER_SCOPE") {
      const grantingMap = member.viewer_scope === "CATALOG_ONLY";
      viewerScope = grantingMap ? "CATALOG_AND_MAP" : "CATALOG_ONLY";
      title = adminCopy(grantingMap ? "giveMapTitle" : "removeMapTitle", { username: member.username });
      explanation = grantingMap
        ? adminCopy("giveMapHelp")
        : adminCopy("removeMapHelp");
    } else if (action === "PROMOTE_TO_OWNER") {
      viewerScope = null;
      title = adminCopy("promoteTitle", { username: member.username });
      explanation = adminCopy("promoteHelp");
    } else if (action === "DOWNGRADE_TO_VIEWER") {
      viewerScope = "CATALOG_ONLY";
      title = adminCopy("downgradeTitle", { username: member.username });
      explanation = adminCopy("downgradeHelp");
    } else if (action === "REMOVE") {
      viewerScope = null;
      title = adminCopy("removeTitle", { username: member.username });
      explanation = adminCopy("removeHelp");
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
      pushNotice(adminCopy("memberUpdated", { username: member.username }));
      setPendingMemberChange(null);
      setMemberChangePassword("");
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
    }
  }

  async function confirmLibraryDeletion(event: FormEvent) {
    event.preventDefault();
    if (!deleteTarget) return;
    setDataBusy(true);
    setError("");
    try {
      const deleted = await serverApi.deleteLibrary(deleteTarget.library_id, {
        current_password: deletePassword,
        confirmation_name: deleteConfirmation,
        acknowledge_permanent_deletion: deleteAcknowledged,
      });
      setDeleteTarget(null);
      setDeletePassword("");
      setDeleteConfirmation("");
      setDeleteAcknowledged(false);
      setControlsPanel(null);
      setWorkspace("ACCOUNT");
      await reloadLibraries();
      pushNotice(adminCopy("libraryDeleted", { name: deleted.name }));
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
    }
  }

  async function preflightBackup(event: FormEvent) {
    event.preventDefault();
    if (!selected || !importFile || (importSourceKind === "LOCAL" && !importReadingOwner)) return;
    setDataBusy(true);
    setImportOperation("INSPECTING");
    setError("");
    try {
      const inspected = importSourceKind === "SERVER"
        ? await serverApi.preflightServerImport(selected.library_id, importFile)
        : await serverApi.preflightLocalImport(selected.library_id, importFile, importReadingOwner);
      setImportJob(inspected);
      setNewImportLibraryName(inspected.source_library_name ?? "");
      setImportMemberMapping({});
      setNewImportSourceMember("");
      setAllowUnmappedPersonalData(false);
      setAllowRepeatedImport(false);
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
      setImportOperation("");
    }
  }

  async function cancelLocalBackup() {
    if (!selected || !importJob) return;
    setDataBusy(true);
    setError("");
    try {
      await serverApi.cancelLocalImport(selected.library_id, importJob.import_id);
      setImportJob(null);
      setImportFile(null);
      setImportMemberMapping({});
      setNewImportSourceMember("");
      setAllowUnmappedPersonalData(false);
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
      setImportOperation("");
    }
  }

  async function consolidateLocalBackupAsNewLibrary(event: FormEvent) {
    event.preventDefault();
    if (!selected || !importJob || !newImportLibraryName.trim()) return;
    setDataBusy(true);
    setImportOperation("IMPORTING_NEW");
    setError("");
    try {
      const completed = await serverApi.consolidateLocalImportAsNewLibrary(
        selected.library_id,
        importJob.import_id,
        newImportLibraryName.trim(),
        allowRepeatedImport,
        importJob.source_kind === "SERVER" && newImportSourceMember
          ? { [newImportSourceMember]: user.user_id }
          : {},
        allowUnmappedPersonalData,
      );
      const createdName = newImportLibraryName.trim();
      setImportFile(null);
      setImportJob(completed);
      setNewImportLibraryName("");
      setControlsPanel(null);
      setSettingsSection("ROOT");
      setWorkspace("CATALOGUE");
      await reloadLibraries(completed.library_id);
      pushNotice(adminCopy("newLibraryImported", { name: createdName, source: adminCopy(importJob.source_kind === "SERVER" ? "sourceServer" : "sourceLocal") }));
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
      setImportOperation("");
    }
  }

  async function consolidateLocalBackup() {
    if (!selected || !importJob) return;
    setDataBusy(true);
    setImportOperation("IMPORTING");
    setError("");
    try {
      const completed = await serverApi.consolidateLocalImport(
        selected.library_id,
        importJob.import_id,
        allowRepeatedImport,
        importJob.source_kind === "SERVER" ? importMemberMapping : {},
        allowUnmappedPersonalData,
      );
      setImportJob(completed);
      setImportFile(null);
      setLibraryRevision((value) => value + 1);
      await reloadLibraries(selected.library_id);
      pushNotice(adminCopy("existingLibraryImported", { name: selected.name, source: adminCopy(importJob.source_kind === "SERVER" ? "sourceServer" : "sourceLocal") }));
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setDataBusy(false);
      setImportOperation("");
    }
  }

  function downloadPortableExport() {
    if (!selected) return;
    const link = document.createElement("a");
    link.href = serverApi.portableExportUrl(selected.library_id);
    link.download = "";
    document.body.appendChild(link);
    link.click();
    link.remove();
    pushNotice(adminCopy("preparingExport", { name: selected.name }));
  }

  return (
    <main className={`server-account-shell ${workspace === "MAP" ? "map-active" : ""}`}>
      <header className="server-account-header">
        <a className="server-brand" href="/">
          <span className="server-brand-mark"><LibraryBig size={24} /></span>
          <span>BOOKPILE</span>
        </a>
        <nav className="server-compact-navigation" aria-label={copy("navControls")}>
          <button type="button" className={controlsPanel === "LIBRARIES" ? "active" : ""} onClick={(event) => toggleControlsPanel("LIBRARIES", event.currentTarget)}>
            <LibraryBig size={17} /><span><b>{selected?.name ?? copy("chooseLibrary")}</b>{selected && <small>{selected.role === "OWNER" ? copy("owner") : copy("viewer")}</small>}</span><ChevronDown size={15} />
          </button>
          {selected && <button type="button" className={controlsPanel === "VIEW" ? "active" : ""} onClick={(event) => { if (workspace === "ACCOUNT") setWorkspace("CATALOGUE"); toggleControlsPanel("VIEW", event.currentTarget); }}>
            {workspace === "ACCOUNT" ? <UserRound size={17} /> : workspace === "MAP" ? <Map size={17} /> : workspace === "STATISTICS" ? <BarChart3 size={17} /> : workspace === "LAYOUT" ? <Layers3 size={17} /> : <BookOpen size={17} />}
            <span><b>{workspace === "ACCOUNT" ? copy("myProfile") : workspace === "LAYOUT" ? copy("customizeLayout") : localizedWorkspaceLabel()}</b><small>{workspace === "ACCOUNT" ? copy("privateAccount") : selected.can_view_map ? copy("catalogueAndMap") : copy("catalogueOnly")}</small></span><ChevronDown size={15} />
          </button>}
          <button type="button" className={`server-compact-identity ${workspace === "ACCOUNT" ? "active" : ""}`} title={copy("openPrivateProfile")} onClick={() => { setWorkspace("ACCOUNT"); setControlsPanel(null); }}><ShieldCheck size={18} /><span><b>{user.username}</b><small>{copy("protectedSession")}</small></span></button>
        </nav>
      </header>
      <section className="server-library-dashboard">
        {error && <Message kind="error">{error}</Message>}
        <TimedNoticeStack notices={notices} onDismiss={dismissNotice} />

        <div className="server-dashboard-grid">
          <aside className={`server-library-sidebar ${controlsPanel === "LIBRARIES" ? "open" : ""}`} style={anchoredPanelStyle(360, "left")}>
            <header><h2>{copy("yourLibraries")}</h2><button type="button" onClick={() => setControlsPanel(null)} aria-label={copy("closeLibraries")}>×</button></header>
            <div className="server-library-list">
              {libraries.map((library) => (
                <button className={library.library_id === selectedId ? "active" : ""} type="button" key={library.library_id} onClick={() => { setSelectedId(library.library_id); setWorkspace("CATALOGUE"); setControlsPanel(null); }}>
                  <LibraryBig size={18} /><span><b>{library.name}</b><small>{library.role === "OWNER" ? copy("owner") : library.viewer_scope === "CATALOG_AND_MAP" ? copy("viewerCatalogueMap") : copy("viewerCatalogue")}</small></span>
                </button>
              ))}
              {!libraries.length && <p>{copy("noLibraries")}</p>}
            </div>
            {selected?.role === "OWNER" && <button className="server-library-settings-link" type="button" onClick={(event) => { setWorkspace("CATALOGUE"); setSettingsSection("ROOT"); toggleControlsPanel("LIBRARY_SETTINGS", event.currentTarget); }}><Layers3 size={17} /><span><b>{copy("librarySettings")}</b><small>{copy("librarySettingsHelp")}</small></span></button>}
            <form className="server-compact-form" onSubmit={createLibrary}>
              <label>{copy("newLibraryName")}<input value={libraryName} onChange={(event) => setLibraryName(event.target.value)} maxLength={160} required /></label>
              <button type="submit" disabled={dataBusy}><Plus size={17} /> {copy("createLibrary")}</button>
            </form>
            <form className="server-compact-form" onSubmit={acceptInvitation}>
              <label>{copy("libraryInvitation")}<input value={invitationToken} onChange={(event) => setInvitationToken(event.target.value)} minLength={32} required /></label>
              <button type="submit" disabled={dataBusy}><Users size={17} /> {copy("joinLibrary")}</button>
            </form>
          </aside>

          <div className="server-library-main">
            {workspace === "ACCOUNT" ? <AccountWorkspace onSignOut={signOut} onLibrariesChanged={reloadLibraries} onAccountDeleted={onSignedOut} /> : selected ? <>
              {workspace === "MAP" && selected.can_view_map
                ? <ServerLibraryMap key={`${selected.library_id}-${libraryRevision}`} libraryId={selected.library_id} perspective={perspectives.find((item) => item.selected) ?? perspectives[0] ?? null} onBack={() => setWorkspace("CATALOGUE")} />
                : workspace === "STATISTICS" && (perspectives.find((item) => item.selected) ?? perspectives[0])
                  ? <StatisticsWorkspace libraryId={selected.library_id} perspective={(perspectives.find((item) => item.selected) ?? perspectives[0])!} locale={workspaceLocale} />
                : workspace === "LAYOUT" && selected.role === "OWNER"
                  ? <PhysicalLibraryWorkspace key={`${selected.library_id}-${libraryRevision}`} libraryId={selected.library_id} />
                  : <CatalogueWorkspace key={`${selected.library_id}-${libraryRevision}`} library={selected} memberSummary={memberSummary} signedInUserId={user.user_id} perspectives={perspectives} locale={workspaceLocale} onOpenProfile={setProfileUserId} onSetUpMap={() => setWorkspace("LAYOUT")} />}
              <section className={`server-dashboard-panel server-floating-control-panel ${controlsPanel === "VIEW" ? "open" : ""}`} style={anchoredPanelStyle(560, "right")}>
                <button className="server-floating-panel-close" type="button" onClick={() => setControlsPanel(null)} aria-label={copy("closeViewPanel")}>×</button>
                <h3>{copy("viewPerspective")}</h3>
                <nav className="server-view-choices" aria-label={copy("libraryView")}>
                  <button type="button" className={workspace === "CATALOGUE" ? "active" : ""} onClick={() => { setWorkspace("CATALOGUE"); setControlsPanel(null); }}><BookOpen size={17} /> {copy("catalogue")}</button>
                  {selected.can_view_map && <button type="button" className={workspace === "MAP" ? "active" : ""} onClick={() => { setWorkspace("MAP"); setControlsPanel(null); }}><Map size={17} /> {copy("libraryMap")}</button>}
                  <button type="button" className={workspace === "STATISTICS" ? "active" : ""} onClick={() => { setWorkspace("STATISTICS"); setControlsPanel(null); }}><BarChart3 size={17} /> {copy("statistics")}</button>
                </nav>
                <p>{copy("perspectiveHelp")}</p>
                <select value={perspectives.find((item) => item.selected)?.user_id ?? ""} onChange={(event) => void selectPerspective(event.target.value)} disabled={dataBusy}>
                  {perspectives.map((item) => <option key={item.user_id} value={item.user_id}>{item.username} · {item.writable ? copy("editablePerspective") : copy("readOnly")}</option>)}
                </select>
                <div className="server-perspective-profiles"><small>{copy("memberProfiles")}</small>{perspectives.map((item) => <button key={item.user_id} type="button" onClick={() => setProfileUserId(item.user_id)}>@{item.username}</button>)}</div>
              </section>

              <div className={`server-members-control-stack ${controlsPanel === "LIBRARY_SETTINGS" ? "open" : ""}`}>
                <button className="server-floating-panel-close" type="button" onClick={() => setControlsPanel(null)} aria-label={adminCopy("closeSettings")}>×</button>
                <section className="server-dashboard-panel server-settings-menu">
                  <h3>{adminCopy("settingsTitle", { name: selected.name })}</h3>
                  {selected.role === "OWNER" && <>
                    <button type="button" onClick={() => { setWorkspace("LAYOUT"); setControlsPanel(null); }}><Layers3 size={17} /><span><b>{adminCopy("manageStructure")}</b><small>{adminCopy("manageStructureHelp")}</small></span></button>
                    <button type="button" onClick={() => setSettingsSection(settingsSection === "MEMBERS" ? "ROOT" : "MEMBERS")}><Users size={17} /><span><b>{adminCopy("manageMembers")}</b><small>{adminCopy("manageMembersHelp")}</small></span></button>
                    <button type="button" onClick={() => setSettingsSection(settingsSection === "DATA" ? "ROOT" : "DATA")}><Download size={17} /><span><b>{adminCopy("dataPortability")}</b><small>{adminCopy("dataPortabilityHelp")}</small></span></button>
                    <button className="danger" type="button" onClick={() => { setDeleteTarget(selected); setControlsPanel(null); }}><Trash2 size={17} /><span><b>{adminCopy("deleteLibrary")}</b><small>{adminCopy("deleteLibraryMenuHelp")}</small></span></button>
                  </>}
                </section>
                {selected.role === "OWNER" && settingsSection === "MEMBERS" && <>
                <section className="server-dashboard-panel server-members-panel">
                  <h3>{adminCopy("manageMembers")}</h3>
                  <div className="server-member-list">{members.map((member) => <div key={member.user_id}><span><button className="server-username-link" type="button" onClick={() => setProfileUserId(member.user_id)}>@{member.username}</button><small>{adminCopy(member.role === "OWNER" ? "equalCoOwner" : member.viewer_scope === "CATALOG_AND_MAP" ? "viewerCatalogueMap" : "viewerCatalogueOnly")}</small></span><span className="server-member-actions">{member.role === "VIEWER" ? <><button type="button" onClick={() => requestMemberChange(member, "CHANGE_VIEWER_SCOPE")}>{adminCopy(member.viewer_scope === "CATALOG_ONLY" ? "giveMapAccess" : "removeMapAccess")}</button><button type="button" onClick={() => requestMemberChange(member, "PROMOTE_TO_OWNER")}>{adminCopy("makeCoOwner")}</button></> : member.user_id !== user.user_id && <button type="button" onClick={() => requestMemberChange(member, "DOWNGRADE_TO_VIEWER")}>{adminCopy("makeViewer")}</button>}<button type="button" onClick={() => requestMemberChange(member, "REMOVE")}>{adminCopy("remove")}</button></span></div>)}</div>
                </section>
                <section className="server-dashboard-panel server-invite-panel">
                  <h4>{adminCopy("inviteMember")}</h4>
                  <form className="server-invite-form" onSubmit={createInvitation}>
                    <label>{adminCopy("role")}<select value={inviteRole} onChange={(event) => { setInviteRole(event.target.value as "OWNER" | "VIEWER"); setOwnerWarning(false); }}><option value="VIEWER">{adminCopy("viewer")}</option><option value="OWNER">{adminCopy("equalCoOwner")}</option></select></label>
                    {inviteRole === "VIEWER" && <label>{adminCopy("access")}<select value={inviteScope} onChange={(event) => setInviteScope(event.target.value as typeof inviteScope)}><option value="CATALOG_ONLY">{adminCopy("catalogueOnly")}</option><option value="CATALOG_AND_MAP">{adminCopy("catalogueMap")}</option></select></label>}
                    <label>{adminCopy("invitationLanguage")}<select value={invitationLocale} onChange={(event) => setInvitationLocale(event.target.value as typeof invitationLocale)}>{availableLocales.map((code) => <option value={code} key={code}>{localeNames[code]}</option>)}</select></label>
                    {inviteRole === "OWNER" && <label className="server-check"><input type="checkbox" checked={ownerWarning} onChange={(event) => setOwnerWarning(event.target.checked)} /> {adminCopy("ownerAcknowledgement")}</label>}
                    <button type="submit" disabled={dataBusy}>{adminCopy("generateInvitation")}</button>
                  </form>
                  {generatedInvitation && <div className="server-generated-invitation">
                    <label>{adminCopy("invitationMessage")}<textarea readOnly value={libraryInvitationMessage(invitationLocale, generatedInvitation.link, generatedInvitation.libraryName, generatedInvitation.role, generatedInvitation.scope)} onFocus={(event) => event.currentTarget.select()} /></label>
                    <div className="server-invitation-copy-actions"><button type="button" onClick={() => void copyInvitation(libraryInvitationMessage(invitationLocale, generatedInvitation.link, generatedInvitation.libraryName, generatedInvitation.role, generatedInvitation.scope), adminCopy("invitationMessageLabel"))}>{adminCopy("copyMessage")}</button><button type="button" onClick={() => void copyInvitation(generatedInvitation.link, adminCopy("invitationLinkLabel"))}>{adminCopy("copyLinkOnly")}</button></div>
                  </div>}
                </section>
                </>}
                {selected.role === "OWNER" && settingsSection === "DATA" && <section className="server-dashboard-panel server-portability-panel">
                  <h3>{adminCopy("dataPortability")}</h3>
                  <div className="server-portability-block">
                    <h4><Download size={17} /> {adminCopy("exportTitle", { name: selected.name })}</h4>
                    <p>{adminCopy("exportHelp")}</p>
                    <button type="button" onClick={downloadPortableExport}><Download size={17} /> {adminCopy("downloadZip")}</button>
                  </div>
                  <div className="server-portability-block">
                    <h4><Upload size={17} /> {adminCopy("importTitle")}</h4>
                    <p>{adminCopy("importHelp")}</p>
                    {!importJob && <form className="server-portability-form" onSubmit={preflightBackup}>
                      <label>{adminCopy("zipSource")}<select value={importSourceKind} onChange={(event) => { setImportSourceKind(event.target.value as "LOCAL" | "SERVER"); setImportFile(null); }}><option value="LOCAL">{adminCopy("localBackup")}</option><option value="SERVER">{adminCopy("serverExport")}</option></select></label>
                      <label>{adminCopy(importSourceKind === "LOCAL" ? "localZip" : "serverZip")}<input key={importSourceKind} type="file" accept=".zip,application/zip" onChange={(event) => setImportFile(event.target.files?.[0] ?? null)} required /></label>
                      {importSourceKind === "LOCAL" && <label>{adminCopy("readingOwner")}<select value={importReadingOwner} onChange={(event) => setImportReadingOwner(event.target.value)} required>{members.filter((item) => item.role === "OWNER").map((item) => <option key={item.user_id} value={item.user_id}>@{item.username}{item.user_id === user.user_id ? ` · ${adminCopy("you")}` : ""}</option>)}</select></label>}
                      <button type="submit" disabled={dataBusy || !importFile || (importSourceKind === "LOCAL" && !importReadingOwner)}>{adminCopy(dataBusy ? "inspecting" : "inspectZip")}</button>
                      <small>{adminCopy("importLimit")}</small>
                    </form>}
                    {importOperation === "INSPECTING" && <div className="server-import-progress" role="status" aria-live="polite"><b>{adminCopy("uploading")}</b><span aria-hidden="true"><i /></span><small>{adminCopy("uploadingHelp")}</small></div>}
                    {importJob?.state === "READY" && <div className="server-import-report" role="status">
                      <h4>{adminCopy("readyReview")}</h4>
                      <p>{importJob.source_kind === "SERVER" ? adminCopy("exportDescription", { name: importJob.source_library_name ?? "" }) : adminCopy("localDescription")} · format {importJob.backup_format_version}, schema {importJob.local_schema_version} · {adminCopy("created")} {new Date(importJob.source_created_at).toLocaleString(workspaceLocale === "gl" ? "gl-ES" : "en-GB")}</p>
                      <dl>{[
                        ["books", "countBooks"], ["bookcases", "countBookcases"], ["shelves", "countShelves"], ["containers", "countContainers"],
                        [importJob.source_kind === "SERVER" ? "contributors" : "book_authors", importJob.source_kind === "SERVER" ? "countContributors" : "countAuthors"],
                        [importJob.source_kind === "SERVER" ? "readings" : "reading_sessions", "countReadings"], ["loans", "countLoans"], ["covers", "countCovers"],
                      ].map(([key, label]) => <div key={key}><dt>{adminCopy(label as Parameters<typeof adminCopy>[0])}</dt><dd>{importJob.counts[key] ?? 0}</dd></div>)}</dl>
                      {importJob.warnings.map((warning) => <p className="server-import-warning" key={warning.code}>{localizedImportWarning(warning, adminCopy)}</p>)}
                      {!importJob.capacity_available && <Message kind="error">{adminCopy("capacityError")}</Message>}
                      {importJob.warnings.some((warning) => warning.code === "REPEATED_ARCHIVE") && <label className="server-check"><input type="checkbox" checked={allowRepeatedImport} onChange={(event) => setAllowRepeatedImport(event.target.checked)} /> {adminCopy("repeatedArchive")}</label>}
                      {importJob.source_kind === "SERVER" && <div className="server-import-member-map">
                        <h4>{adminCopy("personalDataTitle", { name: selected.name })}</h4>
                        <p>{adminCopy("personalDataHelp")}</p>
                        {importJob.source_members.map((source) => <label key={source.member_key}>{adminCopy("sourcePersonalCounts", { username: source.username, readings: source.reading_count, records: source.review_count })}<select value={importMemberMapping[source.member_key] ?? ""} onChange={(event) => setImportMemberMapping((current) => ({ ...current, [source.member_key]: event.target.value }))}><option value="">{adminCopy("doNotRestorePersonal")}</option>{members.filter((item) => item.role === "OWNER").map((owner) => <option key={owner.user_id} value={owner.user_id} disabled={Object.entries(importMemberMapping).some(([key, value]) => key !== source.member_key && value === owner.user_id)}>@{owner.username}{owner.user_id === user.user_id ? ` · ${adminCopy("you")}` : ""}</option>)}</select></label>)}
                        {hasDuplicateMappedOwner && <Message kind="error">{adminCopy("duplicateOwner")}</Message>}
                        {hasUnmappedPersonalData && <label className="server-check"><input type="checkbox" checked={allowUnmappedPersonalData} onChange={(event) => setAllowUnmappedPersonalData(event.target.checked)} /> {adminCopy("omitUnmapped")}</label>}
                      </div>}
                      {importOperation && importOperation !== "INSPECTING" && <div className="server-import-progress" role="status" aria-live="polite"><b>{adminCopy(importOperation === "IMPORTING_NEW" ? "creatingImport" : "importing")}</b><span aria-hidden="true"><i /></span><small>{adminCopy("processingImport", { books: importJob.counts.books ?? 0, covers: importJob.counts.covers ?? 0, readings: importJob.counts[importJob.source_kind === "SERVER" ? "readings" : "reading_sessions"] ?? 0, loans: importJob.counts.loans ?? 0 })}</small></div>}
                      <div className="server-dialog-actions"><button type="button" onClick={() => void cancelLocalBackup()} disabled={dataBusy}>{adminCopy("cancelStaging")}</button><button className="confirm" type="button" onClick={() => void consolidateLocalBackup()} disabled={dataBusy || !importJob.capacity_available || hasBlockingServerConflict || hasDuplicateMappedOwner || (hasUnmappedPersonalData && !allowUnmappedPersonalData) || (importJob.warnings.some((warning) => warning.code === "REPEATED_ARCHIVE") && !allowRepeatedImport)}>{adminCopy(importOperation === "IMPORTING" ? "importing" : importJob.source_kind === "SERVER" ? "restoreHere" : "importHere")}</button></div>
                      <form className="server-import-new-library" onSubmit={consolidateLocalBackupAsNewLibrary}>
                        <label>{adminCopy("createSeparate")}<input value={newImportLibraryName} onChange={(event) => setNewImportLibraryName(event.target.value)} maxLength={160} placeholder={adminCopy("newLibraryName")} required /></label>
                        {importJob.source_kind === "SERVER" && <label>{adminCopy("sourceIdentity")}<select value={newImportSourceMember} onChange={(event) => setNewImportSourceMember(event.target.value)}><option value="">{adminCopy("noneOmitPersonal")}</option>{importJob.source_members.map((source) => <option key={source.member_key} value={source.member_key}>{adminCopy("sourceReadings", { username: source.username, readings: source.reading_count })}</option>)}</select></label>}
                        {importJob.source_kind === "SERVER" && hasUnmappedPersonalDataForNewLibrary && <label className="server-check"><input type="checkbox" checked={allowUnmappedPersonalData} onChange={(event) => setAllowUnmappedPersonalData(event.target.checked)} /> {adminCopy("omitOtherMembers")}</label>}
                        <button type="submit" disabled={dataBusy || !newImportLibraryName.trim() || (importJob.source_kind === "SERVER" && hasUnmappedPersonalDataForNewLibrary && !allowUnmappedPersonalData) || (importJob.warnings.some((warning) => warning.code === "REPEATED_ARCHIVE") && !allowRepeatedImport)}>{adminCopy(importOperation === "IMPORTING_NEW" ? "creatingAndImporting" : "importAsNew")}</button>
                        <small>{adminCopy("newOwnerHelp")}</small>
                      </form>
                    </div>}
                    {importJob?.state === "IMPORTED" && <Message kind="success">{adminCopy("importComplete", { books: importJob.result_counts?.books ?? 0 })}</Message>}
                  </div>
                </section>}
              </div>
            </> : <div className="server-empty-library"><LibraryBig size={48} /><h2>{adminCopy("emptyTitle")}</h2><p>{adminCopy("emptyHelp")}</p></div>}
          </div>
        </div>
      </section>
      {pendingMemberChange && <div className="server-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !dataBusy) setPendingMemberChange(null); }}>
        <section className="server-permission-dialog" role="dialog" aria-modal="true" aria-labelledby="permission-dialog-title">
          <p className="server-card-eyebrow">{adminCopy("permissionChange")}</p>
          <h2 id="permission-dialog-title">{pendingMemberChange.title}</h2>
          <p>{pendingMemberChange.explanation}</p>
          <form onSubmit={confirmMemberChange}>
            {pendingMemberChange.action === "DOWNGRADE_TO_VIEWER" && <label className="server-field">{adminCopy("viewerAccess")}<select value={pendingMemberChange.viewerScope ?? "CATALOG_ONLY"} onChange={(event) => setPendingMemberChange({ ...pendingMemberChange, viewerScope: event.target.value as "CATALOG_ONLY" | "CATALOG_AND_MAP" })}><option value="CATALOG_ONLY">{adminCopy("catalogueOnly")}</option><option value="CATALOG_AND_MAP">{adminCopy("catalogueMap")}</option></select></label>}
            <Field label={adminCopy("currentPassword")} icon={<LockKeyhole size={18} />} type="password" value={memberChangePassword} onChange={(event) => setMemberChangePassword(event.target.value)} autoComplete="current-password" autoFocus />
            <div className="server-dialog-actions"><button type="button" onClick={() => setPendingMemberChange(null)} disabled={dataBusy}>{adminCopy("cancel")}</button><button className={pendingMemberChange.action === "REMOVE" ? "danger" : "confirm"} type="submit" disabled={dataBusy || !memberChangePassword}>{adminCopy(dataBusy ? "applying" : "confirmChange")}</button></div>
          </form>
        </section>
      </div>}
      {deleteTarget && <div className="server-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !dataBusy) setDeleteTarget(null); }}>
        <section className="server-permission-dialog server-delete-library-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-library-title">
          <p className="server-card-eyebrow">{adminCopy("dangerZone")}</p>
          <h2 id="delete-library-title">{adminCopy("deleteTitle", { name: deleteTarget.name })}</h2>
          <p>{adminCopy("deleteHelp")}</p>
          <form onSubmit={confirmLibraryDeletion}>
            <label>{adminCopy("typeExactly", { name: deleteTarget.name })}<input required value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} autoFocus /></label>
            <Field label={adminCopy("currentPassword")} icon={<LockKeyhole size={18} />} type="password" value={deletePassword} onChange={(event) => setDeletePassword(event.target.value)} autoComplete="current-password" />
            <label className="server-check"><input type="checkbox" checked={deleteAcknowledged} onChange={(event) => setDeleteAcknowledged(event.target.checked)} /> {adminCopy("deletionAcknowledgement")}</label>
            <div className="server-dialog-actions"><button type="button" onClick={() => setDeleteTarget(null)} disabled={dataBusy}>{adminCopy("cancel")}</button><button className="danger" type="submit" disabled={dataBusy || deleteConfirmation !== deleteTarget.name || !deletePassword || !deleteAcknowledged}>{adminCopy(dataBusy ? "deleting" : "deleteLibrary")}</button></div>
          </form>
        </section>
      </div>}
      {profileUserId && <ProfileDialog userId={profileUserId} locale={workspaceLocale} onClose={() => setProfileUserId(null)} />}
    </main>
  );
}

function ServerAppContent() {
  const { locale, setLocale, t } = useLocale();
  const [route, setRoute] = useState<Route>(() => routeFromPath(window.location.pathname));
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootError, setBootError] = useState<unknown | null>(null);

  useEffect(() => {
    const showingWorkspace = user && route !== "verify-email" && route !== "reset-password";
    if (!showingWorkspace) document.documentElement.lang = locale;
  }, [locale, route, user]);

  const navigate = useCallback((next: Route) => {
    window.history.pushState({}, "", `/${next}`);
    setRoute(next);
  }, []);

  const acceptAuthenticatedUser = useCallback((current: CurrentUser) => {
    setUser(current);
    setLocale(current.preferred_locale);
  }, [setLocale]);

  useEffect(() => {
    const pop = () => setRoute(routeFromPath(window.location.pathname));
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);

  useEffect(() => {
    let active = true;
    void serverApi.me()
      .then((current) => { if (active) acceptAuthenticatedUser(current); })
      .catch((error: unknown) => {
        if (active && (!(error instanceof ServerApiError) || error.status !== 401)) {
          setBootError(error);
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [acceptAuthenticatedUser]);

  if (loading) {
    return <div className="server-loading"><LibraryBig size={38} /><LoaderCircle className="server-spinner" size={24} /><span>{t("loading")}</span></div>;
  }
  if (bootError !== null) {
    return <div className="server-loading error"><LibraryBig size={38} /><p>{authFriendlyError(bootError, t)}</p><button type="button" onClick={() => window.location.reload()}>{t("tryAgain")}</button></div>;
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
  else if (route === "restore-account") page = <RestoreAccountPage navigate={navigate} />;
  else page = <LoginPage navigate={navigate} onLogin={acceptAuthenticatedUser} />;

  return <AuthShell>{page}</AuthShell>;
}

export default function ServerApp() {
  return <LocaleProvider><ServerAppContent /></LocaleProvider>;
}
