import { describe, expect, it } from "vitest";
import { english } from "./locales/en";
import { catalan } from "./locales/ca";

describe("Catalan public copy", () => {
  it("matches every public key and interpolation marker", () => {
    expect(Object.keys(catalan).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      expect(catalan[key].trim(), key).not.toBe("");
      expect(catalan[key].match(/\{\w+\}/g) ?? [], key)
        .toEqual(english[key].match(/\{\w+\}/g) ?? []);
    }
  });
});
