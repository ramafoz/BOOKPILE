import type { InvitationCatalogue } from "../../invitationCopy";

export const invitationEs: InvitationCatalogue = {
  account: (url) => `Te invito a crear una cuenta en BOOKPILE, un espacio privado para organizar tu biblioteca personal. La invitación solo se puede usar una vez y caduca a los siete días.\n\n${url}`,
  library: (url, libraryName, role, scope) => {
    if (role === "OWNER") return `Te invito a compartir la biblioteca «${libraryName}» en BOOKPILE como copropietario/a con los mismos permisos de administración. La invitación solo se puede usar una vez y caduca a los siete días.\n\n${url}`;
    const access = scope === "CATALOG_AND_MAP" ? "ver el catálogo y el mapa físico" : "ver el catálogo";
    return `Te invito a ${access} de la biblioteca «${libraryName}» en BOOKPILE. La invitación solo se puede usar una vez y caduca a los siete días.\n\n${url}`;
  },
};
