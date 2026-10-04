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
import { authenticatedZh } from "./locales/zh/authenticated";
import { catalogueZh } from "./locales/zh/catalogue";
import { libraryAdminZh } from "./locales/zh/libraryAdmin";
import { loanZh } from "./locales/zh/loan";
import { mapZh } from "./locales/zh/map";
import { physicalZh } from "./locales/zh/physical";
import { profileZh } from "./locales/zh/profile";
import { readingZh } from "./locales/zh/reading";
import { statisticsZh } from "./locales/zh/statistics";

function expectChineseEquivalent(source: Record<string, string>, translation: Record<string, string>) {
  expect(Object.keys(translation).sort()).toEqual(Object.keys(source).sort());
  for (const key of Object.keys(source)) {
    expect(translation[key].trim(), key).not.toBe("");
    expect(translation[key].match(/\{\w+\}/g) ?? [], key)
      .toEqual(source[key].match(/\{\w+\}/g) ?? []);
  }
}

describe("Simplified Chinese copy", () => {
  it("matches every authenticated catalogue", () => {
    expectChineseEquivalent(authenticatedEn, authenticatedZh);
    expectChineseEquivalent(catalogueEn, catalogueZh);
    expectChineseEquivalent(libraryAdminEn, libraryAdminZh);
    expectChineseEquivalent(loanEn, loanZh);
    expectChineseEquivalent(mapEn, mapZh);
    expectChineseEquivalent(physicalEn, physicalZh);
    expectChineseEquivalent(profileEn, profileZh);
    expectChineseEquivalent(readingEn, readingZh);
    expectChineseEquivalent(statisticsEn, statisticsZh);
  });

  it("warns that a promoted co-owner can remove the current owner", () => {
    expect(libraryAdminZh.promoteHelp).toContain("移除您的成员关系");
    expect(libraryAdminZh.ownerAcknowledgement).toContain("移除我的成员关系");
  });

  it("distinguishes every invitation permission", async () => {
    const { loadLocaleCatalogues } = await import("./localeCatalogues");
    await loadLocaleCatalogues("zh");
    const url = "https://bookpile.gal/login?library-invite=private-token";
    expect(accountInvitationMessage("zh", url)).toContain("在 BOOKPILE 创建账户");
    expect(accountInvitationMessage("zh", url)).toContain(url);
    expect(libraryInvitationMessage("zh", url, "家庭书库", "VIEWER", "CATALOG_ONLY"))
      .toContain("查看目录");
    expect(libraryInvitationMessage("zh", url, "家庭书库", "VIEWER", "CATALOG_AND_MAP"))
      .toContain("目录和实体地图");
    const owner = libraryInvitationMessage("zh", url, "家庭书库", "OWNER", null);
    expect(owner).toContain("共同所有者");
    expect(owner).toContain("相同的管理权限");
  });
});
