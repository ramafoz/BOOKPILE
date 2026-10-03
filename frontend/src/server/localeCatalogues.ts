import type { AuthenticatedCopyKey } from "./authenticatedCopy";
import { registerAuthenticatedCatalogue } from "./authenticatedCopy";
import type { CatalogueCopyKey } from "./catalogueCopy";
import { registerCatalogueCatalogue } from "./catalogueCopy";
import type { LibraryAdminCopyKey } from "./libraryAdminCopy";
import { registerLibraryAdminCatalogue } from "./libraryAdminCopy";
import type { InvitationCatalogue } from "./invitationCopy";
import { registerInvitationCatalogue } from "./invitationCopy";
import type { LoanCopyKey } from "./loanCopy";
import { registerLoanCatalogue } from "./loanCopy";
import type { MapCopyKey } from "./mapCopy";
import { registerMapCatalogue } from "./mapCopy";
import type { PhysicalCopyKey } from "./physicalCopy";
import { registerPhysicalCatalogue } from "./physicalCopy";
import type { ProfileCopyKey } from "./profileCopy";
import { registerProfileCatalogue } from "./profileCopy";
import type { ReadingCopyKey } from "./readingCopy";
import { registerReadingCatalogue } from "./readingCopy";
import type { StatisticsCopyKey } from "./statisticsCopy";
import { registerStatisticsCatalogue } from "./statisticsCopy";
import {
  registerMessageCatalogue,
  type AppLocale,
  type MessageKey,
} from "./locale";

export interface LocaleBundle {
  messages: Record<MessageKey, string>;
  authenticated: Record<AuthenticatedCopyKey, string>;
  catalogue: Record<CatalogueCopyKey, string>;
  libraryAdmin: Record<LibraryAdminCopyKey, string>;
  invitation: InvitationCatalogue;
  loan: Record<LoanCopyKey, string>;
  map: Record<MapCopyKey, string>;
  physical: Record<PhysicalCopyKey, string>;
  profile: Record<ProfileCopyKey, string>;
  reading: Record<ReadingCopyKey, string>;
  statistics: Record<StatisticsCopyKey, string>;
}

type DeferredLocale = Exclude<AppLocale, "en">;
type BundleModule = { bundle: LocaleBundle };

const loaders: Record<DeferredLocale, () => Promise<BundleModule>> = {
  gl: () => import("./locales/bundles/gl"),
  es: () => import("./locales/bundles/es"),
  pt: () => import("./locales/bundles/pt"),
  ca: () => import("./locales/bundles/ca"),
  it: () => import("./locales/bundles/it"),
};
const loaded = new Set<AppLocale>(["en"]);
const pending = new Map<AppLocale, Promise<void>>();

function install(locale: AppLocale, bundle: LocaleBundle): void {
  registerMessageCatalogue(locale, bundle.messages);
  registerAuthenticatedCatalogue(locale, bundle.authenticated);
  registerCatalogueCatalogue(locale, bundle.catalogue);
  registerLibraryAdminCatalogue(locale, bundle.libraryAdmin);
  registerInvitationCatalogue(locale, bundle.invitation);
  registerLoanCatalogue(locale, bundle.loan);
  registerMapCatalogue(locale, bundle.map);
  registerPhysicalCatalogue(locale, bundle.physical);
  registerProfileCatalogue(locale, bundle.profile);
  registerReadingCatalogue(locale, bundle.reading);
  registerStatisticsCatalogue(locale, bundle.statistics);
}

export function isLocaleLoaded(locale: AppLocale): boolean {
  return loaded.has(locale);
}

export function loadLocaleCatalogues(locale: AppLocale): Promise<void> {
  if (loaded.has(locale)) return Promise.resolve();
  const existing = pending.get(locale);
  if (existing) return existing;
  const request = loaders[locale as DeferredLocale]().then(({ bundle }) => {
    install(locale, bundle);
    loaded.add(locale);
    pending.delete(locale);
  }).catch((error: unknown) => {
    pending.delete(locale);
    throw error;
  });
  pending.set(locale, request);
  return request;
}
