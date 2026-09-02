import type { CatalogueQuery, LibraryMemberSummary, ReadingPerspective } from "./serverApi";

export type ViewingWorkspace = "CATALOGUE" | "MAP" | "LAYOUT";

const FILTER_KEYS: Array<keyof CatalogueQuery> = [
  "search", "isbn", "language", "original_language", "genre", "publisher",
  "series_name", "translation_status", "fiction_category", "binding",
  "publication_type", "series_state", "author_structure", "page_min",
  "page_max", "year_min", "year_max",
];

export function hasActiveCatalogueFilters(query: CatalogueQuery): boolean {
  return FILTER_KEYS.some((key) => {
    const value = query[key];
    if (Array.isArray(value)) return value.length > 0;
    if (value === undefined || value === null || value === "") return false;
    return value !== "ANY";
  });
}

export function selectedPerspective(
  perspectives: ReadingPerspective[],
): ReadingPerspective | null {
  return perspectives.find((item) => item.selected) ?? perspectives[0] ?? null;
}

export function workspacePerspectiveLabel(
  workspace: ViewingWorkspace,
  signedInUserId: string,
  perspectives: ReadingPerspective[],
): string {
  const view = workspace === "MAP" ? "Map" : "Catalogue";
  const perspective = selectedPerspective(perspectives);
  if (!perspective || perspective.user_id === signedInUserId) return `${view} — self`;
  return `${view} — ${perspective.username}`;
}

export function catalogueTitle(
  signedInUserId: string,
  perspectives: ReadingPerspective[],
): string {
  const perspective = selectedPerspective(perspectives);
  return !perspective || perspective.user_id === signedInUserId
    ? "Your books"
    : `${perspective.username}'s books`;
}

export function cataloguePrivacyLabel(members: LibraryMemberSummary[]): string {
  return members.length > 1 ? "Shared catalogue" : "Private catalogue";
}
