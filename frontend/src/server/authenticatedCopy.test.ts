import { describe, expect, it } from "vitest";
import { authenticatedCopy } from "./authenticatedCopy";

describe("authenticated workspace copy", () => {
  it("renders English and Galician navigation independently", () => {
    expect(authenticatedCopy("en")("yourLibraries")).toBe("Your libraries");
    expect(authenticatedCopy("gl")("yourLibraries")).toBe("As túas bibliotecas");
  });

  it("interpolates account values", () => {
    expect(authenticatedCopy("gl")("typeUsername", { username: "ramafoz" }))
      .toBe("Escribe ramafoz exactamente");
  });

  it("leaves an unknown placeholder visible for diagnostics", () => {
    expect(authenticatedCopy("en")("typeUsername")).toContain("{username}");
  });
});
