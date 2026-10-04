import type { InvitationCatalogue } from "../../invitationCopy";

export const invitationEu: InvitationCatalogue = {
  account: (url) => `BOOKPILEn kontu bat sortzera gonbidatzen zaitut, zure liburutegi pertsonala antolatzeko gune pribatuan. Gonbidapena behin bakarrik erabil daiteke eta zazpi egun barru iraungitzen da.\n\n${url}`,
  library: (url, libraryName, role, scope) => {
    if (role === "OWNER") return `BOOKPILEko «${libraryName}» liburutegia nirekin partekatzera gonbidatzen zaitut, administrazio-ahalmen berak dituen jabekide gisa. Gonbidapena behin bakarrik erabil daiteke eta zazpi egun barru iraungitzen da.\n\n${url}`;
    const access = scope === "CATALOG_AND_MAP" ? "katalogoa eta mapa fisikoa ikustera" : "katalogoa ikustera";
    return `BOOKPILEko «${libraryName}» liburutegiaren ${access} gonbidatzen zaitut. Gonbidapena behin bakarrik erabil daiteke eta zazpi egun barru iraungitzen da.\n\n${url}`;
  },
};
