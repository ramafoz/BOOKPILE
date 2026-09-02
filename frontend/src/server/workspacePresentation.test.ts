import { describe, expect, it } from "vitest";
import {
  cataloguePrivacyLabel,
  catalogueTitle,
  hasActiveCatalogueFilters,
  workspacePerspectiveLabel,
} from "./workspacePresentation";

const self = [{ user_id: "self", username: "ramafoz1", selected: true, writable: true }];
const other = [{ user_id: "owner", username: "ramafoz", selected: true, writable: false }];

describe("compact Server workspace presentation", () => {
  it("distinguishes filtering from sorting and pagination", () => {
    expect(hasActiveCatalogueFilters({ sort_by: "title", sort_order: "desc", offset: 50 })).toBe(false);
    expect(hasActiveCatalogueFilters({ search: "Dune" })).toBe(true);
    expect(hasActiveCatalogueFilters({ language: ["Galician"] })).toBe(true);
    expect(hasActiveCatalogueFilters({ series_state: "ANY" })).toBe(false);
  });

  it("labels the active workspace and reading perspective", () => {
    expect(workspacePerspectiveLabel("CATALOGUE", "self", self)).toBe("Catalogue — self");
    expect(workspacePerspectiveLabel("MAP", "viewer", other)).toBe("Map — ramafoz");
    expect(catalogueTitle("self", self)).toBe("Your books");
    expect(catalogueTitle("viewer", other)).toBe("ramafoz's books");
  });

  it("labels catalogue privacy from the safe member projection", () => {
    expect(cataloguePrivacyLabel([{ user_id: "1", username: "one", role: "OWNER", viewer_scope: null }])).toBe("Private catalogue");
    expect(cataloguePrivacyLabel([
      { user_id: "1", username: "one", role: "OWNER", viewer_scope: null },
      { user_id: "2", username: "two", role: "VIEWER", viewer_scope: "CATALOG_ONLY" },
    ])).toBe("Shared catalogue");
  });
});
