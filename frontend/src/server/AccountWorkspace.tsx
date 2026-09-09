import { type CSSProperties, type FormEvent, useEffect, useState } from "react";
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
  type PrivateAccount,
  type ProfileGender,
  type ProfilePronoun,
  type ProfileVisibility,
  type RecoverableLibrary,
  type StorageOverview,
  ServerApiError,
  serverApi,
} from "./serverApi";

const FIELDS = [
  ["display_name", "Name"],
  ["timezone", "Timezone"],
  ["personal_data", "Personal data"],
] as const;

const VISIBILITY: Array<[ProfileVisibility, string]> = [
  ["PRIVATE", "Only me"],
  ["SHARED_LIBRARY_MEMBERS", "People sharing a library"],
  ["AUTHENTICATED", "All BOOKPILE users"],
];
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

function message(error: unknown) {
  return error instanceof ServerApiError
    ? error.message
    : "BOOKPILE could not complete that request.";
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
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [account, setAccount] = useState<PrivateAccount | null>(null);
  const [storage, setStorage] = useState<StorageOverview | null>(null);
  const [recoverable, setRecoverable] = useState<RecoverableLibrary[]>([]);
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
    const [nextProfile, nextStorage, nextAccount, nextRecoverable] = await Promise.all([
      serverApi.accountProfile(),
      serverApi.accountStorage(),
      serverApi.account(),
      serverApi.recoverableLibraries(),
    ]);
    setProfile(nextProfile);
    setStorage(nextStorage);
    setAccount(nextAccount);
    setRecoverable(nextRecoverable);
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
      setNotice(`“${restored.name}” and all its memberships were restored.`);
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load().catch((caught) => setError(message(caught)));
  }, []);

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
      const {
        user_id: _userId,
        username: _username,
        profile_image_visible: _image,
        ...payload
      } = profile;
      setProfile(await serverApi.updateAccountProfile(payload));
      setStorage(await serverApi.accountStorage());
      setNotice("Your profile and privacy choices were saved.");
    } catch (caught) {
      setError(message(caught));
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
      setNotice("Your private profile image was updated.");
    } catch (caught) {
      setError(message(caught));
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
      setNotice("Your profile image was removed.");
    } catch (caught) {
      setError(message(caught));
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
      setNotice(
        "Your password was changed. Other signed-in devices were disconnected.",
      );
    } catch (caught) {
      setError(message(caught));
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
      setDeleteAccountError(message(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!profile || !storage || !account)
    return (
      <section className="server-account-workspace loading">
        <LoaderCircle className="server-spinner" /> Opening your account…
      </section>
    );
  const gender = profile.gender ?? "UNSPECIFIED";

  return (
    <section className="server-account-workspace">
      <header>
        <div>
          <p className="server-card-eyebrow">Private account</p>
          <h2>Your profile</h2>
          <p>
            Choose what other signed-in BOOKPILE users can see. Email, security
            and storage details always remain private.
          </p>
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
          <h3>Profile image</h3>
          <div className="server-profile-photo">
            {profile.profile_image_visible ? (
              <img
                src={serverApi.profileImageUrl(profile.user_id, imageRevision)}
                alt="Your profile"
              />
            ) : (
              <UserRound size={44} />
            )}
          </div>
          <div className="server-profile-photo-actions">
            <label>
              <Camera size={16} /> Choose image
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
                <Trash2 size={16} /> Remove
              </button>
            )}
          </div>
          <label>
            Who can see it?
            <select
              value={visibility("profile_image")}
              onChange={(event) =>
                setVisibility(
                  "profile_image",
                  event.target.value as ProfileVisibility,
                )
              }
            >
              {VISIBILITY.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </section>
        <section className="server-profile-card server-profile-fields">
          <h3>About you</h3>
          <div className="server-profile-field-grid">
            <label>
              Name{" "}
              <small>
                Shown only on your profile; BOOKPILE uses @{profile.username}{" "}
                elsewhere.
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
              Timezone
              <select
                value={profile.timezone ?? ""}
                onChange={(event) =>
                  update("timezone", event.target.value || null)
                }
              >
                <option value="">Not specified</option>
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
              City
              <input
                value={profile.city ?? ""}
                maxLength={120}
                onChange={(event) => update("city", event.target.value || null)}
              />
            </label>
            <label>
              State / region
              <input
                value={profile.state ?? ""}
                maxLength={120}
                onChange={(event) =>
                  update("state", event.target.value || null)
                }
              />
            </label>
            <label>
              Country
              <input
                value={profile.country ?? ""}
                maxLength={120}
                onChange={(event) =>
                  update("country", event.target.value || null)
                }
              />
            </label>
            <label>
              Date of birth
              <input
                type="date"
                value={profile.date_of_birth ?? ""}
                onChange={(event) =>
                  update("date_of_birth", event.target.value || null)
                }
              />
            </label>
            <label>
              Gender
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
                <option value="UNSPECIFIED">Leave blank</option>
                <option value="MALE">Male</option>
                <option value="FEMALE">Female</option>
                <option value="CUSTOM">Custom</option>
              </select>
            </label>
            {gender === "CUSTOM" && (
              <>
                <label>
                  Custom gender
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
                  Preferred pronoun
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
                    <option value="NEUTRAL">Neutral</option>
                    <option value="MALE">Male</option>
                    <option value="FEMALE">Female</option>
                  </select>
                </label>
                {profile.preferred_pronoun === "NEUTRAL" && (
                  <label>
                    Neutral pronoun text
                    <input
                      value={profile.neutral_pronoun ?? ""}
                      maxLength={80}
                      placeholder="they"
                      onChange={(event) =>
                        update("neutral_pronoun", event.target.value || null)
                      }
                    />
                  </label>
                )}
                <p className="server-profile-pronoun-note">
                  Pronouns are visible to signed-in users even when Gender is
                  private.
                </p>
              </>
            )}
          </div>
        </section>
        <section className="server-profile-card server-privacy-card">
          <h3>Privacy</h3>
          <p>
            Personal data groups gender, location and date of birth. Pronouns
            remain visible to signed-in users.
          </p>
          {FIELDS.map(([field, label]) => (
            <label key={field}>
              <span>{label}</span>
              <select
                value={visibility(field)}
                onChange={(event) =>
                  setVisibility(field, event.target.value as ProfileVisibility)
                }
              >
                {VISIBILITY.map(([value, option]) => (
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
            {busy ? "Saving…" : "Save profile"}
          </button>
        </section>
      </form>
      <section className="server-profile-card server-storage-card">
        <h3>Storage</h3>
        <p>
          Each colour shows how your used space is distributed. Shared-library
          storage is allocated across its Owners.
        </p>
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
                  aria-label={`${library.name}, contribution to used account storage`}
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
                  Account data
                </span>
                <div
                  className="server-storage-track"
                  role="progressbar"
                  aria-label="Account data contribution to used storage"
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
          <b>Total account storage</b>
          <div
            className="server-storage-track stacked"
            role="progressbar"
            aria-label="Total account storage used"
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
        <h3>Account</h3>
        <div className="server-account-data-grid">
          <span>
            <small>Username</small>
            <b>@{account.username}</b>
          </span>
          <span>
            <small>Registration email</small>
            <b>{account.email}</b>
          </span>
          <span>
            <small>Password</small>
            <b>{account.password_protected ? "••••••••••••" : "Not set"}</b>
          </span>
          <span>
            <small>Member since</small>
            <b>{new Date(account.created_at).toLocaleDateString()}</b>
          </span>
        </div>
      </section>
      {recoverable.length > 0 && (
        <section className="server-profile-card server-recovery-card">
          <h3>Recently deleted libraries</h3>
          <p>Every former Owner may restore the complete library for 48 hours. Recovery is all-or-nothing and requires available shared storage.</p>
          <div className="server-recovery-list">
            {recoverable.map((item) => (
              <div key={item.deletion_id}>
                <span><b>{item.name}</b><small>Recoverable until {new Date(item.recover_until).toLocaleString()}</small></span>
                <button type="button" onClick={() => { setRestoreTarget(item); setRestorePassword(""); }}>Restore</button>
              </div>
            ))}
          </div>
        </section>
      )}
      <section className="server-profile-card server-security-card server-security-expanded">
        <div>
          <KeyRound size={24} />
          <span>
            <h3>Security</h3>
            <p>Change your password or end signed-in sessions.</p>
          </span>
        </div>
        <form className="server-password-form" onSubmit={changePassword}>
          <label>
            Current password
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
            New password
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
            Confirm new password
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
            Change password
          </button>
        </form>
        <div className="server-session-actions">
          <button type="button" onClick={() => void onSignOut(false)}>
            <LogOut size={16} /> Sign out
          </button>
          <button type="button" onClick={() => void onSignOut(true)}>
            <LogOut size={16} /> Sign out everywhere
          </button>
          <button className="danger" type="button" onClick={() => { setDeleteAccountError(""); setDeleteAccountOpen(true); }}>
            <Trash2 size={16} /> Delete account
          </button>
        </div>
      </section>
      {restoreTarget && (
        <div className="server-modal-backdrop" role="presentation">
          <section className="server-permission-dialog" role="dialog" aria-modal="true">
            <p className="server-card-eyebrow">Complete recovery</p>
            <h2>Restore “{restoreTarget.name}”?</h2>
            <p>Books, covers, layout, readings, loans and every previous membership will return together.</p>
            <form onSubmit={restoreLibrary}>
              <label>Your current password<input type="password" autoComplete="current-password" autoFocus required value={restorePassword} onChange={(event) => setRestorePassword(event.target.value)} /></label>
              <div className="server-dialog-actions"><button type="button" disabled={busy} onClick={() => setRestoreTarget(null)}>Cancel</button><button className="confirm" type="submit" disabled={busy || !restorePassword}>{busy ? "Restoring…" : "Restore library"}</button></div>
            </form>
          </section>
        </div>
      )}
      {deleteAccountOpen && (
        <div className="server-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setDeleteAccountOpen(false); }}>
          <section className="server-permission-dialog server-delete-library-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-account-title">
            <p className="server-card-eyebrow">Danger zone</p>
            <h2 id="delete-account-title">Delete your account?</h2>
            <p>Your profile becomes invisible, every session is closed and your Viewer memberships are removed immediately. You must transfer or delete every library you own first. You may recover the complete account for 48 hours; after that your profile, personal readings and personal data are permanently erased.</p>
            <form onSubmit={deleteAccount}>
              <label>Type <b>{account.username}</b> exactly<input required autoFocus value={deleteAccountName} onChange={(event) => setDeleteAccountName(event.target.value)} /></label>
              <label>Your current password<input required type="password" autoComplete="current-password" value={deleteAccountPassword} onChange={(event) => setDeleteAccountPassword(event.target.value)} /></label>
              <label className="server-check"><input type="checkbox" checked={deleteAccountAcknowledged} onChange={(event) => setDeleteAccountAcknowledged(event.target.checked)} /> I understand that account recovery expires after 48 hours.</label>
              {deleteAccountError && <div className="server-message error" role="alert">{deleteAccountError}</div>}
              <div className="server-dialog-actions"><button type="button" disabled={busy} onClick={() => setDeleteAccountOpen(false)}>Cancel</button><button className="danger" type="submit" disabled={busy || deleteAccountName !== account.username || !deleteAccountPassword || !deleteAccountAcknowledged}>{busy ? "Deleting…" : "Delete account"}</button></div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
