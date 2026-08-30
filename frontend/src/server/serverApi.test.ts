import { afterEach, describe, expect, it, vi } from "vitest";
import { cookieValue, serverApi } from "./serverApi";

afterEach(() => vi.restoreAllMocks());

describe("cookieValue", () => {
  it("finds and decodes the named CSRF cookie", () => {
    expect(cookieValue(
      "theme=green; bookpile_csrf=a%2Fb%2Bc; other=value",
      "bookpile_csrf",
    )).toBe("a/b+c");
  });

  it("does not accept a cookie whose name merely shares a prefix", () => {
    expect(cookieValue("bookpile_csrf_old=value", "bookpile_csrf")).toBeNull();
  });
});

describe("empty accepted responses", () => {
  it("treats a successful 202 without JSON as completion", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 202 }),
    );

    await expect(
      serverApi.requestPasswordReset("reader@example.com"),
    ).resolves.toBeUndefined();
  });
});
