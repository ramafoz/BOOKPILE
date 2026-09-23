import { describe, expect, it } from "vitest";
import { catalogueCopy } from "./catalogueCopy";

describe("catalogue copy", () => {
  it("provides English and Galician catalogue labels", () => {
    expect(catalogueCopy("en")("physicalLocation")).toBe("Physical location");
    expect(catalogueCopy("gl")("physicalLocation")).toBe("Localización física");
  });

  it("interpolates dynamic catalogue values", () => {
    expect(catalogueCopy("gl")("pageCount", { count: 434 })).toBe("434 páxinas");
    expect(catalogueCopy("en")("onLoanTo", { borrower: "Alex" })).toBe("On loan to Alex");
  });

  it("keeps missing interpolation values visible", () => {
    expect(catalogueCopy("gl")("usersBooks")).toContain("{username}");
  });
});
