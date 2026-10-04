import type { LocaleBundle } from "../../localeCatalogues";
import { simplifiedChinese } from "../zh";
import { authenticatedZh } from "../zh/authenticated";
import { catalogueZh } from "../zh/catalogue";
import { invitationZh } from "../zh/invitation";
import { libraryAdminZh } from "../zh/libraryAdmin";
import { loanZh } from "../zh/loan";
import { mapZh } from "../zh/map";
import { physicalZh } from "../zh/physical";
import { profileZh } from "../zh/profile";
import { readingZh } from "../zh/reading";
import { statisticsZh } from "../zh/statistics";

export const bundle = { messages: simplifiedChinese, authenticated: authenticatedZh, catalogue: catalogueZh, libraryAdmin: libraryAdminZh, invitation: invitationZh, loan: loanZh, map: mapZh, physical: physicalZh, profile: profileZh, reading: readingZh, statistics: statisticsZh } satisfies LocaleBundle;
