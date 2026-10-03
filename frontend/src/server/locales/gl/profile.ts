import type { ProfileCopyKey } from "../../profileCopy";

export const profileGl = {
  openFailed: "Non se puido abrir este perfil.", closeProfile: "Pechar perfil", openingProfile: "Abrindo o perfil…",
  member: "Membro de BOOKPILE", timezone: "Fuso horario", gender: "Xénero", pronouns: "Pronomes", city: "Cidade", state: "Estado / rexión", country: "País", dateOfBirth: "Data de nacemento",
  female: "muller", male: "home", nonBinary: "non binario", other: "outro", they: "elu",
  empty: "Este membro non compartiu contigo ningún dato do seu perfil.",
} satisfies Record<ProfileCopyKey, string>;
