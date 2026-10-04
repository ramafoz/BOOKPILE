import type { InvitationCatalogue } from "../../invitationCopy";

export const invitationFr: InvitationCatalogue = {
  account: (url) => `Je vous invite à créer un compte sur BOOKPILE, un espace privé pour organiser votre bibliothèque personnelle. L’invitation ne peut être utilisée qu’une seule fois et expire au bout de sept jours.\n\n${url}`,
  library: (url, libraryName, role, scope) => {
    if (role === "OWNER") return `Je vous invite à partager la bibliothèque « ${libraryName} » sur BOOKPILE en tant que copropriétaire disposant des mêmes pouvoirs d’administration. L’invitation ne peut être utilisée qu’une seule fois et expire au bout de sept jours.\n\n${url}`;
    const access = scope === "CATALOG_AND_MAP" ? "consulter le catalogue et le plan physique" : "consulter le catalogue";
    return `Je vous invite à ${access} de la bibliothèque « ${libraryName} » sur BOOKPILE. L’invitation ne peut être utilisée qu’une seule fois et expire au bout de sept jours.\n\n${url}`;
  },
};
