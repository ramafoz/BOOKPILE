import { describe, expect, it } from "vitest";
import type { PhysicalLibrary } from "./serverApi";
import { cataloguePageMean, physicalMapGeometry, proportionalBookSegments } from "./serverMapGeometry";

const data = {
  library_id: "library",
  role: "OWNER",
  can_edit: true,
  bookcases: [{ id: "case", name: "Case", description: null, height_mm: null, width_mm: null, depth_mm: null, book_count: 2, created_at: "", updated_at: "", shelves: [{ id: "shelf", bookcase_id: "case", shelf_number: 1, usable_height_mm: null, usable_width_mm: null, usable_depth_mm: null, book_count: 2, created_at: "", updated_at: "", containers: [{ id: "row", shelf_id: "shelf", container_type: "ROW", layer: "BACKGROUND", container_number: 1, book_count: 2, created_at: "", updated_at: "" }] }] }],
  books: [
    { id: "thin", title: "Thin", author: "A", page_count: 100, container_id: "row", position: 1 },
    { id: "thick", title: "Thick", author: "B", page_count: 300, container_id: "row", position: 2 },
  ],
  layout: {
    revision: "revision",
    bookcases: [{ bookcase_id: "case", x: 10, y: 20, width: 40, height: 60 }],
    shelves: [{ shelf_id: "shelf", height_weight: 1 }],
    containers: [{ container_id: "row", x: 0, y: 0, width: 100, height: 100, row_anchor: "LEFT", pile_support_kind: null, pile_support_container_id: null }],
    outside_areas: [{ area_kind: "READING", x: 60, y: 70, width: 10, height: 20 }, { area_kind: "LOANED", x: 75, y: 70, width: 10, height: 20 }],
  },
} satisfies PhysicalLibrary;

describe("Server Library Map geometry", () => {
  it("projects shelf-local geometry into world coordinates", () => {
    const geometry = physicalMapGeometry(data);
    expect(geometry.bookcases[0]).toMatchObject({ x: 10, y: 20, width: 40, height: 60 });
    expect(geometry.containers[0].width).toBeCloseTo(38);
    expect(geometry.containers[0].height).toBeCloseTo(57);
  });

  it("uses strict page proportionality with the catalogue mean fallback", () => {
    const geometry = physicalMapGeometry(data);
    const mean = cataloguePageMean(data.books);
    const segments = proportionalBookSegments(geometry.containers[0], data.books, mean);
    expect(mean).toBe(200);
    expect(segments[1].width).toBeCloseTo(segments[0].width * 3);
  });
});
