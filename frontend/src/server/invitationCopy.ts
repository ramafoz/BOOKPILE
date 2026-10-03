import type { AppLocale } from "./locale";

export type LibraryInvitationRole = "OWNER" | "VIEWER";
export type LibraryInvitationScope = "CATALOG_ONLY" | "CATALOG_AND_MAP" | null;

export interface InvitationCatalogue {
  account: (url: string) => string;
  library: (url: string, libraryName: string, role: LibraryInvitationRole, scope: LibraryInvitationScope) => string;
}

export const invitationEn: InvitationCatalogue = {
  account: (url) => `I invite you to create an account on BOOKPILE, a private space for organising your personal library. This invitation can only be used once and expires after seven days.\n\n${url}`,
  library: (url, libraryName, role, scope) => {
    if (role === "OWNER") return `I invite you to share the “${libraryName}” library on BOOKPILE as an equal co-Owner with the same administrative authority. This invitation can only be used once and expires after seven days.\n\n${url}`;
    const access = scope === "CATALOG_AND_MAP" ? "view the catalogue and physical map of" : "view the catalogue of";
    return `I invite you to ${access} the “${libraryName}” library on BOOKPILE. This invitation can only be used once and expires after seven days.\n\n${url}`;
  },
};

const catalogues: Partial<Record<AppLocale, InvitationCatalogue>> = { en: invitationEn };

export function registerInvitationCatalogue(locale: AppLocale, catalogue: InvitationCatalogue): void {
  catalogues[locale] = catalogue;
}

function invitationCatalogue(locale: AppLocale): InvitationCatalogue {
  const catalogue = catalogues[locale];
  if (!catalogue) throw new Error(`Locale catalogue not loaded: ${locale}`);
  return catalogue;
}

export function accountInvitationMessage(locale: AppLocale, url: string): string {
  return invitationCatalogue(locale).account(url);
}

export function libraryInvitationMessage(locale: AppLocale, url: string, libraryName: string, role: LibraryInvitationRole, scope: LibraryInvitationScope): string {
  return invitationCatalogue(locale).library(url, libraryName, role, scope);
}
