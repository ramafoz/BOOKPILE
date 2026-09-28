import { describe, expect, it } from "vitest";
import { readingCopy } from "./readingCopy";

describe("reading copy", () => {
  it("localizes states and interpolated history labels", () => {
    expect(readingCopy("gl")("rereading")).toBe("En relectura…");
    expect(readingCopy("gl")("readingNumber", { number: 2 })).toBe("Lectura 2");
    expect(readingCopy("en")("personalRecord", { name: "Alex" })).toBe("Alex's personal reading record");
  });
});
