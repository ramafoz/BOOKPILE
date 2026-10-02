import { describe, expect, it } from "vitest";
import { authenticatedCopy, en as authenticatedEn, es as authenticatedEs } from "./authenticatedCopy";
import { en as catalogueEn, es as catalogueEs } from "./catalogueCopy";
import { accountInvitationMessage, libraryInvitationMessage } from "./invitationCopy";
import { en as loanEn, es as loanEs } from "./loanCopy";
import { en as libraryAdminEn, es as libraryAdminEs } from "./libraryAdminCopy";
import { en as mapEn, es as mapEs } from "./mapCopy";
import { en as physicalEn, es as physicalEs } from "./physicalCopy";
import { en as profileEn, es as profileEs } from "./profileCopy";
import { en as readingEn, es as readingEs } from "./readingCopy";
import { en as statisticsEn, es as statisticsEs } from "./statisticsCopy";
import { english } from "./locales/en";
import { spanish } from "./locales/es";
import { translate } from "./locale";
import { friendlyError } from "./friendlyError";
import { ServerApiError } from "./serverApi";

function placeholders(value: string): string[] {
  return (value.match(/\{\w+\}/g) ?? []).sort();
}

function expectComplete(
  source: Record<string, string>,
  translation: Record<string, string>,
): void {
  expect(Object.keys(translation).sort()).toEqual(Object.keys(source).sort());
  for (const key of Object.keys(source)) {
    expect(translation[key].trim(), key).not.toBe("");
    expect(placeholders(translation[key]), key).toEqual(placeholders(source[key]));
  }
}

describe("Spanish copy", () => {
  it("keeps every completed catalogue structurally equivalent to English", () => {
    expectComplete(english, spanish);
    expectComplete(authenticatedEn, authenticatedEs);
    expectComplete(catalogueEn, catalogueEs);
    expectComplete(libraryAdminEn, libraryAdminEs);
    expectComplete(loanEn, loanEs);
    expectComplete(mapEn, mapEs);
    expectComplete(physicalEn, physicalEs);
    expectComplete(profileEn, profileEs);
    expectComplete(readingEn, readingEs);
    expectComplete(statisticsEn, statisticsEs);
  });

  it("distinguishes account, viewer and co-owner invitations", () => {
    const url = "https://bookpile.gal/login?invite=private-token";
    expect(accountInvitationMessage("es", url)).toContain("crear una cuenta");
    expect(libraryInvitationMessage("es", url, "Casa", "VIEWER", "CATALOG_ONLY"))
      .toContain("ver el catálogo");
    expect(libraryInvitationMessage("es", url, "Casa", "VIEWER", "CATALOG_AND_MAP"))
      .toContain("mapa físico");
    expect(libraryInvitationMessage("es", url, "Casa", "OWNER", null))
      .toContain("copropietario/a");
  });

  it("localizes the current perspective and operational failures", () => {
    const t = (key: Parameters<typeof translate>[1], values?: Record<string, string | number>) =>
      translate("es", key, values);
    expect(authenticatedCopy("es")("self")).toBe("yo");
    expect(friendlyError(new ServerApiError("raw", 429, 120), t)).toContain("2 minutos");
    expect(friendlyError(new TypeError("network"), t)).toBe(
      "BOOKPILE no ha podido conectar con el servidor. Inténtalo de nuevo.",
    );
  });
});
