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

describe("Catalan public copy", () => {
  it("matches every public key and interpolation marker", () => {
    expectEquivalent(english, catalan);
  });

  it("matches the completed small authenticated catalogues", () => {
    expectEquivalent(loanEn, loanCa);
    expectEquivalent(profileEn, profileCa);
    expectEquivalent(readingEn, readingCa);
    expectEquivalent(statisticsEn, statisticsCa);
  });
});
