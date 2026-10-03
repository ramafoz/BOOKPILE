import { english, type MessageKey } from "./locales/en";
import { galician } from "./locales/gl";
import { spanish } from "./locales/es";
import { portuguese } from "./locales/pt";

export { english } from "./locales/en";
export type { MessageKey } from "./locales/en";

export const LOCALE_STORAGE_KEY = "bookpile.server.locale";

// A language belongs here only after the current route is fully translated.
export const availableLocales = ["en", "gl", "es", "pt"] as const;
export type AppLocale = (typeof availableLocales)[number];

export const localeNames: Record<AppLocale, string> = {
  en: "English",
  gl: "Galego",
  es: "Español",
  pt: "Português",
};

const intlLocales: Record<AppLocale, string> = {
  // BOOKPILE deliberately offers one Portuguese catalogue for every regional
  // variant. pt-PT provides deterministic date and number conventions; it
  // does not restrict language matching to Portugal.
  en: "en-GB", gl: "gl-ES", es: "es-ES", pt: "pt-PT",
};
const catalogues: Record<AppLocale, Record<MessageKey, string>> = {
  en: english,
  gl: galician,
  es: spanish,
  pt: portuguese,
};

export function intlLocale(locale: AppLocale): string {
  return intlLocales[locale];
}

export function parseLocale(value: string | null | undefined): AppLocale | null {
  const base = value?.trim().toLowerCase().split(/[-_]/)[0];
  return availableLocales.find((locale) => locale === base) ?? null;
}

export function resolveLocale(
  saved: string | null | undefined,
  browserLanguages: readonly string[] = [],
): AppLocale {
  const preference = parseLocale(saved);
  if (preference) return preference;
  for (const language of browserLanguages) {
    const supported = parseLocale(language);
    if (supported) return supported;
  }
  return "en";
}

export function formatLocalDateTime(value: string | Date, locale: AppLocale): string {
  return new Intl.DateTimeFormat(intlLocales[locale], {
    dateStyle: "medium", timeStyle: "short",
  }).format(new Date(value));
}

export function formatLocalNumber(value: number, locale: AppLocale): string {
  return new Intl.NumberFormat(intlLocales[locale]).format(value);
}

export function translate(
  locale: AppLocale,
  key: MessageKey,
  values: Record<string, string | number> = {},
): string {
  return catalogues[locale][key].replace(/\{(\w+)\}/g, (token, name: string) =>
    Object.hasOwn(values, name) ? String(values[name]) : token,
  );
}
