import { describe, expect, it } from "vitest";
import {
  availableLocales, english, formatLocalDateTime, formatLocalNumber,
  parseLocale, resolveLocale, translate,
} from "./locale";
import { galician } from "./locales/gl";
import { spanish } from "./locales/es";
import { portuguese } from "./locales/pt";
import { catalan } from "./locales/ca";
import { italian } from "./locales/it";
import { french } from "./locales/fr";
import { basque } from "./locales/eu";
import { aranese } from "./locales/oc";
import { simplifiedChinese } from "./locales/zh";

describe("Server locale foundation", () => {
  it("exposes only reviewed locales", () => {
    expect(availableLocales).toEqual(["en", "gl", "es", "pt", "ca", "it", "fr", "eu", "oc", "zh"]);
    expect(parseLocale("es-ES")).toBe("es");
    expect(parseLocale("pt-PT")).toBe("pt");
    expect(parseLocale("pt-BR")).toBe("pt");
    expect(parseLocale("ca-ES")).toBe("ca");
    expect(parseLocale("ca-AD")).toBe("ca");
    expect(parseLocale("it-IT")).toBe("it");
    expect(parseLocale("fr-FR")).toBe("fr");
    expect(parseLocale("eu-ES")).toBe("eu");
    expect(parseLocale("oc-ES")).toBe("oc");
    expect(parseLocale("zh-CN")).toBe("zh");
    expect(parseLocale("zh-SG")).toBe("zh");
    expect(parseLocale("zh-Hans-CN")).toBe("zh");
    expect(parseLocale("zh-TW")).toBeNull();
    expect(parseLocale("zh-HK")).toBeNull();
    expect(parseLocale("zh-Hant")).toBeNull();
  });

  it("keeps Spanish entry copy complete", () => {
    expect(Object.keys(spanish).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      expect(spanish[key].trim(), key).not.toBe("");
      expect(spanish[key].match(/\{\w+\}/g) ?? [], key)
        .toEqual(english[key].match(/\{\w+\}/g) ?? []);
    }
  });

  it("prefers a valid saved choice, then the first supported browser language", () => {
    expect(resolveLocale("gl-ES", ["en-US"])).toBe("gl");
    expect(resolveLocale("unsupported", ["zh-TW", "gl-ES", "en-GB"])).toBe("gl");
    expect(resolveLocale(null, ["pt-PT", "en-GB"])).toBe("pt");
    expect(resolveLocale(null, ["pt-BR", "en-GB"])).toBe("pt");
    expect(resolveLocale(null, ["ca-ES", "en-GB"])).toBe("ca");
    expect(resolveLocale(null, ["it-CH", "en-GB"])).toBe("it");
    expect(resolveLocale(null, ["fr-CA", "en-GB"])).toBe("fr");
    expect(resolveLocale(null, ["eu-ES", "en-GB"])).toBe("eu");
    expect(resolveLocale(null, ["oc-ES", "en-GB"])).toBe("oc");
    expect(resolveLocale(null, ["zh-CN"])).toBe("zh");
    expect(resolveLocale(null, ["zh-Hans-SG"])).toBe("zh");
    expect(resolveLocale("zh", ["en-GB"])).toBe("zh");
    expect(resolveLocale(null, ["zh", "en-GB"])).toBe("en");
    expect(resolveLocale(null, ["zh-Hant-TW"])).toBe("en");
    expect(parseLocale("de-DE")).toBeNull();
  });

  it("translates fixed and parameterized copy", () => {
    expect(translate("gl", "signIn")).toBe("Iniciar sesión");
    expect(translate("gl", "tooManyAttemptsMinutesMany", { minutes: 3 })).toContain("3 minutos");
    expect(translate("en", "welcomeBack")).toBe("Welcome back");
    expect(translate("es", "welcomeBack")).toBe("Te damos la bienvenida");
    expect(translate("pt", "welcomeBack")).toBe("Boas-vindas de volta");
    expect(translate("ca", "welcomeBack")).toBe("Et donem la benvinguda");
    expect(translate("it", "welcomeBack")).toBe("Bentornato/a");
    expect(translate("fr", "welcomeBack")).toBe("Bon retour");
    expect(translate("eu", "welcomeBack")).toBe("Ongi etorri berriro");
    expect(translate("oc", "welcomeBack")).toBe("Benvengut/da de nau");
    expect(translate("zh", "welcomeBack")).toBe("欢迎回来");
  });

  it("keeps Portuguese entry copy complete", () => {
    expect(Object.keys(portuguese).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      expect(portuguese[key].trim(), key).not.toBe("");
      expect(portuguese[key].match(/\{\w+\}/g) ?? [], key)
        .toEqual(english[key].match(/\{\w+\}/g) ?? []);
    }
  });

  it("keeps Catalan entry copy complete", () => {
    expect(Object.keys(catalan).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      expect(catalan[key].trim(), key).not.toBe("");
      expect(catalan[key].match(/\{\w+\}/g) ?? [], key)
        .toEqual(english[key].match(/\{\w+\}/g) ?? []);
    }
  });

  it("keeps Italian entry copy complete", () => {
    expect(Object.keys(italian).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      expect(italian[key].trim(), key).not.toBe("");
      expect(italian[key].match(/\{\w+\}/g) ?? [], key)
        .toEqual(english[key].match(/\{\w+\}/g) ?? []);
    }
  });

  it("keeps French entry copy complete", () => {
    expect(Object.keys(french).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      expect(french[key].trim(), key).not.toBe("");
      expect(french[key].match(/\{\w+\}/g) ?? [], key)
        .toEqual(english[key].match(/\{\w+\}/g) ?? []);
    }
  });

  it("keeps Basque entry copy complete", () => {
    expect(Object.keys(basque).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      expect(basque[key].trim(), key).not.toBe("");
      expect(basque[key].match(/\{\w+\}/g) ?? [], key)
        .toEqual(english[key].match(/\{\w+\}/g) ?? []);
    }
  });

  it("keeps Aranese entry copy complete", () => {
    expect(Object.keys(aranese).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      expect(aranese[key].trim(), key).not.toBe("");
      expect(aranese[key].match(/\{\w+\}/g) ?? [], key)
        .toEqual(english[key].match(/\{\w+\}/g) ?? []);
    }
  });

  it("keeps Simplified Chinese entry copy complete", () => {
    expect(Object.keys(simplifiedChinese).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      expect(simplifiedChinese[key].trim(), key).not.toBe("");
      expect(simplifiedChinese[key].match(/\{\w+\}/g) ?? [], key)
        .toEqual(english[key].match(/\{\w+\}/g) ?? []);
    }
  });

  it("provides non-empty translations with matching interpolation variables", () => {
    expect(Object.keys(galician).sort()).toEqual(Object.keys(english).sort());
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      const source = english[key];
      const translation = translate("gl", key);
      expect(translation.trim(), key).not.toBe("");
      expect(translation.match(/\{\w+\}/g) ?? [], key).toEqual(source.match(/\{\w+\}/g) ?? []);
    }
  });

  it("substitutes every declared placeholder in all catalogues", () => {
    for (const key of Object.keys(english) as Array<keyof typeof english>) {
      const placeholders = english[key].match(/\{(\w+)\}/g) ?? [];
      const values = Object.fromEntries(placeholders.map((token) => [token.slice(1, -1), "example"]));
      for (const locale of availableLocales) {
        expect(translate(locale, key, values), `${locale}.${key}`).not.toMatch(/\{\w+\}/);
      }
    }
  });

  it("formats dates and numbers using the selected region", () => {
    const date = "2026-09-21T15:00:00Z";
    expect(formatLocalDateTime(date, "gl")).toBe(new Intl.DateTimeFormat("gl-ES", {
      dateStyle: "medium", timeStyle: "short",
    }).format(new Date(date)));
    expect(formatLocalNumber(1234.5, "gl")).toBe(new Intl.NumberFormat("gl-ES").format(1234.5));
    expect(formatLocalNumber(1234.5, "es")).toBe(new Intl.NumberFormat("es-ES").format(1234.5));
    expect(formatLocalNumber(1234.5, "pt")).toBe(new Intl.NumberFormat("pt-PT").format(1234.5));
    expect(formatLocalDateTime(date, "ca")).toBe(new Intl.DateTimeFormat("ca-ES", {
      dateStyle: "medium", timeStyle: "short",
    }).format(new Date(date)));
    expect(formatLocalNumber(1234.5, "ca")).toBe(new Intl.NumberFormat("ca-ES").format(1234.5));
    expect(formatLocalDateTime(date, "it")).toBe(new Intl.DateTimeFormat("it-IT", {
      dateStyle: "medium", timeStyle: "short",
    }).format(new Date(date)));
    expect(formatLocalNumber(1234.5, "it")).toBe(new Intl.NumberFormat("it-IT").format(1234.5));
    expect(formatLocalDateTime(date, "fr")).toBe(new Intl.DateTimeFormat("fr-FR", {
      dateStyle: "medium", timeStyle: "short",
    }).format(new Date(date)));
    expect(formatLocalNumber(1234.5, "fr")).toBe(new Intl.NumberFormat("fr-FR").format(1234.5));
    expect(formatLocalDateTime(date, "eu")).toBe(new Intl.DateTimeFormat("eu-ES", {
      dateStyle: "medium", timeStyle: "short",
    }).format(new Date(date)));
    expect(formatLocalNumber(1234.5, "eu")).toBe(new Intl.NumberFormat("eu-ES").format(1234.5));
    expect(formatLocalDateTime(date, "oc")).toBe(new Intl.DateTimeFormat("oc-ES", {
      dateStyle: "medium", timeStyle: "short",
    }).format(new Date(date)));
    expect(formatLocalNumber(1234.5, "oc")).toBe(new Intl.NumberFormat("oc-ES").format(1234.5));
    expect(formatLocalDateTime(date, "zh")).toBe(new Intl.DateTimeFormat("zh-CN", {
      dateStyle: "medium", timeStyle: "short",
    }).format(new Date(date)));
    expect(formatLocalNumber(1234.5, "zh")).toBe(new Intl.NumberFormat("zh-CN").format(1234.5));
  });
});
