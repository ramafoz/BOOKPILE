import { describe, expect, it } from "vitest";
import { statisticsCopy } from "./statisticsCopy";

describe("statisticsCopy", () => {
  it("formats English and Galician statistics labels", () => {
    expect(statisticsCopy("en")("usersStatistics", { username: "ana" })).toBe("ana's statistics");
    expect(statisticsCopy("gl")("usersStatistics", { username: "ana" })).toBe("Estatísticas de ana");
    expect(statisticsCopy("gl")("unknownDateSummary", { loaned: 2, returned: 3 })).toContain("2 prestados");
  });
});
