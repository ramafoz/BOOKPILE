import type { PersonalReadingState, PhysicalBook, ReadingCatalogueOverview } from "./serverApi";

export type MapColourMode = "status" | "acquisition" | "finished" | "pending_duration" | "reading_duration" | "reading_rate" | "language" | "original_language" | "translation_status" | "current_ed_year" | "original_publication_year" | "genre" | "publisher" | "author" | "fiction_category" | "binding" | "publication_type";
export const MAP_COLOUR_OPTIONS: Array<{ value: MapColourMode; label: string }> = [
  { value: "status", label: "Reading status" }, { value: "acquisition", label: "Acquisition recency" },
  { value: "finished", label: "Reading recency" }, { value: "pending_duration", label: "Time spent pending" },
  { value: "reading_duration", label: "Reading duration" }, { value: "reading_rate", label: "Reading rate (pages/day)" },
  { value: "language", label: "Language" }, { value: "original_language", label: "Original language" },
  { value: "translation_status", label: "Translation status" }, { value: "current_ed_year", label: "Current edition year" },
  { value: "original_publication_year", label: "Original publication year" }, { value: "genre", label: "Genre focus" },
  { value: "publisher", label: "Publisher focus" }, { value: "author", label: "Author focus" },
  { value: "fiction_category", label: "Fiction / non-fiction" }, { value: "binding", label: "Binding" },
  { value: "publication_type", label: "Publication type" },
];

export type MapReading = ReadingCatalogueOverview["items"][number];
export interface MapColourScale {
  label: string; colour: (book: PhysicalBook) => string; detail: (book: PhysicalBook) => string;
  lowLabel?: string; highLabel?: string; legendItems: Array<{ label: string; colour: string }>; continuous: boolean;
}

const MISSING = "#e5dfd5", PENDING = "#d29a46", READING = "#557f93", REREADING = "#80669a";
const LIGHT = "#d7e8ec", DARK = "#8b4035", FOCUS = "#397f73";
const CATEGORIES = ["#397f73", "#b46f4f", "#537c9a", "#b08a3f", "#7d668f", "#698453", "#a55c6b", "#4f8688", "#8c704c", "#6f7796"];
const titleCase = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
const day = (value: string | null | undefined) => value ? Math.floor(Date.parse(`${value}T00:00:00Z`) / 86_400_000) : null;
const duration = (start: string | null | undefined, end: string | null | undefined) => {
  const first = day(start), last = day(end); return first === null || last === null ? null : Math.max(1, last - first + 1);
};
const interpolate = (start: string, end: string, amount: number) => {
  const channel = (value: string, offset: number) => Number.parseInt(value.slice(offset, offset + 2), 16);
  const mix = (offset: number) => Math.round(channel(start, offset) + (channel(end, offset) - channel(start, offset)) * amount).toString(16).padStart(2, "0");
  return `#${mix(1)}${mix(3)}${mix(5)}`;
};
const percentile = (values: number[], fraction: number) => {
  if (!values.length) return 0; const index = (values.length - 1) * fraction, lower = Math.floor(index), upper = Math.ceil(index);
  return lower === upper ? values[lower] : values[lower] + (values[upper] - values[lower]) * (index - lower);
};
const statusColour = (state: PersonalReadingState) => state === "READ" ? "#4f887b" : state === "READING" ? READING : state === "REREADING" ? REREADING : PENDING;
const genres = (book: PhysicalBook) => (book.genre_text ?? "").split(",").map((value) => value.trim()).filter(Boolean);

