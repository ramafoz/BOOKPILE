import type { MapBook } from "./types";

export interface ProportionalBookSegment {
  book: MapBook;
  offset: number;
  thickness: number;
  effectivePages: number;
}

const DEFAULT_EFFECTIVE_PAGES = 200;

function validPages(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

export function effectiveCataloguePageMean(books: MapBook[]): number {
  const known = books
    .map((book) => book.page_count)
    .filter(validPages);
  if (known.length === 0) return DEFAULT_EFFECTIVE_PAGES;
  return known.reduce((total, pages) => total + pages, 0) / known.length;
}

export function effectiveBookPages(book: MapBook, catalogueMean: number): number {
  if (validPages(book.page_count)) return book.page_count;
  return validPages(catalogueMean) ? catalogueMean : DEFAULT_EFFECTIVE_PAGES;
}

export function proportionalBookSegments(
  books: MapBook[],
  span: number,
  catalogueMean: number,
): ProportionalBookSegment[] {
  const ordered = [...books].sort(
    (first, second) => (first.position ?? 0) - (second.position ?? 0),
  );
  const weighted = ordered.map((book) => ({
    book,
    effectivePages: effectiveBookPages(book, catalogueMean),
  }));
  const totalPages = weighted.reduce(
    (total, item) => total + item.effectivePages,
    0,
  );
  let offset = 0;
  return weighted.map((item, index) => {
    const thickness = index === weighted.length - 1
      ? Math.max(0, span - offset)
      : span * item.effectivePages / Math.max(totalPages, 1);
    const segment = { ...item, offset, thickness };
    offset += thickness;
    return segment;
  });
}
