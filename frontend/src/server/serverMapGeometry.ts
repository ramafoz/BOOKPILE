import type {
  PhysicalBook,
  PhysicalLibrary,
  VisualContainerLayout,
  VisualLayout,
  VisualShelfLayout,
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

const MIN_STRUCTURE_MM = 5;
const SHELF_FALLBACK_FRACTION = .14;

function compressShelfSpans(values: number[], fallbackIndexes: number[], available: number): number[] {
  if (values.reduce((sum, value) => sum + value, 0) <= available + 1e-6) return values;
  const fallback = new Set(fallbackIndexes);
  const fixed = values.reduce((sum, value, index) => sum + (fallback.has(index) ? 0 : value), 0);
  const remaining = available - fixed;
  if (!fallbackIndexes.length || remaining < MIN_STRUCTURE_MM * fallbackIndexes.length - 1e-6) throw new Error("Shelves do not fit");
  const current = fallbackIndexes.reduce((sum, index) => sum + values[index], 0);
  const result = [...values];
  fallbackIndexes.forEach((index) => { result[index] = Math.max(MIN_STRUCTURE_MM, values[index] * remaining / current); });
  if (result.reduce((sum, value) => sum + value, 0) > available + 1e-6) throw new Error("Shelves do not fit");
  return result;
}

/** Mirror the server's shelf projection for a live, non-persistent layout preview. */
export function previewPhysicalShelfLayout(data: PhysicalLibrary, layout: VisualLayout): VisualLayout {
  if (layout.geometry_mode !== "PHYSICAL") return layout;
  const bookcaseLayouts = new Map(layout.bookcases.map((item) => [item.bookcase_id, item]));
  const shelfLayouts = new Map(layout.shelves.map((item) => [item.shelf_id, item]));
  const projected = new Map<string, VisualShelfLayout>();
  try {
    data.bookcases.forEach((bookcase) => {
      const furniture = bookcaseLayouts.get(bookcase.id);
      if (!furniture) return;
      const shelves = [...bookcase.shelves].sort((a, b) => a.shelf_number - b.shelf_number);
      if (!shelves.length) return;
      const current = shelves.map((shelf) => shelfLayouts.get(shelf.id)).filter((item): item is VisualShelfLayout => Boolean(item));
      if (current.length !== shelves.length) throw new Error("Incomplete shelf layout");
      const vertical = furniture.shelf_direction === "TOP_TO_BOTTOM" || furniture.shelf_direction === "BOTTOM_TO_TOP";
      const separators = current.slice(0, -1).map((item) => furniture.homogeneous_structure ? furniture.separator_thickness_mm : (item.separator_after_mm ?? furniture.separator_thickness_mm));
      if (separators.some((value) => value < MIN_STRUCTURE_MM)) throw new Error("Invalid separator");
      if (vertical) {
        const fallbackIndexes: number[] = [];
        let spans = shelves.map((shelf, index) => {
          if (shelf.usable_height_mm && shelf.usable_height_mm > 0) return shelf.usable_height_mm;
          fallbackIndexes.push(index);
          return furniture.height_mm * SHELF_FALLBACK_FRACTION;
        });
        const available = furniture.height_mm - furniture.top_closure_mm - furniture.bottom_closure_mm - separators.reduce((sum, value) => sum + value, 0);
        spans = compressShelfSpans(spans, fallbackIndexes, available);
        const residual = Math.max(0, available - spans.reduce((sum, value) => sum + value, 0));
        let cursor = furniture.shelf_direction === "TOP_TO_BOTTOM"
          ? furniture.height_mm - furniture.top_closure_mm
          : furniture.bottom_closure_mm + residual;
        current.forEach((item, index) => {
          const shelf = shelves[index];
          const physicalTop = furniture.shelf_direction === "TOP_TO_BOTTOM" ? index === 0 : index === current.length - 1;
          const left = item.open_top && physicalTop ? 0 : (furniture.homogeneous_structure ? furniture.frame_left_mm : item.left_frame_mm);
          const right = item.open_top && physicalTop ? 0 : (furniture.homogeneous_structure ? furniture.frame_right_mm : item.right_frame_mm);
          const width = shelf.usable_width_mm && shelf.usable_width_mm > 0 ? shelf.usable_width_mm : furniture.width_mm - left - right;
          const x = item.open_top && physicalTop ? 0 : item.alignment === "LEFT" ? item.offset_mm : item.alignment === "RIGHT" ? furniture.width_mm - width + item.offset_mm : (furniture.width_mm - width) / 2 + item.offset_mm;
          const floor = furniture.shelf_direction === "TOP_TO_BOTTOM" ? cursor - spans[index] : cursor;
          projected.set(item.shelf_id, { ...item, x_mm: x, floor_y_mm: floor, width_mm: width, height_mm: spans[index], width_source: shelf.usable_width_mm ? "ENTERED" : "FALLBACK", height_source: shelf.usable_height_mm ? "ENTERED" : "FALLBACK" });
          cursor = furniture.shelf_direction === "TOP_TO_BOTTOM" ? floor - (separators[index] ?? 0) : floor + spans[index] + (separators[index] ?? 0);
        });
      } else {
        const fallbackIndexes: number[] = [];
        let spans = shelves.map((shelf, index) => {
          if (shelf.usable_width_mm && shelf.usable_width_mm > 0) return shelf.usable_width_mm;
          fallbackIndexes.push(index);
          return furniture.width_mm * SHELF_FALLBACK_FRACTION;
        });
        const baseAvailable = furniture.width_mm - furniture.frame_left_mm - furniture.frame_right_mm - separators.reduce((sum, value) => sum + value, 0);
        spans = compressShelfSpans(spans, fallbackIndexes, baseAvailable);
        const residual = Math.max(0, baseAvailable - spans.reduce((sum, value) => sum + value, 0));
        const effectiveSeparators = separators.length ? separators.map((value) => value + residual / separators.length) : separators;
        let left = furniture.frame_left_mm;
        let right = furniture.frame_right_mm;
        if (!effectiveSeparators.length) {
          if (left > 0 && right > 0) { left += residual / 2; right += residual / 2; }
          else if (left > 0) left += residual;
          else if (right > 0) right += residual;
          else if (current.length === 1 && fallbackIndexes.length) spans[0] = furniture.width_mm;
        }
        let cursor = furniture.shelf_direction === "LEFT_TO_RIGHT" ? left : furniture.width_mm - right;
        current.forEach((item, index) => {
          const shelf = shelves[index];
          const top = furniture.homogeneous_structure ? furniture.top_closure_mm : item.top_closure_mm;
          const bottom = furniture.homogeneous_structure ? furniture.bottom_closure_mm : item.bottom_board_mm;
          const height = shelf.usable_height_mm && shelf.usable_height_mm > 0 ? shelf.usable_height_mm : furniture.height_mm - top - bottom;
          const x = furniture.shelf_direction === "LEFT_TO_RIGHT" ? cursor : cursor - spans[index];
          projected.set(item.shelf_id, { ...item, x_mm: x, floor_y_mm: bottom, width_mm: spans[index], height_mm: height, width_source: shelf.usable_width_mm ? "ENTERED" : "FALLBACK", height_source: shelf.usable_height_mm ? "ENTERED" : "FALLBACK" });
          cursor = furniture.shelf_direction === "LEFT_TO_RIGHT" ? x + spans[index] + (effectiveSeparators[index] ?? 0) : x - (effectiveSeparators[index] ?? 0);
        });
      }
    });
  } catch {
    return layout;
  }
  return { ...layout, shelves: layout.shelves.map((item) => projected.get(item.shelf_id) ?? item) };
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
    const explicitShelvesAvailable = bookcase.shelves.every((shelf) => {
      const item = shelfLayouts.get(shelf.id);
      return item && [item.x_mm, item.floor_y_mm, item.width_mm, item.height_mm]
        .every((value) => Number.isFinite(value));
    });
    const insetX = layout.width_mm * 0.025;
    const insetY = layout.height_mm * 0.025;
    const legacyInner = {
      x: layout.x_mm + insetX,
      y: top + insetY,
      width: layout.width_mm - insetX * 2,
      height: layout.height_mm - insetY * 2,
    };
    const legacyTotalWeight = bookcase.shelves.reduce(
      (total, shelf) => total + (shelfLayouts.get(shelf.id)?.height_weight ?? 1),
      0,
    ) || 1;
    let legacyShelfY = legacyInner.y;
    bookcase.shelves.forEach((shelf) => {
      const shelfLayout = shelfLayouts.get(shelf.id);
      if (!shelfLayout) return;
      const legacyHeight = legacyInner.height * (shelfLayout.height_weight ?? 1) / legacyTotalWeight;
      const shelfRect: MapShelfRect = explicitShelvesAvailable
        ? {
            shelfId: shelf.id,
            bookcaseId: bookcase.id,
            x: layout.x_mm + shelfLayout.x_mm,
            y: -layout.floor_y_mm - shelfLayout.floor_y_mm - shelfLayout.height_mm,
            width: shelfLayout.width_mm,
            height: shelfLayout.height_mm,
          }
        : {
            shelfId: shelf.id,
            bookcaseId: bookcase.id,
            x: legacyInner.x,
            y: legacyShelfY,
            width: legacyInner.width,
            height: legacyHeight,
          };
      legacyShelfY += legacyHeight;
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
