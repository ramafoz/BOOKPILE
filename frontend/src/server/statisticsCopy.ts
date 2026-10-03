import type { AppLocale } from "./locale";

export const en = {
  loadFailed: "Statistics could not be loaded.", days: "{count} days", noUsableDates: "No usable dates", durationSummary: "Median {median} · {measured} measured · {excluded} excluded",
  personalPerspective: "Personal reading perspective", usersStatistics: "{username}'s statistics", personalReadingHelp: "Reading events are personal; catalogue ownership remains shared.",
  language: "Language", allLanguages: "All languages", genre: "Genre", allGenres: "All genres", publisher: "Publisher", allPublishers: "All publishers", finishedYear: "Finished in year", allYears: "All years", clear: "Clear", apply: "Apply",
  uniqueBooks: "Unique books read", readingEvents: "Reading events", dated: "{count} dated", rereadings: "Rereadings", averagePagesDay: "Average pages/day", pendingTime: "Time spent pending", readingDuration: "Reading duration",
  readingPace: "Reading pace", pagesRead: "pages read", pagesWeek: "pages/week", pagesMonth: "pages/month", medianPagesDay: "median pages/day per book",
  readingByYear: "Reading by year", year: "Year", books: "Books", readings: "Readings", pages: "Pages", noDatedReadings: "No dated readings match these filters.", booksResult: "Books in this result", book: "Book", daysReading: "Days reading", pagesDay: "Pages/day", noCompletedReadings: "No completed readings match these filters.",
  statisticsNote: "Unknown-date historical readings count as personal history, but cannot be assigned to dated page or rate statistics. Missing page counts contribute no pages.",
  sharedCustody: "Shared physical custody", loanStatistics: "Loan statistics", loanHelp: "These totals belong to the library and do not change with reading perspective.", currentlyLoaned: "Currently on loan", overdue: "Overdue", returnedLoans: "Returned loans", unknownDates: "Unknown dates", unknownDateSummary: "{loaned} loaned · {returned} returned",
  loansByYear: "Loans by year", loaned: "Loaned", returned: "Returned", noDatedLoans: "No dated loans match these filters.", mostLoaned: "Most loaned books", loans: "Loans", noLoans: "No loans match these filters.",
} as const;
export type StatisticsCopyKey = keyof typeof en;



export type StatisticsCopy = (key: StatisticsCopyKey, values?: Record<string, string | number>) => string;
const catalogues: Partial<Record<AppLocale, Record<StatisticsCopyKey, string>>> = { en };

export function registerStatisticsCatalogue(
  locale: AppLocale,
  catalogue: Record<StatisticsCopyKey, string>,
): void {
  catalogues[locale] = catalogue;
}
export function statisticsCopy(locale: AppLocale): StatisticsCopy {
  const catalogue = catalogues[locale];
  if (!catalogue) throw new Error(`Locale catalogue not loaded: ${locale}`);
  return (key, values = {}) => catalogue[key].replace(/\{(\w+)\}/g, (token, name: string) => Object.hasOwn(values, name) ? String(values[name]) : token);
}
