import type { InvitationCatalogue } from "../../invitationCopy";

export const invitationOc: InvitationCatalogue = {
  account: (url) => `Te convidi a crear un compde en BOOKPILE, un espaci privat entà organizar era tua bibliotèca personau. Era invitacion sonque se pòt emplegar un còp e expire dempús de sèt dies.\n\n${url}`,
  library: (url, libraryName, role, scope) => {
    if (role === "OWNER") return `Te convidi a compartir era bibliotèca «${libraryName}» en BOOKPILE coma coproprietari/ària damb es madeishi poders d'administracion. Era invitacion sonque se pòt emplegar un còp e expire dempús de sèt dies.\n\n${url}`;
    const access = scope === "CATALOG_AND_MAP" ? "consultar eth catalòg e eth mapa fisic" : "consultar eth catalòg";
    return `Te convidi a ${access} dera bibliotèca «${libraryName}» en BOOKPILE. Era invitacion sonque se pòt emplegar un còp e expire dempús de sèt dies.\n\n${url}`;
  },
};
