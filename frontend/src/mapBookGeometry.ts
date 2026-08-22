import type { MapBook, VisualRect } from "./types";

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

export interface OutsideBookGroupItem {
  book: MapBook;
  share: number;
  effectivePages: number;
}

export interface ReadingIconGrid {
  rows: number;
  columns: number;
  occupiedPercent: number;
}

export function readingIconGrid(
  count: number,
  surfaceAspectRatio = 1,
): ReadingIconGrid {
  const total = Math.max(0, Math.floor(count));
  if (total === 0) return { rows: 1, columns: 1, occupiedPercent: 0 };
  const desiredIconAspect = 1.35;
  let best = { rows: 1, columns: total, score: Number.POSITIVE_INFINITY };
  for (let rows = 1; rows <= total; rows += 1) {
    const columns = Math.ceil(total / rows);
    if (rows * columns > total + 1) continue;
    const cellAspect = Math.max(0.01, surfaceAspectRatio) * rows / columns;
    const emptyCells = rows * columns - total;
    const score = Math.abs(Math.log(cellAspect / desiredIconAspect)) +
      emptyCells * 0.08;
    if (score < best.score) best = { rows, columns, score };
  }
  return {
    rows: best.rows,
    columns: best.columns,
    occupiedPercent: Math.sqrt(
      best.rows * best.columns / (total + 1),
    ) * 100,
  };
}

export function proportionalOutsideBookGroups(
  books: MapBook[],
  catalogueMean: number,
  maximumItemsPerGroup = 10,
): OutsideBookGroupItem[][] {
  if (books.length === 0) return [];
  const groupSize = Math.max(1, Math.floor(maximumItemsPerGroup));
  const groups: Array<Array<{ book: MapBook; effectivePages: number }>> = [];
  for (let index = 0; index < books.length; index += groupSize) {
    groups.push(
      books.slice(index, index + groupSize).map((book) => ({
        book,
        effectivePages: effectiveBookPages(book, catalogueMean),
      })),
    );
  }
  const maximumPages = Math.max(
    1,
    (Number.isFinite(catalogueMean) && catalogueMean > 0
      ? catalogueMean
      : DEFAULT_EFFECTIVE_PAGES) * groupSize,
    ...groups.map((group) => group.reduce(
      (total, item) => total + item.effectivePages,
      0,
    )),
  );
  return groups.map((group) => group.map((item) => ({
    ...item,
    share: item.effectivePages / maximumPages,
  })));
}

export function containerRectWithoutAbsentBooks(
  rect: VisualRect,
  containerType: "ROW" | "PILE",
  rowAnchor: "LEFT" | "RIGHT",
  visibleBooks: MapBook[],
  absentBooks: MapBook[],
  catalogueMean: number,
): VisualRect {
  if (absentBooks.length === 0) return rect;
  const visiblePages = visibleBooks.reduce(
    (total, book) => total + effectiveBookPages(book, catalogueMean),
    0,
  );
  const absentPages = absentBooks.reduce(
    (total, book) => total + effectiveBookPages(book, catalogueMean),
    0,
  );
  const ratio = visiblePages / Math.max(1, visiblePages + absentPages);
  if (containerType === "ROW") {
    const width = rect.width * ratio;
    return {
      ...rect,
      x: rowAnchor === "RIGHT" ? rect.x + rect.width - width : rect.x,
      width,
    };
  }
  const height = rect.height * ratio;
  return {
    ...rect,
    y: rect.y + rect.height - height,
    height,
  };
}
