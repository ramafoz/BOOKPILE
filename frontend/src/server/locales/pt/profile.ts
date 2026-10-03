import type { ProfileCopyKey } from "../../profileCopy";

export const profilePt = {
  openFailed: "Não foi possível abrir este perfil.", closeProfile: "Fechar perfil", openingProfile: "A abrir o perfil…", member: "Membro do BOOKPILE", timezone: "Fuso horário", gender: "Género", pronouns: "Pronomes", city: "Cidade", state: "Distrito / região", country: "País", dateOfBirth: "Data de nascimento", female: "mulher", male: "homem", nonBinary: "não binário", other: "outro", they: "elu", empty: "Este membro não partilhou consigo quaisquer dados do perfil.",
} satisfies Record<ProfileCopyKey, string>;

