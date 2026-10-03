import type { ProfileCopyKey } from "../../profileCopy";

export const profileEs = {
  openFailed: "No se ha podido abrir este perfil.", closeProfile: "Cerrar perfil", openingProfile: "Abriendo el perfil…",
  member: "Miembro de BOOKPILE", timezone: "Zona horaria", gender: "Género", pronouns: "Pronombres", city: "Ciudad", state: "Provincia / región", country: "País", dateOfBirth: "Fecha de nacimiento",
  female: "mujer", male: "hombre", nonBinary: "no binario", other: "otro", they: "elle",
  empty: "Este miembro no ha compartido contigo ningún dato de su perfil.",
} satisfies Record<ProfileCopyKey, string>;
