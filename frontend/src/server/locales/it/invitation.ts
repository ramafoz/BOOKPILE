import type { InvitationCatalogue } from "../../invitationCopy";

export const invitationIt: InvitationCatalogue = {
  account: (url) => `Ti invito a creare un account su BOOKPILE, uno spazio privato per organizzare la tua biblioteca personale. L'invito può essere utilizzato una sola volta e scade dopo sette giorni.\n\n${url}`,
  library: (url, libraryName, role, scope) => {
    if (role === "OWNER") return `Ti invito a condividere la biblioteca «${libraryName}» su BOOKPILE come coproprietario/a con la stessa autorità amministrativa. L'invito può essere utilizzato una sola volta e scade dopo sette giorni.\n\n${url}`;
    const access = scope === "CATALOG_AND_MAP" ? "vedere il catalogo e la mappa fisica" : "vedere il catalogo";
    return `Ti invito a ${access} della biblioteca «${libraryName}» su BOOKPILE. L'invito può essere utilizzato una sola volta e scade dopo sette giorni.\n\n${url}`;
  },
};
