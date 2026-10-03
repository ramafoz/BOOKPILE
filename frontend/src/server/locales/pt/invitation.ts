import type { InvitationCatalogue } from "../../invitationCopy";

export const invitationPt: InvitationCatalogue = {
  account: (url) => `Convido-te a criar uma conta no BOOKPILE, um espaço privado para organizar a tua biblioteca pessoal. O convite só pode ser usado uma vez e expira após sete dias.\n\n${url}`,
  library: (url, libraryName, role, scope) => {
    if (role === "OWNER") return `Convido-te a partilhar a biblioteca «${libraryName}» no BOOKPILE como coproprietário/a com a mesma autoridade administrativa. O convite só pode ser usado uma vez e expira após sete dias.\n\n${url}`;
    const access = scope === "CATALOG_AND_MAP" ? "ver o catálogo e o mapa físico" : "ver o catálogo";
    return `Convido-te a ${access} da biblioteca «${libraryName}» no BOOKPILE. O convite só pode ser usado uma vez e expira após sete dias.\n\n${url}`;
  },
};
