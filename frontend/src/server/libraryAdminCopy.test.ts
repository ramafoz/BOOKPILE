import { describe, expect, it } from "vitest";
import { libraryAdminCopy } from "./libraryAdminCopy";

describe("libraryAdminCopy", () => {
  it("keeps permission and deletion warnings complete in both locales", () => {
    expect(libraryAdminCopy("en")("promoteTitle", { username: "ana" })).toContain("ana");
    expect(libraryAdminCopy("gl")("promoteHelp")).toContain("mesma autoridade");
    expect(libraryAdminCopy("gl")("deletionAcknowledgement")).toContain("definitivamente");
  });
});
