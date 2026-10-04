import type { ProfileCopyKey } from "../../profileCopy";

export const profileOc = {
  openFailed: "Non s'a pogut daurir aguest perfil.", closeProfile: "Barrar eth perfil", openingProfile: "En tot daurir eth perfil…", member: "Membre de BOOKPILE", timezone: "Zòna orària", gender: "Genre", pronouns: "Pronòms", city: "Vila", state: "Província / region", country: "País", dateOfBirth: "Data de naishença", female: "hemna", male: "òme", nonBinary: "non binari", other: "un aute", they: "eth/era", empty: "Aguest membre non a compartit cap d'informacion de perfil damb tu.",
} satisfies Record<ProfileCopyKey, string>;
