import { useEffect, useState } from "react";
import { LoaderCircle, UserRound, X } from "lucide-react";
import { type AccountProfile, ServerApiError, serverApi } from "./serverApi";

function value(value: string | null | undefined) {
  return value || null;
}

export default function ProfileDialog({
  userId,
  onClose,
}: {
  userId: string;
  onClose: () => void;
}) {
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
            : "This profile could not be opened.",
        ),
      );
  }, [userId]);
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
          aria-label="Close profile"
        >
          <X />
        </button>
        {!profile && !error && (
          <p className="server-profile-loading">
            <LoaderCircle className="server-spinner" /> Opening profile…
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
                <p className="server-card-eyebrow">BOOKPILE member</p>
                <h2 id="public-profile-title">@{profile.username}</h2>
                {profile.display_name && <p>{profile.display_name}</p>}
              </div>
            </div>
            <dl className="server-public-profile-data">
              {value(profile.timezone) && (
                <>
                  <dt>Timezone</dt>
                  <dd>{profile.timezone}</dd>
                </>
              )}
              {profile.gender && profile.gender !== "UNSPECIFIED" && (
                <>
                  <dt>Gender</dt>
                  <dd>
                    {profile.gender === "CUSTOM"
                      ? profile.custom_gender
                      : profile.gender.toLowerCase()}
                  </dd>
                </>
              )}
              {profile.gender === "CUSTOM" && profile.preferred_pronoun && (
                <>
                  <dt>Pronouns</dt>
                  <dd>
                    {profile.preferred_pronoun === "NEUTRAL"
                      ? profile.neutral_pronoun || "they"
                      : profile.preferred_pronoun.toLowerCase()}
                  </dd>
                </>
              )}
              {value(profile.city) && (
                <>
                  <dt>City</dt>
                  <dd>{profile.city}</dd>
                </>
              )}
              {value(profile.state) && (
                <>
                  <dt>State / region</dt>
                  <dd>{profile.state}</dd>
                </>
              )}
              {value(profile.country) && (
                <>
                  <dt>Country</dt>
                  <dd>{profile.country}</dd>
                </>
              )}
              {value(profile.date_of_birth) && (
                <>
                  <dt>Date of birth</dt>
                  <dd>
                    {new Date(
                      `${profile.date_of_birth}T00:00:00`,
                    ).toLocaleDateString()}
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
                  This member has not shared any profile details with you.
                </p>
              )}
          </>
        )}
      </section>
    </div>
  );
}
