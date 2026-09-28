import { useEffect, useMemo, useState } from "react";
import { LoaderCircle, UserRound, X } from "lucide-react";
import { type AccountProfile, ServerApiError, serverApi } from "./serverApi";
import type { AppLocale } from "./locale";
import { profileCopy } from "./profileCopy";

function value(value: string | null | undefined) {
  return value || null;
}

export default function ProfileDialog({
  userId,
  locale,
  onClose,
}: {
  userId: string;
  locale: AppLocale;
  onClose: () => void;
}) {
  const copy = useMemo(() => profileCopy(locale), [locale]);
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    void serverApi
      .profile(userId)
      .then(setProfile)
      .catch((caught) =>
        setError(
          caught instanceof ServerApiError
            ? caught.message
            : copy("openFailed"),
        ),
      );
  }, [copy, userId]);
  return (
    <div
      className="server-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="server-public-profile"
        role="dialog"
        aria-modal="true"
        aria-labelledby="public-profile-title"
      >
        <button
          className="server-dialog-close"
          type="button"
          onClick={onClose}
          aria-label={copy("closeProfile")}
        >
          <X />
        </button>
        {!profile && !error && (
          <p className="server-profile-loading">
            <LoaderCircle className="server-spinner" /> {copy("openingProfile")}
          </p>
        )}
        {error && <div className="server-message error">{error}</div>}
        {profile && (
          <>
            <div className="server-public-profile-heading">
              <div className="server-profile-photo">
                {profile.profile_image_visible ? (
                  <img
                    src={serverApi.profileImageUrl(profile.user_id)}
                    alt=""
                  />
                ) : (
                  <UserRound size={44} />
                )}
              </div>
              <div>
                <p className="server-card-eyebrow">{copy("member")}</p>
                <h2 id="public-profile-title">@{profile.username}</h2>
                {profile.display_name && <p>{profile.display_name}</p>}
              </div>
            </div>
            <dl className="server-public-profile-data">
              {value(profile.timezone) && (
                <>
                  <dt>{copy("timezone")}</dt>
                  <dd>{profile.timezone}</dd>
                </>
              )}
              {profile.gender && profile.gender !== "UNSPECIFIED" && (
                <>
                  <dt>{copy("gender")}</dt>
                  <dd>
                    {profile.gender === "CUSTOM"
                      ? profile.custom_gender
                      : copy(profile.gender === "FEMALE" ? "female" : profile.gender === "MALE" ? "male" : profile.gender === "NON_BINARY" ? "nonBinary" : "other")}
                  </dd>
                </>
              )}
              {profile.gender === "CUSTOM" && profile.preferred_pronoun && (
                <>
                  <dt>{copy("pronouns")}</dt>
                  <dd>
                    {profile.preferred_pronoun === "NEUTRAL"
                      ? profile.neutral_pronoun || copy("they")
                      : profile.preferred_pronoun.toLowerCase()}
                  </dd>
                </>
              )}
              {value(profile.city) && (
                <>
                  <dt>{copy("city")}</dt>
                  <dd>{profile.city}</dd>
                </>
              )}
              {value(profile.state) && (
                <>
                  <dt>{copy("state")}</dt>
                  <dd>{profile.state}</dd>
                </>
              )}
              {value(profile.country) && (
                <>
                  <dt>{copy("country")}</dt>
                  <dd>{profile.country}</dd>
                </>
              )}
              {value(profile.date_of_birth) && (
                <>
                  <dt>{copy("dateOfBirth")}</dt>
                  <dd>
                    {new Date(
                      `${profile.date_of_birth}T00:00:00`,
                    ).toLocaleDateString(locale === "gl" ? "gl-ES" : "en-GB")}
                  </dd>
                </>
              )}
            </dl>
            {!profile.display_name &&
              !profile.timezone &&
              !profile.gender &&
              !profile.city &&
              !profile.state &&
              !profile.country &&
              !profile.date_of_birth && (
                <p className="server-profile-empty">
                  {copy("empty")}
                </p>
              )}
          </>
        )}
      </section>
    </div>
  );
}
