import type { LocaleBundle } from "../../localeCatalogues";
import { catalan } from "../ca";
import { authenticatedCa } from "../ca/authenticated";
import { catalogueCa } from "../ca/catalogue";
import { libraryAdminCa } from "../ca/libraryAdmin";
import { invitationCa } from "../ca/invitation";
import { loanCa } from "../ca/loan";
import { mapCa } from "../ca/map";
import { physicalCa } from "../ca/physical";
import { profileCa } from "../ca/profile";
import { readingCa } from "../ca/reading";
import { statisticsCa } from "../ca/statistics";

export const bundle = { messages: catalan, authenticated: authenticatedCa, catalogue: catalogueCa, libraryAdmin: libraryAdminCa, invitation: invitationCa, loan: loanCa, map: mapCa, physical: physicalCa, profile: profileCa, reading: readingCa, statistics: statisticsCa } satisfies LocaleBundle;
