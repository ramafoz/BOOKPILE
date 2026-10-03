import type { LocaleBundle } from "../../localeCatalogues";
import { galician } from "../gl";
import { authenticatedGl } from "../gl/authenticated";
import { catalogueGl } from "../gl/catalogue";
import { libraryAdminGl } from "../gl/libraryAdmin";
import { invitationGl } from "../gl/invitation";
import { loanGl } from "../gl/loan";
import { mapGl } from "../gl/map";
import { physicalGl } from "../gl/physical";
import { profileGl } from "../gl/profile";
import { readingGl } from "../gl/reading";
import { statisticsGl } from "../gl/statistics";

export const bundle = { messages: galician, authenticated: authenticatedGl, catalogue: catalogueGl, libraryAdmin: libraryAdminGl, invitation: invitationGl, loan: loanGl, map: mapGl, physical: physicalGl, profile: profileGl, reading: readingGl, statistics: statisticsGl } satisfies LocaleBundle;
