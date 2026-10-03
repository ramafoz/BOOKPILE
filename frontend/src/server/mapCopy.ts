import type { AppLocale } from "./locale";

export const en = {
  unavailable: "Library Map unavailable.", bookUnavailable: "Book information unavailable.", previewFailed: "The destination could not be previewed.", undoFailed: "Undo failed.", applyFailed: "The rearrangement could not be applied.", loading: "Loading Library Map…",
  visualIndex: "Visual library index", libraryMap: "Library Map", backCatalogue: "Back to catalogue", catalogue: "Catalogue", reorganize: "Reorganize books", editLayout: "Edit layout", chooseInspection: "Choose inspection mode", books: "Books", containers: "Containers", inspectionMode: "Inspection mode: {mode}. Tap to switch.",
  colourBy: "Colour by", genre: "Genre", publisher: "Publisher", author: "Author", choose: "Choose…", perspectiveColours: "Colours show {username}'s perspective. Physical custody is shared.",
  dragObject: "Drag selected object", resizeObject: "Resize selected object", cameraControls: "Map camera controls", resetView: "Reset view", zoomIn: "Zoom in", zoomOut: "Zoom out",
  draftMovement: "Draft movement", chooseBook: "Choose a book", chooseBookMap: "Choose a book on the map", expandDraft: "Expand draft", collapseDraft: "Collapse draft", expand: "Expand", collapse: "Collapse", cancelDraft: "Cancel draft",
  oldPosition: "Old position", newPosition: "New position", collapsePosition: "Collapse", leaveGap: "Leave gap", squeeze: "Squeeze", swap: "Swap", continue: "Continue", releaseSpace: "Release shelf space if this move removes pages from its source container",
  book: "Book", chooseMapHere: "Choose on map or here", destinationContainer: "Destination container", shelf: "Shelf", background: "Background", foreground: "Foreground", row: "Row", pile: "Pile", position: "Position", previewDestination: "Preview destination", moveNumber: "Move {number}", unchangedDraft: "This draft adds up to an unchanged arrangement. Add another move or cancel it.", undo: "Undo last step", addMove: "Add another move", apply: "Apply",
  bookMoved: "“{title}”: {source} → {destination}", bookShifted: "{count} book shifted {reason}.", booksShifted: "{count} books shifted {reason}.", occupyGap: "to occupy the gap", fillGapAndMakeRoom: "to fill the gap and make new room", makeRoom: "to make room", continueWithBook: "Continue with “{title}”.", noStackingCapacity: "{container} has no free stacking-axis capacity.", booksCompressed: "{container} will compress its books by {percent}%.", insufficientCapacity: "{container} needs {needed}% but only {available}% is available.", unknownScale: "{container} had no known scale; its first book uses 10% of available space.", layoutConflict: "The projected layout conflicts with another physical element.", rearrangementWarning: "The movement needs attention before it can be applied.",
  clearSelection: "Clear selection", selectedBook: "Selected book", pages: "{count} pages", unknownPages: "Page count unknown · visual fallback {count} pages", selectedContainer: "Selected container", bookCount: "{count} book", booksCount: "{count} books", focusContainer: "Focus container", loadingDetails: "Loading…", completeInformation: "Complete information", readOnlyInspection: "Read-only inspection",
  readingStatus: "Reading status", acquisitionRecency: "Acquisition recency", readingRecency: "Reading recency", pendingDuration: "Time spent pending", readingDuration: "Reading duration", readingRate: "Reading rate (pages/day)", language: "Language", originalLanguage: "Original language", translationStatus: "Translation status", editionYear: "Current edition year", originalYear: "Original publication year", genreFocus: "Genre focus", publisherFocus: "Publisher focus", authorFocus: "Author focus", fictionCategory: "Fiction / non-fiction", binding: "Binding", publicationType: "Publication type",
  pending: "Pending", reading: "Reading", onLoan: "On loan", physicalCopyReading: "This physical copy is being read", physicalCopyOnLoan: "This physical copy is on loan", rereading: "Re-reading", read: "Read", notSelected: "Not selected", otherBooks: "Other books", chooseFocus: "Choose a {mode}", notRecorded: "Not recorded", originalCollection: "Original collection", noAcquisitionDate: "No acquisition date", stillReading: "Still reading", stillRereading: "Still re-reading", readNoData: "Read · no data", noData: "No data", days: "{count} days", pagesPerDay: "{count} pages/day", noRecordedData: "No recorded data", shortest: "Shortest", longest: "Longest", slowest: "Slowest", fastest: "Fastest", oldest: "Oldest", newest: "Newest", endpointOne: "{adjective}: “{title}” · {value}", endpointTie: "{adjective}: tie ({count}) · {value}",
} as const;
export type MapCopyKey = keyof typeof en;



export type MapCopy = (key: MapCopyKey, values?: Record<string, string | number>) => string;
const catalogues: Partial<Record<AppLocale, Record<MapCopyKey, string>>> = { en };

export function registerMapCatalogue(
  locale: AppLocale,
  catalogue: Record<MapCopyKey, string>,
): void {
  catalogues[locale] = catalogue;
}
export function mapCopy(locale: AppLocale): MapCopy {
  const catalogue = catalogues[locale];
  if (!catalogue) throw new Error(`Locale catalogue not loaded: ${locale}`);
  return (key, values = {}) => catalogue[key].replace(/\{(\w+)\}/g, (token, name: string) => Object.hasOwn(values, name) ? String(values[name]) : token);
}
