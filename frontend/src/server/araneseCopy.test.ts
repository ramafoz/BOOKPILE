import { describe, expect, it } from "vitest";
import { en as authenticatedEn } from "./authenticatedCopy";
import { en as catalogueEn } from "./catalogueCopy";
import { accountInvitationMessage, libraryInvitationMessage } from "./invitationCopy";
import { en as libraryAdminEn } from "./libraryAdminCopy";
import { en as loanEn } from "./loanCopy";
import { en as mapEn } from "./mapCopy";
import { en as physicalEn } from "./physicalCopy";
import { en as profileEn } from "./profileCopy";
import { en as readingEn } from "./readingCopy";
import { en as statisticsEn } from "./statisticsCopy";
import { authenticatedOc } from "./locales/oc/authenticated";
import { catalogueOc } from "./locales/oc/catalogue";
import { libraryAdminOc } from "./locales/oc/libraryAdmin";
import { loanOc } from "./locales/oc/loan";
import { mapOc } from "./locales/oc/map";
import { physicalOc } from "./locales/oc/physical";
import { profileOc } from "./locales/oc/profile";
import { readingOc } from "./locales/oc/reading";
import { statisticsOc } from "./locales/oc/statistics";

function expectAraneseEquivalent(source: Record<string, string>, translation: Record<string, string>) {
  expect(Object.keys(translation).sort()).toEqual(Object.keys(source).sort());
  for (const key of Object.keys(source)) {
    expect(translation[key].trim(), key).not.toBe("");
    expect(translation[key].match(/\{\w+\}/g) ?? [], key)
      .toEqual(source[key].match(/\{\w+\}/g) ?? []);
  }
}

describe("Aranese copy", () => {
  it("matches every authenticated catalogue", () => {
    expectAraneseEquivalent(authenticatedEn, authenticatedOc);
    expectAraneseEquivalent(catalogueEn, catalogueOc);
    expectAraneseEquivalent(libraryAdminEn, libraryAdminOc);
    expectAraneseEquivalent(loanEn, loanOc);
    expectAraneseEquivalent(mapEn, mapOc);
    expectAraneseEquivalent(physicalEn, physicalOc);
    expectAraneseEquivalent(profileEn, profileOc);
    expectAraneseEquivalent(readingEn, readingOc);
    expectAraneseEquivalent(statisticsEn, statisticsOc);
  });

  it("warns that a promoted co-owner can remove the current owner", () => {
    expect(libraryAdminOc.promoteHelp).toContain("eliminar era tua membresia");
    expect(libraryAdminOc.ownerAcknowledgement).toContain("eliminar era mia membresia");
  });

  it("distinguishes every invitation permission", async () => {
    const { loadLocaleCatalogues } = await import("./localeCatalogues");
    await loadLocaleCatalogues("oc");
    const url = "https://bookpile.gal/login?library-invite=private-token";
    expect(accountInvitationMessage("oc", url)).toContain("crear un compde");
    expect(accountInvitationMessage("oc", url)).toContain(url);
    expect(libraryInvitationMessage("oc", url, "Ostal", "VIEWER", "CATALOG_ONLY"))
      .toContain("consultar eth catalòg");
    expect(libraryInvitationMessage("oc", url, "Ostal", "VIEWER", "CATALOG_AND_MAP"))
      .toContain("catalòg e eth mapa fisic");
    const owner = libraryInvitationMessage("oc", url, "Ostal", "OWNER", null);
    expect(owner).toContain("coproprietari");
    expect(owner).toContain("madeishi poders d'administracion");
  });
});
