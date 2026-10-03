import type { ProfileCopyKey } from "../../profileCopy";

export const profileIt = {
  openFailed: "Non è stato possibile aprire questo profilo.", closeProfile: "Chiudi il profilo", openingProfile: "Apertura del profilo…", member: "Membro di BOOKPILE", timezone: "Fuso orario", gender: "Genere", pronouns: "Pronomi", city: "Città", state: "Provincia / regione", country: "Paese", dateOfBirth: "Data di nascita", female: "donna", male: "uomo", nonBinary: "non binario", other: "altro", they: "loro", empty: "Questo membro non ha condiviso con te alcun dato del profilo.",
} satisfies Record<ProfileCopyKey, string>;
