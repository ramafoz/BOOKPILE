import type { AppLocale } from "./locale";

export const en = {
  openFailed: "This profile could not be opened.", closeProfile: "Close profile", openingProfile: "Opening profile…",
  member: "BOOKPILE member", timezone: "Timezone", gender: "Gender", pronouns: "Pronouns", city: "City", state: "State / region", country: "Country", dateOfBirth: "Date of birth",
  female: "female", male: "male", nonBinary: "non-binary", other: "other", they: "they",
  empty: "This member has not shared any profile details with you.",
} as const;
export type ProfileCopyKey = keyof typeof en;



const catalogues: Partial<Record<AppLocale, Record<ProfileCopyKey, string>>> = { en };

export function registerProfileCatalogue(
  locale: AppLocale,
  catalogue: Record<ProfileCopyKey, string>,
): void {
  catalogues[locale] = catalogue;
}
export function profileCopy(locale: AppLocale) {
  const catalogue = catalogues[locale];
  if (!catalogue) throw new Error(`Locale catalogue not loaded: ${locale}`);
  return (key: ProfileCopyKey) => catalogue[key];
}
