import { describe, expect, it } from "vitest";
import { physicalCopy } from "./physicalCopy";

describe("physicalCopy", () => {
  it("keeps destructive and geometry copy complete", () => {
    expect(physicalCopy("gl")("deleteConfirm", { label: "Andel 2" })).toContain("Andel 2");
    expect(physicalCopy("en")("shelfFixedHelp", { dimensions: "Width", structure: "frames" })).toContain("frames");
  });
});
