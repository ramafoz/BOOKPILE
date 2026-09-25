import { type CSSProperties, type FormEvent, useCallback, useEffect, useState } from "react";
import {
  Camera,
  KeyRound,
  LoaderCircle,
  LogOut,
  ShieldCheck,
  Trash2,
  UserRound,
} from "lucide-react";
import {
  type AccountProfile,
  type BetaInvitationStatus,
  type PrivateAccount,
  type ProfileGender,
  type ProfilePronoun,
  type ProfileVisibility,
  type RecoverableLibrary,
  type StorageOverview,
  ServerApiError,
  serverApi,
} from "./serverApi";
import { useLocale } from "./LocaleContext";
import { availableLocales, formatLocalDateTime, localeNames } from "./locale";
import { accountInvitationMessage } from "./invitationCopy";
import { authenticatedCopy } from "./authenticatedCopy";
const COLOURS = [
  "#2f7667",
  "#a95d36",
  "#d39a31",
  "#567ca2",
  "#875f8d",
  "#748b47",
  "#b66f72",
  "#477f86",
];
const TIMEZONES = (() => {
  const supported =
    (
      Intl as unknown as { supportedValuesOf?: (key: string) => string[] }
    ).supportedValuesOf?.("timeZone") ?? [];
  return supported.length
    ? supported
    : [
        "Europe/Madrid",
        "Europe/London",
        "America/New_York",
        "Asia/Tokyo",
        "UTC",
      ];
})();

function message(error: unknown, fallback: string) {
  return error instanceof ServerApiError
    ? error.message
    : fallback;
}

