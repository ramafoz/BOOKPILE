import { describe, expect, it } from "vitest";
import { nextInspectionId } from "./mapInspection";

describe("map inspection selection", () => {
  it("selects and changes inspected items", () => {
    expect(nextInspectionId(null, 4)).toBe(4);
    expect(nextInspectionId(4, 8)).toBe(8);
  });

  it("deselects the current item unless its details are being opened", () => {
    expect(nextInspectionId(4, 4)).toBeNull();
    expect(nextInspectionId(4, 4, true)).toBe(4);
  });
});
