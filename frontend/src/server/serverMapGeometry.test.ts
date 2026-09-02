import { describe, expect, it } from "vitest";
import type { PhysicalLibrary } from "./serverApi";
import { cataloguePageMean, physicalMapGeometry, proportionalBookSegments, proportionalRearrangementSlots } from "./serverMapGeometry";

const data = {
  library_id: "library",
  role: "OWNER",
  can_edit: true,
  bookcases: [{ id: "case", name: "Case", description: null, height_mm: null, width_mm: null, depth_mm: null, book_count: 2, created_at: "", updated_at: "", shelves: [{ id: "shelf", bookcase_id: "case", shelf_number: 1, usable_height_mm: null, usable_width_mm: null, usable_depth_mm: null, book_count: 2, created_at: "", updated_at: "", containers: [{ id: "row", shelf_id: "shelf", container_type: "ROW", layer: "BACKGROUND", container_number: 1, book_count: 2, created_at: "", updated_at: "" }] }] }],
  books: [
    { id: "thin", title: "Thin", author: "A", page_count: 100, height_mm: 200, width_mm: 140, thickness_mm: 10, container_id: "row", position: 1 },
    { id: "thick", title: "Thick", author: "B", page_count: 300, height_mm: 240, width_mm: 160, thickness_mm: 30, container_id: "row", position: 2 },
  ],
  layout: {
    revision: "revision",
    geometry_mode: "MANUAL",
    coordinate_system_version: 2,
    bookcases: [{ bookcase_id: "case", x_mm: 200, floor_y_mm: 1600, width_mm: 800, height_mm: 1200 }],
    shelves: [{ shelf_id: "shelf", height_weight: 1 }],
    containers: [{ container_id: "row", x: 0, y: 0, width: 100, height: 100, row_anchor: "LEFT", support_kind: "SHELF", support_container_id: null, pile_alignment: "RIGHT" }],
    outside_areas: [{ area_kind: "READING", x_mm: 1200, y_mm: 1400, width_mm: 200, height_mm: 400 }, { area_kind: "LOANED", x_mm: 1500, y_mm: 1400, width_mm: 200, height_mm: 400 }],
  },
} satisfies PhysicalLibrary;

describe("Server Library Map geometry", () => {
  it("projects shelf-local geometry into world coordinates", () => {
    const geometry = physicalMapGeometry(data);
    expect(geometry.bookcases[0]).toMatchObject({ x: 200, y: 400, width: 800, height: 1200 });
    expect(geometry.containers[0].width).toBeCloseTo(760);
    expect(geometry.containers[0].height).toBeCloseTo(1140);
  });

  it("uses strict page proportionality with the catalogue mean fallback", () => {
    const geometry = physicalMapGeometry(data);
    const mean = cataloguePageMean(data.books);
    const segments = proportionalBookSegments(geometry.containers[0], data.books);
    expect(mean).toBe(200);
    expect(segments[1].width).toBeCloseTo(segments[0].width * 3);
    expect(segments.reduce((sum, segment) => sum + segment.width, 0)).toBeCloseTo(geometry.containers[0].width);
  });

  it("uses real millimetres only when physical geometry is active", () => {
    const physical = {
      ...data,
      bookcases: [{
        ...data.bookcases[0],
        shelves: [{ ...data.bookcases[0].shelves[0], usable_width_mm: 760 }],
      }],
      layout: { ...data.layout, geometry_mode: "PHYSICAL" as const },
    };
    const geometry = physicalMapGeometry(physical);
    const segments = proportionalBookSegments(geometry.containers[0], physical.books, undefined, true);
    expect(segments[0].width).toBeCloseTo(10);
    expect(segments[1].width).toBeCloseTo(30);
  });

  it("keeps internal gaps visible and adds a selectable end target", () => {
    const geometry = physicalMapGeometry(data);
    const books = [{ ...data.books[1], position: 2 }];
    const slots = proportionalRearrangementSlots(geometry.containers[0], books, [1], data.books[0]);
    expect(slots.map((slot) => [slot.position, slot.book?.id ?? null, slot.isEndTarget])).toEqual([
      [1, null, false],
      [2, "thick", false],
      [3, null, true],
    ]);
    expect(slots[0].width).toBeGreaterThan(0);
    expect(slots[2].x).toBeCloseTo(geometry.containers[0].x + geometry.containers[0].width);
  });
});
