import type { InvitationCatalogue } from "../../invitationCopy";

export const invitationCa: InvitationCatalogue = {
  account: (url) => `Et convido a crear un compte a BOOKPILE, un espai privat per organitzar la teva biblioteca personal. La invitació només es pot utilitzar una vegada i caduca al cap de set dies.\n\n${url}`,
  library: (url, libraryName, role, scope) => {
    if (role === "OWNER") return `Et convido a compartir la biblioteca «${libraryName}» a BOOKPILE com a copropietari/ària amb la mateixa autoritat administrativa. La invitació només es pot utilitzar una vegada i caduca al cap de set dies.\n\n${url}`;
    const access = scope === "CATALOG_AND_MAP" ? "veure el catàleg i el mapa físic" : "veure el catàleg";
    return `Et convido a ${access} de la biblioteca «${libraryName}» a BOOKPILE. La invitació només es pot utilitzar una vegada i caduca al cap de set dies.\n\n${url}`;
  },
};
