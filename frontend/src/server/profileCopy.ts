import type { AppLocale } from "./locale";

const en = {
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

const catalogues: Record<AppLocale, Record<ProfileCopyKey, string>> = { en, gl };
export function profileCopy(locale: AppLocale) {
  return (key: ProfileCopyKey) => catalogues[locale][key];
}
