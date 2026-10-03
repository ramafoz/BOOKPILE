import type { LocaleBundle } from "../../localeCatalogues";
import { italian } from "../it";
import { authenticatedIt } from "../it/authenticated";
import { catalogueIt } from "../it/catalogue";
import { libraryAdminIt } from "../it/libraryAdmin";
import { invitationIt } from "../it/invitation";
import { loanIt } from "../it/loan";
import { mapIt } from "../it/map";
import { physicalIt } from "../it/physical";
import { profileIt } from "../it/profile";
import { readingIt } from "../it/reading";
import { statisticsIt } from "../it/statistics";

export const bundle = { messages: italian, authenticated: authenticatedIt, catalogue: catalogueIt, libraryAdmin: libraryAdminIt, invitation: invitationIt, loan: loanIt, map: mapIt, physical: physicalIt, profile: profileIt, reading: readingIt, statistics: statisticsIt } satisfies LocaleBundle;
