import type { LocaleBundle } from "../../localeCatalogues";
import { spanish } from "../es";
import { authenticatedEs } from "../es/authenticated";
import { catalogueEs } from "../es/catalogue";
import { libraryAdminEs } from "../es/libraryAdmin";
import { invitationEs } from "../es/invitation";
import { loanEs } from "../es/loan";
import { mapEs } from "../es/map";
import { physicalEs } from "../es/physical";
import { profileEs } from "../es/profile";
import { readingEs } from "../es/reading";
import { statisticsEs } from "../es/statistics";

export const bundle = { messages: spanish, authenticated: authenticatedEs, catalogue: catalogueEs, libraryAdmin: libraryAdminEs, invitation: invitationEs, loan: loanEs, map: mapEs, physical: physicalEs, profile: profileEs, reading: readingEs, statistics: statisticsEs } satisfies LocaleBundle;
