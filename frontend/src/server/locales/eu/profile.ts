import type { ProfileCopyKey } from "../../profileCopy";

export const profileEu = {
  openFailed: "Ezin izan da profila ireki.", closeProfile: "Itxi profila", openingProfile: "Profila irekitzen…", member: "BOOKPILEko kidea", timezone: "Ordu-zona", gender: "Generoa", pronouns: "Izenordainak", city: "Hiria", state: "Probintzia / eskualdea", country: "Herrialdea", dateOfBirth: "Jaioteguna", female: "emakumea", male: "gizona", nonBinary: "ez-bitarra", other: "beste bat", they: "hura", empty: "Kide honek ez du zurekin profileko informaziorik partekatu.",
} satisfies Record<ProfileCopyKey, string>;
