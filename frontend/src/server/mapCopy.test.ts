import { describe, expect, it } from "vitest";
import { mapCopy } from "./mapCopy";

describe("mapCopy", () => {
  it("formats map and computed legend copy", () => {
    expect(mapCopy("gl")("inspectionMode", { mode: "libros" })).toContain("libros");
    expect(mapCopy("en")("endpointTie", { adjective: "Oldest", count: 2, value: "2020" })).toContain("tie (2)");
    expect(mapCopy("gl")("booksShifted", { count: 3, reason: mapCopy("gl")("makeRoom") })).toContain("3 libros");
  });
});
