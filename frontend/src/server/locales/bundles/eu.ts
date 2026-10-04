import type { LocaleBundle } from "../../localeCatalogues";
import { basque } from "../eu";
import { authenticatedEu } from "../eu/authenticated";
import { catalogueEu } from "../eu/catalogue";
import { invitationEu } from "../eu/invitation";
import { libraryAdminEu } from "../eu/libraryAdmin";
import { loanEu } from "../eu/loan";
import { mapEu } from "../eu/map";
import { physicalEu } from "../eu/physical";
import { profileEu } from "../eu/profile";
import { readingEu } from "../eu/reading";
import { statisticsEu } from "../eu/statistics";

export const bundle = { messages: basque, authenticated: authenticatedEu, catalogue: catalogueEu, libraryAdmin: libraryAdminEu, invitation: invitationEu, loan: loanEu, map: mapEu, physical: physicalEu, profile: profileEu, reading: readingEu, statistics: statisticsEu } satisfies LocaleBundle;
