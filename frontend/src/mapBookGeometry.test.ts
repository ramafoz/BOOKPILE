import { describe, expect, it } from "vitest";
import type { MapBook } from "./types";
import {
  containerRectWithoutAbsentBooks,
  proportionalBookSegments,
  proportionalOutsideBookGroups,
  readingIconGrid,
} from "./mapBookGeometry";

function book(id: number, pages: number | null, position = id): MapBook {
  return {
    id,
    title: `Book ${id}`,
    author: "Author",
    has_multiple_authors: false,
    structured_authors: [],
    cover_filename: null,
    isbn_10: null,
    isbn_13: null,
    subtitle: null,
    page_count: pages,
    publisher: null,
    current_ed_year: null,
    original_publication_year: null,
    language: null,
    edition_number: null,
    fiction_category: null,
    binding: null,
    publication_type: null,
    genre_text: null,
    series_name: null,
    series_volume: null,
    status: "PENDING",
    is_rereading: false,
    is_on_loan: false,
    loaned_to: null,
    container_id: 1,
    position,
    acquisition_date: null,
    reading_started_date: null,
    read_date: null,
  };
}

describe("page-proportional map geometry", () => {
  it("allocates strict proportional thickness", () => {
    const segments = proportionalBookSegments(
      [book(1, 100), book(2, 300)],
      80,
      200,
    );
    expect(segments[0].thickness).toBeCloseTo(20);
    expect(segments[1].thickness).toBeCloseTo(60);
  });

  it("keeps one scale across wrapped outside groups", () => {
    const groups = proportionalOutsideBookGroups(
      [book(1, 100), book(2, 300), book(3, 200)],
      200,
      2,
    );
    expect(groups).toHaveLength(2);
    expect(groups[0][0].share).toBeCloseTo(0.25);
    expect(groups[0][1].share).toBeCloseTo(0.75);
    expect(groups[1][0].share).toBeCloseTo(0.5);
  });

  it("does not enlarge a lone average book to fill an outside area", () => {
    const groups = proportionalOutsideBookGroups([book(1, 200)], 200, 10);
    expect(groups[0][0].share).toBeCloseTo(0.1);
  });

  it("reserves exactly one additional reading-icon share", () => {
    for (const count of [1, 2, 3, 4, 5, 8]) {
      const grid = readingIconGrid(count, 1.4);
      const gridArea = (grid.occupiedPercent / 100) ** 2;
      const iconArea = gridArea * count / (grid.rows * grid.columns);
      expect(iconArea).toBeCloseTo(count / (count + 1), 8);
    }
  });

  it("shrinks a left-anchored row without changing its origin", () => {
    const rect = containerRectWithoutAbsentBooks(
      { x: 10, y: 20, width: 60, height: 30 },
      "ROW",
      "LEFT",
      [book(1, 300)],
      [book(2, 100)],
      200,
    );
    expect(rect.x).toBe(10);
    expect(rect.width).toBeCloseTo(45);
  });

  it("preserves the bottom support of a reduced pile", () => {
    const rect = containerRectWithoutAbsentBooks(
      { x: 10, y: 20, width: 30, height: 60 },
      "PILE",
      "LEFT",
      [book(1, 100)],
      [book(2, 200)],
      200,
    );
    expect(rect.y + rect.height).toBeCloseTo(80);
    expect(rect.height).toBeCloseTo(20);
  });
});
