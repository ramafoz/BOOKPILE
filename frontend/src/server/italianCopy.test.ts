import { describe, expect, it } from "vitest";
import { english } from "./locales/en";
import { italian } from "./locales/it";
import { en as loanEn } from "./loanCopy";
import { en as profileEn } from "./profileCopy";
import { en as readingEn } from "./readingCopy";
import { en as statisticsEn } from "./statisticsCopy";
import { loanIt } from "./locales/it/loan";
import { profileIt } from "./locales/it/profile";
import { readingIt } from "./locales/it/reading";
import { statisticsIt } from "./locales/it/statistics";
import { en as catalogueEn } from "./catalogueCopy";
import { en as authenticatedEn } from "./authenticatedCopy";
import { catalogueIt } from "./locales/it/catalogue";
import { authenticatedIt } from "./locales/it/authenticated";
import { en as libraryAdminEn } from "./libraryAdminCopy";
import { libraryAdminIt } from "./locales/it/libraryAdmin";
import { en as mapEn } from "./mapCopy";
import { en as physicalEn } from "./physicalCopy";
import { mapIt } from "./locales/it/map";
import { physicalIt } from "./locales/it/physical";
import { accountInvitationMessage, libraryInvitationMessage } from "./invitationCopy";

export function expectItalianEquivalent(source: Record<string, string>, translation: Record<string, string>) {
  expect(Object.keys(translation).sort()).toEqual(Object.keys(source).sort());
  for (const key of Object.keys(source)) {
    expect(translation[key].trim(), key).not.toBe("");
    expect(translation[key].match(/\{\w+\}/g) ?? [], key)
      .toEqual(source[key].match(/\{\w+\}/g) ?? []);
  }
}

describe("Italian prepared copy", () => {
  it("matches the public and small authenticated catalogues", () => {
    expectItalianEquivalent(english, italian);
    expectItalianEquivalent(loanEn, loanIt);
    expectItalianEquivalent(profileEn, profileIt);
    expectItalianEquivalent(readingEn, readingIt);
    expectItalianEquivalent(statisticsEn, statisticsIt);
    expectItalianEquivalent(catalogueEn, catalogueIt);
    expectItalianEquivalent(authenticatedEn, authenticatedIt);
    expectItalianEquivalent(libraryAdminEn, libraryAdminIt);
    expectItalianEquivalent(mapEn, mapIt);
    expectItalianEquivalent(physicalEn, physicalIt);
  });

  it("warns that a promoted co-owner can remove the current owner", () => {
    expect(libraryAdminIt.promoteHelp).toContain("rimuovere la tua appartenenza");
    expect(libraryAdminIt.ownerAcknowledgement).toContain("rimuovere la mia appartenenza");
  });

  it("distinguishes every Italian invitation permission", () => {
    const url = "https://bookpile.gal/login?library-invite=private-token";
    expect(accountInvitationMessage("it", url)).toContain("creare un account");
    expect(accountInvitationMessage("it", url)).toContain(url);
    expect(libraryInvitationMessage("it", url, "Casa", "VIEWER", "CATALOG_ONLY"))
      .toContain("vedere il catalogo della");
    expect(libraryInvitationMessage("it", url, "Casa", "VIEWER", "CATALOG_AND_MAP"))
      .toContain("catalogo e la mappa fisica");
    const owner = libraryInvitationMessage("it", url, "Casa", "OWNER", null);
    expect(owner).toContain("coproprietario/a");
    expect(owner).toContain("stessa autorità amministrativa");
  });
});
