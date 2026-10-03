import type { AppLocale } from "./locale";
import { profilePt } from "./locales/pt/profile";
import { profileCa } from "./locales/ca/profile";
import { profileIt } from "./locales/it/profile";

export const en = {
  openFailed: "This profile could not be opened.", closeProfile: "Close profile", openingProfile: "Opening profile…",
  member: "BOOKPILE member", timezone: "Timezone", gender: "Gender", pronouns: "Pronouns", city: "City", state: "State / region", country: "Country", dateOfBirth: "Date of birth",
  female: "female", male: "male", nonBinary: "non-binary", other: "other", they: "they",
  empty: "This member has not shared any profile details with you.",
} as const;
export type ProfileCopyKey = keyof typeof en;
const gl = {
  openFailed: "Non se puido abrir este perfil.", closeProfile: "Pechar perfil", openingProfile: "Abrindo o perfil…",
  member: "Membro de BOOKPILE", timezone: "Fuso horario", gender: "Xénero", pronouns: "Pronomes", city: "Cidade", state: "Estado / rexión", country: "País", dateOfBirth: "Data de nacemento",
  female: "muller", male: "home", nonBinary: "non binario", other: "outro", they: "elu",
  empty: "Este membro non compartiu contigo ningún dato do seu perfil.",
} satisfies Record<ProfileCopyKey, string>;
export const es = {
  openFailed: "No se ha podido abrir este perfil.", closeProfile: "Cerrar perfil", openingProfile: "Abriendo el perfil…",
  member: "Miembro de BOOKPILE", timezone: "Zona horaria", gender: "Género", pronouns: "Pronombres", city: "Ciudad", state: "Provincia / región", country: "País", dateOfBirth: "Fecha de nacimiento",
  female: "mujer", male: "hombre", nonBinary: "no binario", other: "otro", they: "elle",
  empty: "Este miembro no ha compartido contigo ningún dato de su perfil.",
} satisfies Record<ProfileCopyKey, string>;
export const pt = profilePt;
export const ca = profileCa;
export const it = profileIt;

const catalogues: Record<AppLocale, Record<ProfileCopyKey, string>> = { en, gl, es, pt, ca, it };
export function profileCopy(locale: AppLocale) {
  return (key: ProfileCopyKey) => catalogues[locale][key];
}
