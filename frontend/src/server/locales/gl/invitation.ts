import type { InvitationCatalogue } from "../../invitationCopy";

export const invitationGl: InvitationCatalogue = {
  account: (url) => `Convídote a crear unha conta en BOOKPILE, un espazo privado para organizar a túa biblioteca persoal. O convite é dun só uso e caduca aos sete días.\n\n${url}`,
  library: (url, libraryName, role, scope) => {
    if (role === "OWNER") return `Convídote a compartir a biblioteca «${libraryName}» en BOOKPILE como copropietario/a con iguais permisos de administración. Este convite é dun só uso e caduca aos sete días.\n\n${url}`;
    const access = scope === "CATALOG_AND_MAP" ? "ver o catálogo e o mapa físico" : "ver o catálogo";
    return `Convídote a ${access} da biblioteca «${libraryName}» en BOOKPILE. Este convite é dun só uso e caduca aos sete días.\n\n${url}`;
  },
};
