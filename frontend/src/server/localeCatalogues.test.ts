import { describe, expect, it, vi } from "vitest";

describe("deferred locale catalogues", () => {
  it("starts with English only and installs a requested locale atomically", async () => {
    vi.resetModules();
    const catalogues = await import("./localeCatalogues");
    const locale = await import("./locale");

    expect(catalogues.isLocaleLoaded("en")).toBe(true);
    expect(catalogues.isLocaleLoaded("gl")).toBe(false);
    expect(() => locale.translate("gl", "welcomeBack")).toThrow("Locale catalogue not loaded: gl");

    await catalogues.loadLocaleCatalogues("gl");

    expect(catalogues.isLocaleLoaded("gl")).toBe(true);
    expect(locale.translate("gl", "welcomeBack")).toBe("Dámosche a benvida");
  });

  it("shares one in-flight request for the same locale", async () => {
    vi.resetModules();
    const { loadLocaleCatalogues } = await import("./localeCatalogues");

    const first = loadLocaleCatalogues("es");
    const second = loadLocaleCatalogues("es");

    expect(second).toBe(first);
    await first;
  });
});
