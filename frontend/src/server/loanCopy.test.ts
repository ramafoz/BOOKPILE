import { describe, expect, it } from "vitest";
import { loanCopy } from "./loanCopy";

describe("loan copy", () => {
  it("localizes active and historical custody", () => {
    expect(loanCopy("gl")("onLoanTo", { borrower: "Alex" })).toBe("Prestado a Alex");
    expect(loanCopy("gl")("returnedRecord", { loaned: "1/1", returned: "2/1" }))
      .toBe("Prestado o 1/1 · devolto o 2/1");
  });
});
