import { describe, expect, it } from "vitest";
import { english } from "./locales/en";
import { catalan } from "./locales/ca";
import { en as loanEn } from "./loanCopy";
import { en as profileEn } from "./profileCopy";
import { en as readingEn } from "./readingCopy";
import { en as statisticsEn } from "./statisticsCopy";
import { loanCa } from "./locales/ca/loan";
import { profileCa } from "./locales/ca/profile";
import { readingCa } from "./locales/ca/reading";
import { statisticsCa } from "./locales/ca/statistics";
import { en as catalogueEn } from "./catalogueCopy";
import { catalogueCa } from "./locales/ca/catalogue";
import { en as authenticatedEn } from "./authenticatedCopy";
import { en as libraryAdminEn } from "./libraryAdminCopy";
import { authenticatedCa } from "./locales/ca/authenticated";
import { libraryAdminCa } from "./locales/ca/libraryAdmin";
import { en as mapEn } from "./mapCopy";
import { mapCa } from "./locales/ca/map";
import { en as physicalEn } from "./physicalCopy";
import { physicalCa } from "./locales/ca/physical";
import { accountInvitationMessage, libraryInvitationMessage } from "./invitationCopy";

function expectEquivalent(
  source: Record<string, string>,
  translation: Record<string, string>,
) {
  expect(Object.keys(translation).sort()).toEqual(Object.keys(source).sort());
  for (const key of Object.keys(source)) {
    expect(translation[key].trim(), key).not.toBe("");
    expect(translation[key].match(/\{\w+\}/g) ?? [], key)
      .toEqual(source[key].match(/\{\w+\}/g) ?? []);
  }
}

describe("Catalan copy", () => {
  it("matches every public key and interpolation marker", () => {
    expectEquivalent(english, catalan);
  });

  it("matches the completed small authenticated catalogues", () => {
    expectEquivalent(loanEn, loanCa);
    expectEquivalent(profileEn, profileCa);
    expectEquivalent(readingEn, readingCa);
    expectEquivalent(statisticsEn, statisticsCa);
    expectEquivalent(catalogueEn, catalogueCa);
    expectEquivalent(authenticatedEn, authenticatedCa);
    expectEquivalent(libraryAdminEn, libraryAdminCa);
    expectEquivalent(mapEn, mapCa);
    expectEquivalent(physicalEn, physicalCa);
  });

  it("distinguishes every prepared invitation permission", () => {
    const url = "https://bookpile.gal/login?library-invite=private-token";
    expect(accountInvitationMessage("ca", url)).toContain("crear un compte");
    expect(accountInvitationMessage("ca", url)).toContain(url);
    expect(libraryInvitationMessage("ca", url, "Casa", "VIEWER", "CATALOG_ONLY"))
      .toContain("veure el catàleg de");
    expect(libraryInvitationMessage("ca", url, "Casa", "VIEWER", "CATALOG_AND_MAP"))
      .toContain("catàleg i el mapa físic");
    const owner = libraryInvitationMessage("ca", url, "Casa", "OWNER", null);
    expect(owner).toContain("copropietari/ària");
    expect(owner).toContain("mateixa autoritat administrativa");
  });

  it("warns that a promoted co-owner can remove the current owner", () => {
    expect(libraryAdminCa.promoteHelp).toContain("eliminar la teva pertinença");
    expect(libraryAdminCa.promoteHelp).not.toContain("eliminar la seva pròpia pertinença");
  });
});
