import type { LocaleBundle } from "../../localeCatalogues";
import { aranese } from "../oc";
import { authenticatedOc } from "../oc/authenticated";
import { catalogueOc } from "../oc/catalogue";
import { invitationOc } from "../oc/invitation";
import { libraryAdminOc } from "../oc/libraryAdmin";
import { loanOc } from "../oc/loan";
import { mapOc } from "../oc/map";
import { physicalOc } from "../oc/physical";
import { profileOc } from "../oc/profile";
import { readingOc } from "../oc/reading";
import { statisticsOc } from "../oc/statistics";

export const bundle = { messages: aranese, authenticated: authenticatedOc, catalogue: catalogueOc, libraryAdmin: libraryAdminOc, invitation: invitationOc, loan: loanOc, map: mapOc, physical: physicalOc, profile: profileOc, reading: readingOc, statistics: statisticsOc } satisfies LocaleBundle;
