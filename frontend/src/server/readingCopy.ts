import type { AppLocale } from "./locale";

export const en = {
  pending: "Pending", reading: "Reading…", rereading: "Re-reading…", read: "Read", loading: "Loading…",
  copyBeingRead: "This physical copy is currently being read", updateStatus: "Update your reading status", readOnly: "This reading perspective is read-only",
  unknown: "Unknown", datesUnknown: "Reading dates unknown", since: "Since {date}", dateRange: "{start} – {finish}",
  history: "Reading history", personalRecord: "{name}'s personal reading record", readingNumber: "Reading {number}", noSessions: "No reading sessions recorded for this perspective.",
  goodreadsReviews: "Goodreads reviews", usersReview: "{username}'s review",
  finishRereading: "Finish re-reading?", didYouFinish: "Did you finish?", rereadBook: "Re-read this book?", startReading: "Start reading?",
  cancelActive: "Cancel this active {kind}? The active session will be permanently removed.", kindReading: "reading", kindRereading: "re-reading",
  close: "Close", personalReading: "Personal reading", finished: "Finished", started: "Started", cancelReading: "Cancel reading", back: "Back", saving: "Saving…", confirm: "Confirm",
  requestFailed: "BOOKPILE could not complete that request.", permanentDelete: "Permanently delete this reading ({description})? This cannot be undone.",
  myPersonalData: "My personal data", myReading: "My reading", loadingRecord: "Loading your reading record…", edit: "Edit", delete: "Delete", noReadings: "No readings recorded yet.",
  editHistorical: "Edit historical reading", addHistorical: "Add historical reading", cancelEdit: "Cancel edit", saveReading: "Save reading", addReading: "Add reading",
  myGoodreadsReview: "My Goodreads review", reviewUrl: "Review URL", removeReviewHelp: "Leave this empty to remove your saved review link.", saveGoodreads: "Save Goodreads link",
} as const;
export type ReadingCopyKey = keyof typeof en;



export type ReadingCopy = (key: ReadingCopyKey, values?: Record<string, string | number>) => string;
const catalogues: Partial<Record<AppLocale, Record<ReadingCopyKey, string>>> = { en };

export function registerReadingCatalogue(
  locale: AppLocale,
  catalogue: Record<ReadingCopyKey, string>,
): void {
  catalogues[locale] = catalogue;
}
export function readingCopy(locale: AppLocale): ReadingCopy {
  const catalogue = catalogues[locale];
  if (!catalogue) throw new Error(`Locale catalogue not loaded: ${locale}`);
  return (key, values = {}) => catalogue[key].replace(/\{(\w+)\}/g, (token, name: string) => Object.hasOwn(values, name) ? String(values[name]) : token);
}