export function buildMapColourScale(mode: MapColourMode, books: PhysicalBook[], readings: Map<string, MapReading>, focus = ""): MapColourScale {
  const label = MAP_COLOUR_OPTIONS.find((option) => option.value === mode)?.label ?? mode;
  const reading = (book: PhysicalBook) => readings.get(book.id);
  if (mode === "status") return { label, colour: (book) => statusColour(reading(book)?.state ?? "PENDING"), detail: (book) => titleCase(reading(book)?.state ?? "PENDING"), legendItems: [
    { label: "Pending", colour: PENDING }, { label: "Reading", colour: READING }, { label: "Re-reading", colour: REREADING }, { label: "Read", colour: "#4f887b" },
  ], continuous: false };
  if (["genre", "publisher", "author"].includes(mode)) {
    const matches = (book: PhysicalBook) => mode === "genre" ? genres(book).includes(focus) : mode === "publisher" ? book.publisher === focus : book.author === focus;
    return { label, colour: (book) => focus && matches(book) ? FOCUS : MISSING, detail: (book) => focus && matches(book) ? focus : "Not selected", legendItems: focus ? [{ label: focus, colour: FOCUS }, { label: "Other books", colour: MISSING }] : [{ label: `Choose a ${mode}`, colour: MISSING }], continuous: false };
  }
  const category = (book: PhysicalBook) => mode === "language" ? book.language : mode === "original_language" ? book.original_language : mode === "translation_status" ? book.translation_status : mode === "fiction_category" ? book.fiction_category : mode === "binding" ? book.binding : mode === "publication_type" ? book.publication_type : null;
  if (["language", "original_language", "translation_status", "fiction_category", "binding", "publication_type"].includes(mode)) {
    const values = [...new Set(books.map(category).filter((value): value is string => Boolean(value)))].sort((a, b) => a.localeCompare(b));
    const colours = new Map(values.map((value, index) => [value, CATEGORIES[index % CATEGORIES.length]]));
    return { label, colour: (book) => colours.get(category(book) ?? "") ?? MISSING, detail: (book) => category(book) ? titleCase(category(book)!) : "Not recorded", legendItems: [...values.map((value) => ({ label: titleCase(value), colour: colours.get(value)! })), { label: "Not recorded", colour: MISSING }], continuous: false };
  }
  const metric = (book: PhysicalBook): number | null => {
    const item = reading(book);
    if (mode === "acquisition") return day(book.acquisition_date);
    if (mode === "finished") return day(item?.finished_date);
    if (mode === "pending_duration") return duration(book.acquisition_date, item?.started_date);
    if (mode === "reading_duration") return duration(item?.started_date, item?.finished_date);
    if (mode === "reading_rate") { const days = duration(item?.started_date, item?.finished_date); return book.page_count && days ? book.page_count / days : null; }
    if (mode === "current_ed_year") return book.current_ed_year ?? null;
    if (mode === "original_publication_year") return book.original_publication_year ?? null;
    return null;
  };
  const special = (book: PhysicalBook): { label: string; colour: string } | null => {
    const item = reading(book), state = item?.state ?? "PENDING";
    if (mode === "acquisition" && !book.acquisition_date) return { label: book.is_original_collection ? "Original collection" : "No acquisition date", colour: MISSING };
    if (mode === "finished" && state === "PENDING") return { label: "Pending", colour: PENDING };
    if (mode === "finished" && ["READING", "REREADING"].includes(state)) return { label: state === "REREADING" ? "Re-reading" : "Reading", colour: state === "REREADING" ? REREADING : READING };
    if (["pending_duration", "reading_duration", "reading_rate"].includes(mode) && state === "PENDING") return { label: "Pending", colour: PENDING };
    if (["reading_duration", "reading_rate"].includes(mode) && ["READING", "REREADING"].includes(state)) return { label: state === "REREADING" ? "Still re-reading" : "Still reading", colour: state === "REREADING" ? REREADING : READING };
    if (metric(book) === null) return { label: state === "READ" ? "Read · no data" : "No data", colour: MISSING };
    return null;
  };
  const scored = books.map((book) => ({ book, value: metric(book) })).filter((item): item is { book: PhysicalBook; value: number } => !special(item.book) && item.value !== null);
  const values = scored.map((item) => item.value).sort((a, b) => a - b), minimum = percentile(values, values.length >= 3 ? .01 : 0), maximum = percentile(values, values.length >= 3 ? .99 : 1);
  const describe = (value: number) => mode.includes("duration") ? `${Math.round(value)} days` : mode === "reading_rate" ? `${value.toFixed(1)} pages/day` : mode.includes("year") ? String(value) : new Date(value * 86_400_000).toLocaleDateString();
  const endpoint = (low: boolean) => { if (!scored.length) return "No recorded data"; const value = low ? values[0] : values.at(-1)!; const winners = scored.filter((item) => item.value === value); const adjective = mode.includes("duration") ? (low ? "Shortest" : "Longest") : mode === "reading_rate" ? (low ? "Slowest" : "Fastest") : (low ? "Oldest" : "Newest"); return winners.length === 1 ? `${adjective}: “${winners[0].book.title}” · ${describe(value)}` : `${adjective}: tie (${winners.length}) · ${describe(value)}`; };
  const legendItems = [...new Map(books.map(special).filter((item): item is { label: string; colour: string } => Boolean(item)).map((item) => [item.label, item])).values()];
  return { label, colour: (book) => { const item = special(book); if (item) return item.colour; const value = metric(book); if (value === null) return MISSING; const amount = maximum === minimum ? .65 : Math.max(0, Math.min(1, (value - minimum) / (maximum - minimum))); return interpolate(LIGHT, DARK, amount); }, detail: (book) => special(book)?.label ?? (metric(book) === null ? "No data" : describe(metric(book)!)), lowLabel: endpoint(true), highLabel: endpoint(false), legendItems, continuous: true };
}
