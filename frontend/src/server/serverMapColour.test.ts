import { describe, expect, it } from "vitest";
import type { PhysicalBook, ReadingCatalogueOverview } from "./serverApi";
import { buildMapColourScale } from "./serverMapColour";

const book = (id: string, extra: Partial<PhysicalBook> = {}): PhysicalBook => ({
  id, title: `Book ${id}`, author: "Author", page_count: 200,
  height_mm: null, width_mm: null, thickness_mm: null, container_id: "container", position: 1,
  ...extra,
});
const reading = (bookId: string, state: ReadingCatalogueOverview["items"][number]["state"], active = false): ReadingCatalogueOverview["items"][number] => ({
  book_id: bookId, state, active_reader_present: active, goodreads_url: null,
  started_date: null, finished_date: null, dates_unknown: false,
});

describe("server map colour scales", () => {
  it("keeps physical custody separate from the selected reading perspective", () => {
    const target = book("one");
    const scale = buildMapColourScale("status", [target], new Map([[target.id, reading(target.id, "PENDING", true)]]));
    expect(scale.detail(target)).toBe("Pending");
    expect(scale.colour(target)).not.toBe("#557f93");
  });

  it("flattens numeric outliers to the first and ninety-ninth percentile", () => {
    const books = Array.from({ length: 101 }, (_, index) => book(String(index), { current_ed_year: index === 100 ? 9999 : 1900 + index }));
    const scale = buildMapColourScale("current_ed_year", books, new Map());
    expect(scale.lowLabel).toContain("Book 0");
    expect(scale.highLabel).toContain("Book 100");
    expect(scale.colour(books[99])).toBe(scale.colour(books[100]));
  });

  it("supports categorical and focused metadata", () => {
    const first = book("one", { language: "Galician", original_language: "English", translation_status: "TRANSLATED", genre_text: "History, Galicia" });
    const second = book("two", { language: "English", original_language: "English", translation_status: "ORIGINAL", genre_text: "Science" });
    expect(buildMapColourScale("language", [first, second], new Map()).colour(first)).not.toBe(buildMapColourScale("language", [first, second], new Map()).colour(second));
    expect(buildMapColourScale("translation_status", [first, second], new Map()).detail(first)).toBe("Translated");
    expect(buildMapColourScale("original_language", [first, second], new Map()).detail(first)).toBe("English");
    expect(buildMapColourScale("genre", [first, second], new Map(), "Galicia").detail(first)).toBe("Galicia");
  });
});
