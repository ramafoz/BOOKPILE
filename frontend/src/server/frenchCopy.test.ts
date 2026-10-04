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
import { authenticatedFr } from "./locales/fr/authenticated";
import { catalogueFr } from "./locales/fr/catalogue";
import { libraryAdminFr } from "./locales/fr/libraryAdmin";
import { loanFr } from "./locales/fr/loan";
import { mapFr } from "./locales/fr/map";
import { physicalFr } from "./locales/fr/physical";
import { profileFr } from "./locales/fr/profile";
import { readingFr } from "./locales/fr/reading";
import { statisticsFr } from "./locales/fr/statistics";

function expectFrenchEquivalent(source: Record<string, string>, translation: Record<string, string>) {
  expect(Object.keys(translation).sort()).toEqual(Object.keys(source).sort());
  for (const key of Object.keys(source)) {
    expect(translation[key].trim(), key).not.toBe("");
    expect(translation[key].match(/\{\w+\}/g) ?? [], key)
      .toEqual(source[key].match(/\{\w+\}/g) ?? []);
  }
}

describe("French copy", () => {
  it("matches every authenticated catalogue", () => {
    expectFrenchEquivalent(authenticatedEn, authenticatedFr);
    expectFrenchEquivalent(catalogueEn, catalogueFr);
    expectFrenchEquivalent(libraryAdminEn, libraryAdminFr);
    expectFrenchEquivalent(loanEn, loanFr);
    expectFrenchEquivalent(mapEn, mapFr);
    expectFrenchEquivalent(physicalEn, physicalFr);
    expectFrenchEquivalent(profileEn, profileFr);
    expectFrenchEquivalent(readingEn, readingFr);
    expectFrenchEquivalent(statisticsEn, statisticsFr);
  });

  it("warns that a promoted co-owner can remove the current owner", () => {
    expect(libraryAdminFr.promoteHelp).toContain("supprimer votre appartenance");
    expect(libraryAdminFr.ownerAcknowledgement).toContain("supprimer mon appartenance");
  });

  it("distinguishes every invitation permission", async () => {
    const { loadLocaleCatalogues } = await import("./localeCatalogues");
    await loadLocaleCatalogues("fr");
    const url = "https://bookpile.gal/login?library-invite=private-token";
    expect(accountInvitationMessage("fr", url)).toContain("créer un compte");
    expect(accountInvitationMessage("fr", url)).toContain(url);
    expect(libraryInvitationMessage("fr", url, "Maison", "VIEWER", "CATALOG_ONLY"))
      .toContain("consulter le catalogue de la bibliothèque");
    expect(libraryInvitationMessage("fr", url, "Maison", "VIEWER", "CATALOG_AND_MAP"))
      .toContain("catalogue et le plan physique");
    const owner = libraryInvitationMessage("fr", url, "Maison", "OWNER", null);
    expect(owner).toContain("copropriétaire");
    expect(owner).toContain("mêmes pouvoirs d’administration");
  });
});
