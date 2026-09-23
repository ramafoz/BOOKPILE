import { describe, expect, it } from "vitest";
import { profileCopy } from "./profileCopy";

describe("profileCopy", () => {
  it("provides complete English and Galician profile copy", () => {
    expect(profileCopy("en")("closeProfile")).toBe("Close profile");
    expect(profileCopy("gl")("closeProfile")).toBe("Pechar perfil");
    expect(profileCopy("gl")("dateOfBirth")).toBe("Data de nacemento");
  });
});
