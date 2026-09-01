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
}

export interface BookSegment extends WorldRect {
  book: PhysicalBook;
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
    bookcases.push({ bookcaseId: bookcase.id, ...layout });
    const insetX = layout.width * 0.025;
    const insetY = layout.height * 0.025;
    const inner = {
      x: layout.x + insetX,
      y: layout.y + insetY,
      width: layout.width - insetX * 2,
      height: layout.height - insetY * 2,
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
  catalogueMean: number,
): BookSegment[] {
  const ordered = [...books].sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
  const pages = ordered.map((book) => book.page_count && book.page_count > 0 ? book.page_count : catalogueMean);
  const total = pages.reduce((sum, value) => sum + value, 0) || 1;
  let offset = 0;
  return ordered.map((book, index) => {
    const span = rect.type === "ROW" ? rect.width : rect.height;
    const thickness = index === ordered.length - 1 ? span - offset : span * pages[index] / total;
    const segment = rect.type === "ROW"
      ? { x: rect.x + offset, y: rect.y, width: thickness, height: rect.height }
      : { x: rect.x, y: rect.y + offset, width: rect.width, height: thickness };
    offset += thickness;
    return { ...segment, book };
  });
}

export function boundsForRects(rects: WorldRect[]): WorldRect {
  if (!rects.length) return { x: 0, y: 0, width: 100, height: 100 };
  const minX = Math.min(...rects.map((rect) => rect.x));
  const minY = Math.min(...rects.map((rect) => rect.y));
  const maxX = Math.max(...rects.map((rect) => rect.x + rect.width));
  const maxY = Math.max(...rects.map((rect) => rect.y + rect.height));
  return { x: minX, y: minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) };
}
