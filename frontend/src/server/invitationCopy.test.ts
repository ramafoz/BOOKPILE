import { describe, expect, it } from "vitest";
import { accountInvitationMessage, libraryInvitationMessage } from "./invitationCopy";

const url = "https://bookpile.gal/login?library-invite=private-token";

describe("localized invitation copy", () => {
  it("includes the account URL and expiry without implying an existing account", () => {
    expect(accountInvitationMessage("en", url)).toContain(url);
    expect(accountInvitationMessage("en", url)).toContain("create an account");
    expect(accountInvitationMessage("gl", url)).toContain("crear unha conta");
  });

  it("distinguishes viewer scopes and equal co-Owner authority", () => {
    expect(libraryInvitationMessage("en", url, "Home", "VIEWER", "CATALOG_ONLY"))
      .toContain("view the catalogue of");
    expect(libraryInvitationMessage("gl", url, "Casa", "VIEWER", "CATALOG_AND_MAP"))
      .toContain("catálogo e o mapa físico");
    const owner = libraryInvitationMessage("en", url, "Home", "OWNER", null);
    expect(owner).toContain("equal co-Owner");
    expect(owner).toContain("same administrative authority");
  });
});
