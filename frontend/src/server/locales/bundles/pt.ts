import type { LocaleBundle } from "../../localeCatalogues";
import { portuguese } from "../pt";
import { authenticatedPt } from "../pt/authenticated";
import { cataloguePt } from "../pt/catalogue";
import { libraryAdminPt } from "../pt/libraryAdmin";
import { invitationPt } from "../pt/invitation";
import { loanPt } from "../pt/loan";
import { mapPt } from "../pt/map";
import { physicalPt } from "../pt/physical";
import { profilePt } from "../pt/profile";
import { readingPt } from "../pt/reading";
import { statisticsPt } from "../pt/statistics";

export const bundle = { messages: portuguese, authenticated: authenticatedPt, catalogue: cataloguePt, libraryAdmin: libraryAdminPt, invitation: invitationPt, loan: loanPt, map: mapPt, physical: physicalPt, profile: profilePt, reading: readingPt, statistics: statisticsPt } satisfies LocaleBundle;
