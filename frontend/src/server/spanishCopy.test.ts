import { describe, expect, it } from "vitest";
import { en as authenticatedEn, es as authenticatedEs } from "./authenticatedCopy";
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
});
