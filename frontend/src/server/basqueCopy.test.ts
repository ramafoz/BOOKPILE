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
import { authenticatedEu } from "./locales/eu/authenticated";
import { catalogueEu } from "./locales/eu/catalogue";
import { libraryAdminEu } from "./locales/eu/libraryAdmin";
import { loanEu } from "./locales/eu/loan";
import { mapEu } from "./locales/eu/map";
import { physicalEu } from "./locales/eu/physical";
import { profileEu } from "./locales/eu/profile";
import { readingEu } from "./locales/eu/reading";
import { statisticsEu } from "./locales/eu/statistics";

function expectBasqueEquivalent(source: Record<string, string>, translation: Record<string, string>) {
  expect(Object.keys(translation).sort()).toEqual(Object.keys(source).sort());
  for (const key of Object.keys(source)) {
    expect(translation[key].trim(), key).not.toBe("");
    expect(translation[key].match(/\{\w+\}/g) ?? [], key)
      .toEqual(source[key].match(/\{\w+\}/g) ?? []);
  }
}

describe("Basque copy", () => {
  it("matches every authenticated catalogue", () => {
    expectBasqueEquivalent(authenticatedEn, authenticatedEu);
    expectBasqueEquivalent(catalogueEn, catalogueEu);
    expectBasqueEquivalent(libraryAdminEn, libraryAdminEu);
    expectBasqueEquivalent(loanEn, loanEu);
    expectBasqueEquivalent(mapEn, mapEu);
    expectBasqueEquivalent(physicalEn, physicalEu);
    expectBasqueEquivalent(profileEn, profileEu);
    expectBasqueEquivalent(readingEn, readingEu);
    expectBasqueEquivalent(statisticsEn, statisticsEu);
  });

  it("warns that a promoted co-owner can remove the current owner", () => {
    expect(libraryAdminEu.promoteHelp).toContain("zure kidetza kendu");
    expect(libraryAdminEu.ownerAcknowledgement).toContain("nire kidetza kendu");
  });

  it("distinguishes every invitation permission", async () => {
    const { loadLocaleCatalogues } = await import("./localeCatalogues");
    await loadLocaleCatalogues("eu");
    const url = "https://bookpile.gal/login?library-invite=private-token";
    expect(accountInvitationMessage("eu", url)).toContain("kontu bat sortzera");
    expect(accountInvitationMessage("eu", url)).toContain(url);
    expect(libraryInvitationMessage("eu", url, "Etxea", "VIEWER", "CATALOG_ONLY"))
      .toContain("katalogoa ikustera");
    expect(libraryInvitationMessage("eu", url, "Etxea", "VIEWER", "CATALOG_AND_MAP"))
      .toContain("katalogoa eta mapa fisikoa");
    const owner = libraryInvitationMessage("eu", url, "Etxea", "OWNER", null);
    expect(owner).toContain("jabekide");
    expect(owner).toContain("administrazio-ahalmen berak");
  });
});
