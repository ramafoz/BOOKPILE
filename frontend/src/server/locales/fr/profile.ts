import type { ProfileCopyKey } from "../../profileCopy";

export const profileFr = {
  openFailed: "Impossible d’ouvrir ce profil.", closeProfile: "Fermer le profil", openingProfile: "Ouverture du profil…", member: "Membre de BOOKPILE", timezone: "Fuseau horaire", gender: "Genre", pronouns: "Pronoms", city: "Ville", state: "Province / région", country: "Pays", dateOfBirth: "Date de naissance", female: "femme", male: "homme", nonBinary: "non binaire", other: "autre", they: "iel", empty: "Ce membre ne vous a communiqué aucune information de profil.",
} satisfies Record<ProfileCopyKey, string>;
