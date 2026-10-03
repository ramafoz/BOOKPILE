import type { ProfileCopyKey } from "../../profileCopy";

export const profileCa = {
  openFailed: "No s'ha pogut obrir aquest perfil.", closeProfile: "Tanca el perfil", openingProfile: "Obrint el perfil…", member: "Membre de BOOKPILE", timezone: "Zona horària", gender: "Gènere", pronouns: "Pronoms", city: "Ciutat", state: "Província / regió", country: "País", dateOfBirth: "Data de naixement", female: "dona", male: "home", nonBinary: "no-binari", other: "altre", they: "elle", empty: "Aquest membre no ha compartit cap dada del perfil amb tu.",
} satisfies Record<ProfileCopyKey, string>;
