import type { LocaleBundle } from "../../localeCatalogues";
import { french } from "../fr";
import { authenticatedFr } from "../fr/authenticated";
import { catalogueFr } from "../fr/catalogue";
import { invitationFr } from "../fr/invitation";
import { libraryAdminFr } from "../fr/libraryAdmin";
import { loanFr } from "../fr/loan";
import { mapFr } from "../fr/map";
import { physicalFr } from "../fr/physical";
import { profileFr } from "../fr/profile";
import { readingFr } from "../fr/reading";
import { statisticsFr } from "../fr/statistics";

export const bundle = { messages: french, authenticated: authenticatedFr, catalogue: catalogueFr, libraryAdmin: libraryAdminFr, invitation: invitationFr, loan: loanFr, map: mapFr, physical: physicalFr, profile: profileFr, reading: readingFr, statistics: statisticsFr } satisfies LocaleBundle;
