import { describe, expect, it } from "vitest";
import {
  availableLocales, english, formatLocalDateTime, formatLocalNumber,
  parseLocale, resolveLocale, translate,
} from "./locale";

describe("Server locale foundation", () => {
  it("exposes only reviewed locales", () => {
    expect(availableLocales).toEqual(["en", "gl"]);
  });

  it("prefers a valid saved choice, then the first supported browser language", () => {
    expect(resolveLocale("gl-ES", ["en-US"])).toBe("gl");
    expect(resolveLocale("unsupported", ["zh-CN", "gl-ES", "en-GB"])).toBe("gl");
    expect(resolveLocale(null, ["zh-CN"])).toBe("en");
    expect(parseLocale("pt-BR")).toBeNull();
  });

  it("translates fixed and parameterized copy", () => {
    expect(translate("gl", "signIn")).toBe("Iniciar sesión");
    expect(translate("gl", "tooManyAttemptsMinutesMany", { minutes: 3 })).toContain("3 minutos");
    expect(translate("en", "welcomeBack")).toBe("Welcome back");
  });

  it("provides non-empty translations with matching interpolation variables", () => {
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      const source = english[key];
      const translation = translate("gl", key);
      expect(translation.trim(), key).not.toBe("");
      expect(translation.match(/\{\w+\}/g) ?? [], key).toEqual(source.match(/\{\w+\}/g) ?? []);
    }
  });

  it("formats dates and numbers using the selected region", () => {
    const date = "2026-09-21T15:00:00Z";
    expect(formatLocalDateTime(date, "gl")).toBe(new Intl.DateTimeFormat("gl-ES", {
      dateStyle: "medium", timeStyle: "short",
    }).format(new Date(date)));
    expect(formatLocalNumber(1234.5, "gl")).toBe(new Intl.NumberFormat("gl-ES").format(1234.5));
  });
});