export default function AccountWorkspace({
  onSignOut,
  onLibrariesChanged,
  onAccountDeleted,
}: {
  onSignOut: (everyDevice: boolean) => Promise<void>;
  onLibrariesChanged: (preferredId?: string) => Promise<void>;
  onAccountDeleted: () => void;
}) {
  const { locale, setLocale } = useLocale();
  const copy = authenticatedCopy(locale);
  const fields = [
    ["display_name", copy("fieldName")],
    ["timezone", copy("fieldTimezone")],
    ["personal_data", copy("fieldPersonalData")],
  ] as const;
  const visibilityOptions: Array<[ProfileVisibility, string]> = [
    ["PRIVATE", copy("visibilityPrivate")],
    ["SHARED_LIBRARY_MEMBERS", copy("visibilityLibrary")],
    ["AUTHENTICATED", copy("visibilityAuthenticated")],
  ];
  const requestFailedMessage = copy("requestFailed");
  const errorMessage = useCallback(
    (caught: unknown) => message(caught, requestFailedMessage),
    [requestFailedMessage],
  );
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [account, setAccount] = useState<PrivateAccount | null>(null);
  const [storage, setStorage] = useState<StorageOverview | null>(null);
  const [recoverable, setRecoverable] = useState<RecoverableLibrary[]>([]);
  const [betaInvitations, setBetaInvitations] = useState<BetaInvitationStatus | null>(null);
  const [earnedInvitationLink, setEarnedInvitationLink] = useState("");
  const [earnedInvitationExpiry, setEarnedInvitationExpiry] = useState("");
  const [invitationLocale, setInvitationLocale] = useState(locale);
  const [restoreTarget, setRestoreTarget] = useState<RecoverableLibrary | null>(null);
  const [restorePassword, setRestorePassword] = useState("");
  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false);
  const [deleteAccountPassword, setDeleteAccountPassword] = useState("");
  const [deleteAccountName, setDeleteAccountName] = useState("");
  const [deleteAccountAcknowledged, setDeleteAccountAcknowledged] = useState(false);
  const [deleteAccountError, setDeleteAccountError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [imageRevision, setImageRevision] = useState("");
  const [passwords, setPasswords] = useState({
    current_password: "",
    new_password: "",
    confirmation: "",
  });

  async function load() {
    const [nextProfile, nextStorage, nextAccount, nextRecoverable, nextBetaInvitations] = await Promise.all([
      serverApi.accountProfile(),
      serverApi.accountStorage(),
      serverApi.account(),
      serverApi.recoverableLibraries(),
      serverApi.betaInvitationStatus(),
    ]);
    setProfile(nextProfile);
    setStorage(nextStorage);
    setAccount(nextAccount);
    setRecoverable(nextRecoverable);
    setBetaInvitations(nextBetaInvitations);
  }

  async function createBetaInvitation() {
    setBusy(true);
    setError("");
    try {
      const invitation = await serverApi.createEarnedAccountInvitation();
      const url = new URL("/register", window.location.origin);
      url.searchParams.set("invite", invitation.invitation_token);
      setEarnedInvitationLink(url.toString());
      setEarnedInvitationExpiry(invitation.expires_at);
      setBetaInvitations(await serverApi.betaInvitationStatus());
      setNotice(copy("invitationReady"));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function changeAccountLocale(nextLocale: typeof locale) {
    if (nextLocale === locale) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await serverApi.updatePreferredLocale(nextLocale);
      setLocale(updated.preferred_locale);
      setInvitationLocale(updated.preferred_locale);
      setNotice(copy("languageSaved"));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function copyBetaInvitation(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setNotice(copy("copied", { label }));
    } catch {
      setError(copy("clipboardFailed"));
    }
  }

  async function restoreLibrary(event: FormEvent) {
    event.preventDefault();
    if (!restoreTarget) return;
    setBusy(true);
    setError("");
    try {
      const restored = await serverApi.restoreLibrary(
        restoreTarget.deletion_id,
        restorePassword,
      );
      setRestoreTarget(null);
      setRestorePassword("");
      await Promise.all([load(), onLibrariesChanged(restored.library_id)]);
      setNotice(copy("libraryRestored", { name: restored.name }));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load().catch((caught) => setError(errorMessage(caught)));
  }, [errorMessage]);

  function update<K extends keyof AccountProfile>(
    field: K,
    value: AccountProfile[K],
  ) {
    setProfile((current) =>
      current ? { ...current, [field]: value } : current,
    );
  }

  function visibility(field: string): ProfileVisibility {
    return profile?.visibilities?.[field] ?? "PRIVATE";
  }

  function setVisibility(field: string, value: ProfileVisibility) {
    if (!profile) return;
    update("visibilities", { ...(profile.visibilities ?? {}), [field]: value });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!profile) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        display_name: profile.display_name,
        timezone: profile.timezone,
        gender: profile.gender,
        custom_gender: profile.custom_gender,
        preferred_pronoun: profile.preferred_pronoun,
        neutral_pronoun: profile.neutral_pronoun,
        city: profile.city,
        state: profile.state,
        country: profile.country,
        date_of_birth: profile.date_of_birth,
        visibilities: profile.visibilities,
      };
      setProfile(await serverApi.updateAccountProfile(payload));
      setStorage(await serverApi.accountStorage());
      setNotice(copy("profileSaved"));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function upload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await serverApi.uploadProfileImage(file);
      setProfile((current) =>
        current ? { ...current, profile_image_visible: true } : current,
      );
      setStorage(await serverApi.accountStorage());
      setImageRevision(String(Date.now()));
      setNotice(copy("imageUpdated"));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function removeImage() {
    setBusy(true);
    setError("");
    try {
      await serverApi.removeProfileImage();
      setProfile((current) =>
        current ? { ...current, profile_image_visible: false } : current,
      );
      setStorage(await serverApi.accountStorage());
      setNotice(copy("imageRemoved"));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await serverApi.changePassword(passwords);
      setPasswords({
        current_password: "",
        new_password: "",
        confirmation: "",
      });
      setNotice(copy("passwordChanged"));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function deleteAccount(event: FormEvent) {
    event.preventDefault();
    if (!account) return;
    setBusy(true);
    setError("");
    setDeleteAccountError("");
    try {
      await serverApi.deleteAccount({
        current_password: deleteAccountPassword,
        confirmation_username: deleteAccountName,
        acknowledge_permanent_deletion: deleteAccountAcknowledged,
      });
      onAccountDeleted();
    } catch (caught) {
      setDeleteAccountError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!profile || !storage || !account)
    return (
      <section className="server-account-workspace loading">
        <LoaderCircle className="server-spinner" /> {copy("openingAccount")}
      </section>
    );
  const gender = profile.gender ?? "UNSPECIFIED";

  return (
    <section className="server-account-workspace">
      <header>
        <div>
          <p className="server-card-eyebrow">{copy("privateAccount")}</p>
          <h2>{copy("yourProfile")}</h2>
          <p>{copy("profileIntro")}</p>
        </div>
        <ShieldCheck size={42} />
      </header>
      {error && (
        <div className="server-message error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="server-message success" role="status">
          {notice}
        </div>
      )}
      <form onSubmit={save} className="server-profile-layout">
        <section className="server-profile-card">
          <h3>{copy("profileImage")}</h3>
          <div className="server-profile-photo">
            {profile.profile_image_visible ? (
              <img
                src={serverApi.profileImageUrl(profile.user_id, imageRevision)}
                alt={copy("yourProfileImage")}
              />
            ) : (
              <UserRound size={44} />
            )}
          </div>
          <div className="server-profile-photo-actions">
            <label>
              <Camera size={16} /> {copy("chooseImage")}
              <input
                type="file"
                accept="image/*,.heic,.heif"
                disabled={busy}
                onChange={(event) => {
                  void upload(event.target.files?.[0]);
                  event.currentTarget.value = "";
                }}
              />
            </label>
            {profile.profile_image_visible && (
              <button
                type="button"
                onClick={() => void removeImage()}
                disabled={busy}
              >
                <Trash2 size={16} /> {copy("remove")}
              </button>
            )}
          </div>
          <label>
            {copy("whoCanSeeIt")}
            <select
              value={visibility("profile_image")}
              onChange={(event) =>
                setVisibility(
                  "profile_image",
                  event.target.value as ProfileVisibility,
                )
              }
            >
              {visibilityOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </section>
        <section className="server-profile-card server-profile-fields">
          <h3>{copy("aboutYou")}</h3>
          <div className="server-profile-field-grid">
            <label>
              {copy("name")}{" "}
              <small>
                {copy("nameHelp", { username: profile.username })}
              </small>
              <input
                value={profile.display_name ?? ""}
                maxLength={100}
                onChange={(event) =>
                  update("display_name", event.target.value || null)
                }
              />
            </label>
            <label>
              {copy("timezone")}
              <select
                value={profile.timezone ?? ""}
                onChange={(event) =>
                  update("timezone", event.target.value || null)
                }
              >
                <option value="">{copy("notSpecified")}</option>
                {profile.timezone && !TIMEZONES.includes(profile.timezone) && (
                  <option value={profile.timezone}>{profile.timezone}</option>
                )}
                {TIMEZONES.map((timezone) => (
                  <option key={timezone} value={timezone}>
                    {timezone}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {copy("city")}
              <input
                value={profile.city ?? ""}
                maxLength={120}
                onChange={(event) => update("city", event.target.value || null)}
              />
            </label>
            <label>
              {copy("stateRegion")}
              <input
                value={profile.state ?? ""}
                maxLength={120}
                onChange={(event) =>
                  update("state", event.target.value || null)
                }
              />
            </label>
            <label>
              {copy("country")}
              <input
                value={profile.country ?? ""}
                maxLength={120}
                onChange={(event) =>
                  update("country", event.target.value || null)
                }
              />
            </label>
            <label>
              {copy("dateOfBirth")}
              <input
                type="date"
                value={profile.date_of_birth ?? ""}
                onChange={(event) =>
                  update("date_of_birth", event.target.value || null)
                }
              />
            </label>
            <label>
              {copy("gender")}
              <select
                value={gender}
                onChange={(event) => {
                  const value = event.target.value as ProfileGender;
                  setProfile({
                    ...profile,
                    gender: value,
                    custom_gender:
                      value === "CUSTOM" ? profile.custom_gender : null,
                    preferred_pronoun:
                      value === "CUSTOM"
                        ? (profile.preferred_pronoun ?? "NEUTRAL")
                        : null,
                    neutral_pronoun:
                      value === "CUSTOM" ? profile.neutral_pronoun : null,
                  });
                }}
              >
                <option value="UNSPECIFIED">{copy("leaveBlank")}</option>
                <option value="MALE">{copy("male")}</option>
                <option value="FEMALE">{copy("female")}</option>
                <option value="CUSTOM">{copy("custom")}</option>
              </select>
            </label>
            {gender === "CUSTOM" && (
              <>
                <label>
                  {copy("customGender")}
                  <input
                    required
                    value={profile.custom_gender ?? ""}
                    maxLength={80}
                    onChange={(event) =>
                      update("custom_gender", event.target.value || null)
                    }
                  />
                </label>
                <label>
                  {copy("preferredPronoun")}
                  <select
                    value={profile.preferred_pronoun ?? "NEUTRAL"}
                    onChange={(event) => {
                      const value = event.target.value as ProfilePronoun;
                      setProfile({
                        ...profile,
                        preferred_pronoun: value,
                        neutral_pronoun:
                          value === "NEUTRAL" ? profile.neutral_pronoun : null,
                      });
                    }}
                  >
                    <option value="NEUTRAL">{copy("neutral")}</option>
                    <option value="MALE">{copy("male")}</option>
                    <option value="FEMALE">{copy("female")}</option>
                  </select>
                </label>
                {profile.preferred_pronoun === "NEUTRAL" && (
                  <label>
                    {copy("neutralPronounText")}
                    <input
                      value={profile.neutral_pronoun ?? ""}
                      maxLength={80}
                      placeholder={copy("neutralPronounPlaceholder")}
                      onChange={(event) =>
                        update("neutral_pronoun", event.target.value || null)
                      }
                    />
                  </label>
                )}
                <p className="server-profile-pronoun-note">
                  {copy("pronounVisibility")}
                </p>
              </>
            )}
          </div>
        </section>
        <section className="server-profile-card server-privacy-card">
          <h3>{copy("privacy")}</h3>
          <p>{copy("privacyHelp")}</p>
          {fields.map(([field, label]) => (
            <label key={field}>
              <span>{label}</span>
              <select
                value={visibility(field)}
                onChange={(event) =>
                  setVisibility(field, event.target.value as ProfileVisibility)
                }
              >
                {visibilityOptions.map(([value, option]) => (
                  <option key={value} value={value}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <button
            className="server-primary-action"
            type="submit"
            disabled={busy}
          >
            {busy ? copy("saving") : copy("saveProfile")}
          </button>
        </section>
      </form>
      <section className="server-profile-card server-storage-card">
        <h3>{copy("storage")}</h3>
        <p>{copy("storageHelp")}</p>
        {storage.libraries.length +
          (storage.account_data_share_of_used > 0 ? 1 : 0) >
          1 && (
          <div className="server-storage-library-list">
            {storage.libraries.map((library) => (
              <div key={library.library_id}>
                <span>
                  <i
                    style={
                      {
                        "--storage-colour":
                          COLOURS[library.colour_key % COLOURS.length],
                      } as CSSProperties
                    }
                  />
                  {library.name}
                </span>
                <div
                  className="server-storage-track"
                  role="progressbar"
                  aria-label={copy("libraryStorageLabel", { library: library.name })}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(library.share_of_used * 100)}
                >
                  <i
                    style={{
                      width: `${library.share_of_used * 100}%`,
                      background: COLOURS[library.colour_key % COLOURS.length],
                    }}
                  />
                </div>
              </div>
            ))}
            {storage.account_data_share_of_used > 0 && (
              <div>
                <span>
                  <i className="neutral" />
                  {copy("accountData")}
                </span>
                <div
                  className="server-storage-track"
                  role="progressbar"
                  aria-label={copy("accountDataStorageLabel")}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(
                    storage.account_data_share_of_used * 100,
                  )}
                >
                  <i
                    className="neutral"
                    style={{
                      width: `${storage.account_data_share_of_used * 100}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        )}
        <div className="server-storage-total">
          <b>{copy("totalAccountStorage")}</b>
          <div
            className="server-storage-track stacked"
            role="progressbar"
            aria-label={copy("totalStorageLabel")}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(storage.used_share_of_entitlement * 100)}
          >
            {storage.libraries.map((library) => (
              <i
                key={library.library_id}
                style={{
                  width: `${library.share_of_entitlement * 100}%`,
                  background: COLOURS[library.colour_key % COLOURS.length],
                }}
              />
            ))}
            {storage.account_data_share_of_entitlement > 0 && (
              <i
                className="neutral"
                style={{
                  width: `${storage.account_data_share_of_entitlement * 100}%`,
                }}
              />
            )}
          </div>
        </div>
      </section>
      <section className="server-profile-card server-account-data-card">
        <h3>{copy("account")}</h3>
        <div className="server-account-data-grid">
          <span>
            <small>{copy("username")}</small>
            <b>@{account.username}</b>
          </span>
          <span>
            <small>{copy("registrationEmail")}</small>
            <b>{account.email}</b>
          </span>
          <span>
            <small>{copy("password")}</small>
            <b>{account.password_protected ? "••••••••••••" : copy("notSet")}</b>
          </span>
          <span>
            <small>{copy("memberSince")}</small>
            <b>{formatLocalDateTime(account.created_at, locale)}</b>
          </span>
        </div>
      </section>
      <section className="server-profile-card server-language-card">
        <h3>{copy("language")}</h3>
        <p>{copy("languageHelp")}</p>
        <label className="server-invitation-language">{copy("bookpileLanguage")}<select value={locale} disabled={busy} onChange={(event) => void changeAccountLocale(event.target.value as typeof locale)}>{availableLocales.map((code) => <option value={code} key={code}>{localeNames[code]}</option>)}</select></label>
      </section>
      {betaInvitations && (
        <section className="server-profile-card server-beta-invitation-card">
          <h3>{copy("inviteSomeone")}</h3>
          <p>{copy("betaInvitationHelp")}</p>
          <div className="server-beta-day-progress" role="progressbar" aria-label={copy("invitationProgressLabel", { active: betaInvitations.active_day_count, required: betaInvitations.days_required })} aria-valuemin={0} aria-valuemax={betaInvitations.days_required} aria-valuenow={betaInvitations.active_day_count}>
            {Array.from({ length: betaInvitations.days_required }, (_, index) => <i key={index} className={index < betaInvitations.active_day_count ? "complete" : ""} />)}
          </div>
          <small>{copy("invitationProgress", { active: betaInvitations.active_day_count, required: betaInvitations.days_required })}</small>
          <div className="server-beta-invitation-summary"><span><b>{betaInvitations.available_credits}</b> {copy("invitationsReady")}</span><span><b>{betaInvitations.open_invitations}</b> {copy("invitationsOpen")}</span></div>
          <label className="server-invitation-language">{copy("invitationLanguage")}<select value={invitationLocale} onChange={(event) => setInvitationLocale(event.target.value as typeof invitationLocale)}>{availableLocales.map((code) => <option value={code} key={code}>{localeNames[code]}</option>)}</select></label>
          {betaInvitations.available_credits > 0 && <button className="server-primary-action" type="button" disabled={busy} onClick={() => void createBetaInvitation()}><KeyRound size={16} /> {copy("createAccountInvitation")}</button>}
          {earnedInvitationLink && <div className="server-earned-invitation">
            <label>{copy("invitationMessage")}<textarea readOnly value={accountInvitationMessage(invitationLocale, earnedInvitationLink)} onFocus={(event) => event.currentTarget.select()} /></label>
            <div className="server-invitation-copy-actions"><button type="button" onClick={() => void copyBetaInvitation(accountInvitationMessage(invitationLocale, earnedInvitationLink), copy("invitationMessage"))}>{copy("copyMessage")}</button><button type="button" onClick={() => void copyBetaInvitation(earnedInvitationLink, copy("invitationLink"))}>{copy("copyLinkOnly")}</button></div>
            <small>{copy("invitationExpires", { date: formatLocalDateTime(earnedInvitationExpiry, locale) })}</small>
          </div>}
        </section>
      )}
      {recoverable.length > 0 && (
        <section className="server-profile-card server-recovery-card">
          <h3>{copy("recentlyDeletedLibraries")}</h3>
          <p>{copy("recoveryHelp")}</p>
          <div className="server-recovery-list">
            {recoverable.map((item) => (
              <div key={item.deletion_id}>
                <span><b>{item.name}</b><small>{copy("recoverableUntil", { date: formatLocalDateTime(item.recover_until, locale) })}</small></span>
                <button type="button" onClick={() => { setRestoreTarget(item); setRestorePassword(""); }}>{copy("restore")}</button>
              </div>
            ))}
          </div>
        </section>
      )}
      <section className="server-profile-card server-security-card server-security-expanded">
        <div>
          <KeyRound size={24} />
          <span>
            <h3>{copy("security")}</h3>
            <p>{copy("securityHelp")}</p>
          </span>
        </div>
        <form className="server-password-form" onSubmit={changePassword}>
          <label>
            {copy("currentPassword")}
            <input
              type="password"
              autoComplete="current-password"
              required
              value={passwords.current_password}
              onChange={(event) =>
                setPasswords({
                  ...passwords,
                  current_password: event.target.value,
                })
              }
            />
          </label>
          <label>
            {copy("newPassword")}
            <input
              type="password"
              autoComplete="new-password"
              minLength={12}
              required
              value={passwords.new_password}
              onChange={(event) =>
                setPasswords({ ...passwords, new_password: event.target.value })
              }
            />
          </label>
          <label>
            {copy("confirmNewPassword")}
            <input
              type="password"
              autoComplete="new-password"
              minLength={12}
              required
              value={passwords.confirmation}
              onChange={(event) =>
                setPasswords({ ...passwords, confirmation: event.target.value })
              }
            />
          </label>
          <button type="submit" disabled={busy}>
            {copy("changePassword")}
          </button>
        </form>
        <div className="server-session-actions">
          <button type="button" onClick={() => void onSignOut(false)}>
            <LogOut size={16} /> {copy("signOut")}
          </button>
          <button type="button" onClick={() => void onSignOut(true)}>
            <LogOut size={16} /> {copy("signOutEverywhere")}
          </button>
          <button className="danger" type="button" onClick={() => { setDeleteAccountError(""); setDeleteAccountOpen(true); }}>
            <Trash2 size={16} /> {copy("deleteAccount")}
          </button>
        </div>
      </section>
      {restoreTarget && (
        <div className="server-modal-backdrop" role="presentation">
          <section className="server-permission-dialog" role="dialog" aria-modal="true">
            <p className="server-card-eyebrow">{copy("completeRecovery")}</p>
            <h2>{copy("restoreLibraryTitle", { name: restoreTarget.name })}</h2>
            <p>{copy("restoreLibraryHelp")}</p>
            <form onSubmit={restoreLibrary}>
              <label>{copy("yourCurrentPassword")}<input type="password" autoComplete="current-password" autoFocus required value={restorePassword} onChange={(event) => setRestorePassword(event.target.value)} /></label>
              <div className="server-dialog-actions"><button type="button" disabled={busy} onClick={() => setRestoreTarget(null)}>{copy("cancel")}</button><button className="confirm" type="submit" disabled={busy || !restorePassword}>{busy ? copy("restoring") : copy("restoreLibrary")}</button></div>
            </form>
          </section>
        </div>
      )}
      {deleteAccountOpen && (
        <div className="server-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setDeleteAccountOpen(false); }}>
          <section className="server-permission-dialog server-delete-library-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-account-title">
            <p className="server-card-eyebrow">{copy("dangerZone")}</p>
            <h2 id="delete-account-title">{copy("deleteAccountTitle")}</h2>
            <p>{copy("deleteAccountHelp")}</p>
            <form onSubmit={deleteAccount}>
              <label>{copy("typeUsername", { username: account.username })}<input required autoFocus value={deleteAccountName} onChange={(event) => setDeleteAccountName(event.target.value)} /></label>
              <label>{copy("yourCurrentPassword")}<input required type="password" autoComplete="current-password" value={deleteAccountPassword} onChange={(event) => setDeleteAccountPassword(event.target.value)} /></label>
              <label className="server-check"><input type="checkbox" checked={deleteAccountAcknowledged} onChange={(event) => setDeleteAccountAcknowledged(event.target.checked)} /> {copy("deletionAcknowledgement")}</label>
              {deleteAccountError && <div className="server-message error" role="alert">{deleteAccountError}</div>}
              <div className="server-dialog-actions"><button type="button" disabled={busy} onClick={() => setDeleteAccountOpen(false)}>{copy("cancel")}</button><button className="danger" type="submit" disabled={busy || deleteAccountName !== account.username || !deleteAccountPassword || !deleteAccountAcknowledged}>{busy ? copy("deleting") : copy("deleteAccount")}</button></div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
