import type {
  PhysicalBook,
  PhysicalLibrary,
  VisualContainerLayout,
} from "./serverApi";

export interface WorldRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface MapShelfRect extends WorldRect {
  shelfId: string;
  bookcaseId: string;
}

export interface MapContainerRect extends WorldRect {
  containerId: string;
  shelfId: string;
  type: "ROW" | "PILE";
  layer: "BACKGROUND" | "FOREGROUND";
  layout: VisualContainerLayout;
  shelfWorldWidth: number;
  shelfWorldHeight: number;
  shelfUsableWidthMm: number | null;
  shelfUsableHeightMm: number | null;
}

export interface BookSegment extends WorldRect {
  book: PhysicalBook;
}

export interface RearrangementSlot extends WorldRect {
  position: number;
  book: PhysicalBook | null;
  isEndTarget: boolean;
}

export interface BookVisualDefaults {
  thicknessMm: number;
  heightMm: number;
  thicknessPerPage: number | null;
}

function median(values: number[], fallback: number): number {
  if (!values.length) return fallback;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

export function catalogueBookVisualDefaults(books: PhysicalBook[]): BookVisualDefaults {
  const measured = books.map((book) => book.thickness_mm).filter((value): value is number => Boolean(value && value > 0));
  const heights = books.map((book) => book.height_mm).filter((value): value is number => Boolean(value && value > 0));
  const ratios = books
    .filter((book) => Boolean(book.thickness_mm && book.page_count && book.thickness_mm > 0 && book.page_count > 0))
    .map((book) => book.thickness_mm! / book.page_count!);
  return { thicknessMm: median(measured, 20), heightMm: median(heights, 220), thicknessPerPage: ratios.length ? median(ratios, 0) : null };
}

function resolvedThickness(book: PhysicalBook, defaults: BookVisualDefaults): number {
  if (book.thickness_mm && book.thickness_mm > 0) return book.thickness_mm;
  if (book.page_count && book.page_count > 0 && defaults.thicknessPerPage) return book.page_count * defaults.thicknessPerPage;
  return defaults.thicknessMm;
}

function resolvedHeight(book: PhysicalBook, defaults: BookVisualDefaults): number {
  return book.height_mm && book.height_mm > 0 ? book.height_mm : defaults.heightMm;
}

export function cataloguePageMean(books: PhysicalBook[]): number {
  const known = books.map((book) => book.page_count)
    .filter((pages): pages is number => typeof pages === "number" && pages > 0);
  return known.length
    ? known.reduce((total, pages) => total + pages, 0) / known.length
    : 200;
}

export function physicalMapGeometry(data: PhysicalLibrary): {
  bookcases: Array<WorldRect & { bookcaseId: string }>;
  shelves: MapShelfRect[];
  containers: MapContainerRect[];
} {
  const bookcaseLayouts = new Map(data.layout.bookcases.map((item) => [item.bookcase_id, item]));
  const shelfLayouts = new Map(data.layout.shelves.map((item) => [item.shelf_id, item]));
  const containerLayouts = new Map(data.layout.containers.map((item) => [item.container_id, item]));
  const bookcases: Array<WorldRect & { bookcaseId: string }> = [];
  const shelves: MapShelfRect[] = [];
  const containers: MapContainerRect[] = [];

  data.bookcases.forEach((bookcase) => {
    const layout = bookcaseLayouts.get(bookcase.id);
    if (!layout) return;
    // Persisted floor coordinates use a mathematical Y axis: positive is up.
    // SVG uses positive Y down, so both the baseline and the height are inverted.
    const top = -layout.floor_y_mm - layout.height_mm;
    bookcases.push({ bookcaseId: bookcase.id, x: layout.x_mm, y: top, width: layout.width_mm, height: layout.height_mm });
    const insetX = layout.width_mm * 0.025;
    const insetY = layout.height_mm * 0.025;
    const inner = {
      x: layout.x_mm + insetX,
      y: top + insetY,
      width: layout.width_mm - insetX * 2,
      height: layout.height_mm - insetY * 2,
    };
    const totalWeight = bookcase.shelves.reduce(
      (total, shelf) => total + (shelfLayouts.get(shelf.id)?.height_weight ?? 1),
      0,
    ) || 1;
    let shelfY = inner.y;
    bookcase.shelves.forEach((shelf) => {
      const height = inner.height * (shelfLayouts.get(shelf.id)?.height_weight ?? 1) / totalWeight;
      const shelfRect: MapShelfRect = {
        shelfId: shelf.id,
        bookcaseId: bookcase.id,
        x: inner.x,
        y: shelfY,
        width: inner.width,
        height,
      };
      shelves.push(shelfRect);
      shelf.containers.forEach((container) => {
        const containerLayout = containerLayouts.get(container.id);
        if (!containerLayout) return;
        containers.push({
          containerId: container.id,
          shelfId: shelf.id,
          type: container.container_type,
          layer: container.layer,
          layout: containerLayout,
          shelfWorldWidth: shelfRect.width,
          shelfWorldHeight: shelfRect.height,
          shelfUsableWidthMm: shelf.usable_width_mm,
          shelfUsableHeightMm: shelf.usable_height_mm,
          x: shelfRect.x + shelfRect.width * containerLayout.x / 100,
          y: shelfRect.y + shelfRect.height * containerLayout.y / 100,
          width: shelfRect.width * containerLayout.width / 100,
          height: shelfRect.height * containerLayout.height / 100,
        });
      });
      shelfY += height;
    });
  });
  return { bookcases, shelves, containers };
}

export function proportionalBookSegments(
  rect: MapContainerRect,
  books: PhysicalBook[],
  defaults: BookVisualDefaults = catalogueBookVisualDefaults(books),
  physical = false,
): BookSegment[] {
  const ordered = [...books].sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
  const pages = ordered.map((book) => resolvedThickness(book, defaults));
  const total = pages.reduce((sum, value) => sum + value, 0) || 1;
  if (!physical) {
    const span = rect.type === "ROW" ? rect.width : rect.height;
    let offset = 0;
    return ordered.map((book, index) => {
      const thickness = index === ordered.length - 1 ? span - offset : span * pages[index] / total;
      const segment = rect.type === "ROW"
        ? { x: rect.x + offset, y: rect.y, width: thickness, height: rect.height }
        : { x: rect.x, y: rect.y + offset, width: rect.width, height: thickness };
      offset += thickness;
      return { ...segment, book };
    });
  }
  const physicalThicknessScale = rect.type === "ROW"
    ? (rect.shelfUsableWidthMm ? rect.shelfWorldWidth / rect.shelfUsableWidthMm : null)
    : (rect.shelfUsableHeightMm ? rect.shelfWorldHeight / rect.shelfUsableHeightMm : null);
  const thicknesses = pages.map((value) => physicalThicknessScale ? value * physicalThicknessScale : (rect.type === "ROW" ? rect.width : rect.height) * value / total);
  const occupiedSpan = thicknesses.reduce((sum, value) => sum + value, 0);
  let offset = rect.type === "ROW" && rect.layout.row_anchor === "RIGHT"
    ? rect.width - occupiedSpan
    : rect.type === "PILE" ? rect.height - occupiedSpan : 0;
  return ordered.map((book, index) => {
    const thickness = thicknesses[index];
    const physicalLength = rect.shelfUsableHeightMm && rect.type === "ROW"
      ? resolvedHeight(book, defaults) * rect.shelfWorldHeight / rect.shelfUsableHeightMm
      : rect.shelfUsableWidthMm && rect.type === "PILE"
        ? resolvedHeight(book, defaults) * rect.shelfWorldWidth / rect.shelfUsableWidthMm
        : rect.type === "ROW" ? rect.height : rect.width;
    const pileX = rect.layout.pile_alignment === "LEFT"
      ? rect.x
      : rect.layout.pile_alignment === "CENTER"
        ? rect.x + (rect.width - physicalLength) / 2
        : rect.x + rect.width - physicalLength;
    const segment = rect.type === "ROW"
      ? { x: rect.x + offset, y: rect.y + rect.height - physicalLength, width: thickness, height: physicalLength }
      : { x: pileX, y: rect.y + offset, width: physicalLength, height: thickness };
    offset += thickness;
    return { ...segment, book };
  });
}

export function proportionalRearrangementSlots(
  rect: MapContainerRect,
  books: PhysicalBook[],
  gapPositions: number[],
  movingBook: PhysicalBook | null,
  defaults: BookVisualDefaults = catalogueBookVisualDefaults(books),
): RearrangementSlot[] {
  const byPosition = new Map(
    books
      .filter((book) => book.position !== null)
      .map((book) => [book.position as number, book]),
  );
  const gaps = new Set(gapPositions);
  const lastPosition = Math.max(0, ...byPosition.keys(), ...gaps);
  const movingPages = movingBook ? resolvedThickness(movingBook, defaults) : defaults.thicknessMm;
  const items = Array.from({ length: lastPosition }, (_, index) => {
    const position = index + 1;
    const item = byPosition.get(position) ?? null;
    const pages = item ? resolvedThickness(item, defaults) : movingPages;
    return { position, book: item, pages };
  });
  const totalPages = items.reduce((sum, item) => sum + item.pages, 0) || movingPages;
  const span = rect.type === "ROW" ? rect.width : rect.height;
  let offset = 0;
  const slots = items.map((item, index): RearrangementSlot => {
    const thickness = index === items.length - 1
      ? span - offset
      : span * item.pages / totalPages;
    const geometry = rect.type === "ROW"
      ? { x: rect.x + offset, y: rect.y, width: thickness, height: rect.height }
      : { x: rect.x, y: rect.y + offset, width: rect.width, height: thickness };
    offset += thickness;
    return { ...geometry, position: item.position, book: item.book, isEndTarget: false };
  });
  const endThickness = items.length
    ? Math.max(span * movingPages / totalPages, span * 0.035)
    : span;
  slots.push({
    ...(rect.type === "ROW"
      ? { x: rect.x + rect.width, y: rect.y, width: endThickness, height: rect.height }
      : { x: rect.x, y: rect.y + rect.height, width: rect.width, height: endThickness }),
    position: lastPosition + 1,
    book: null,
    isEndTarget: true,
  });
  return slots;
}

export function boundsForRects(rects: WorldRect[]): WorldRect {
  if (!rects.length) return { x: 0, y: 0, width: 100, height: 100 };
  const minX = Math.min(...rects.map((rect) => rect.x));
  const minY = Math.min(...rects.map((rect) => rect.y));
  const maxX = Math.max(...rects.map((rect) => rect.x + rect.width));
  const maxY = Math.max(...rects.map((rect) => rect.y + rect.height));
  return { x: minX, y: minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) };
}
