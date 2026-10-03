import { describe, expect, it } from "vitest";
import { authenticatedCopy, en as authenticatedEn } from "./authenticatedCopy";
import { authenticatedPt } from "./locales/pt/authenticated";
import { en as catalogueEn } from "./catalogueCopy";
import { cataloguePt } from "./locales/pt/catalogue";
import { friendlyError } from "./friendlyError";
import { accountInvitationMessage, libraryInvitationMessage } from "./invitationCopy";
import { en as libraryAdminEn } from "./libraryAdminCopy";
import { libraryAdminPt } from "./locales/pt/libraryAdmin";
import { en as loanEn } from "./loanCopy";
import { loanPt } from "./locales/pt/loan";
import { en as mapEn } from "./mapCopy";
import { mapPt } from "./locales/pt/map";
import { en as physicalEn } from "./physicalCopy";
import { physicalPt } from "./locales/pt/physical";
import { en as profileEn } from "./profileCopy";
import { profilePt } from "./locales/pt/profile";
import { en as readingEn } from "./readingCopy";
import { readingPt } from "./locales/pt/reading";
import { ServerApiError } from "./serverApi";
import { en as statisticsEn } from "./statisticsCopy";
import { statisticsPt } from "./locales/pt/statistics";
import { english } from "./locales/en";
import { portuguese } from "./locales/pt";
import { translate } from "./locale";

function placeholders(value: string): string[] {
  return (value.match(/\{\w+\}/g) ?? []).sort();
}

function expectComplete(source: Record<string, string>, translation: Record<string, string>): void {
  expect(Object.keys(translation).sort()).toEqual(Object.keys(source).sort());
  for (const key of Object.keys(source)) {
    expect(translation[key].trim(), key).not.toBe("");
    expect(placeholders(translation[key]), key).toEqual(placeholders(source[key]));
  }
}

describe("Portuguese copy", () => {
  it("keeps every completed catalogue structurally equivalent to English", () => {
    expectComplete(english, portuguese);
    expectComplete(authenticatedEn, authenticatedPt);
    expectComplete(catalogueEn, cataloguePt);
    expectComplete(libraryAdminEn, libraryAdminPt);
    expectComplete(loanEn, loanPt);
    expectComplete(mapEn, mapPt);
    expectComplete(physicalEn, physicalPt);
    expectComplete(profileEn, profilePt);
    expectComplete(readingEn, readingPt);
    expectComplete(statisticsEn, statisticsPt);
  });

  it("distinguishes account, viewer and co-owner invitations", () => {
    const url = "https://bookpile.gal/login?invite=private-token";
    expect(accountInvitationMessage("pt", url)).toContain("criar uma conta");
    expect(libraryInvitationMessage("pt", url, "Casa", "VIEWER", "CATALOG_ONLY"))
      .toContain("ver o catálogo");
    expect(libraryInvitationMessage("pt", url, "Casa", "VIEWER", "CATALOG_AND_MAP"))
      .toContain("mapa físico");
    expect(libraryInvitationMessage("pt", url, "Casa", "OWNER", null))
      .toContain("coproprietário/a");
  });

  it("localizes the current perspective and operational failures", () => {
    const t = (key: Parameters<typeof translate>[1], values?: Record<string, string | number>) =>
      translate("pt", key, values);
    expect(authenticatedCopy("pt")("self")).toBe("eu");
    expect(friendlyError(new ServerApiError("raw", 429, 120), t)).toContain("2 minutos");
    expect(friendlyError(new TypeError("network"), t)).toBe(
      "O BOOKPILE não conseguiu ligar ao servidor. Tente novamente.",
    );
  });
});
