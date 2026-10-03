import type { AppLocale } from "./locale";

export const en = {
  loadFailed: "Loan data could not be loaded.", unknown: "Unknown", loanHistory: "Loan history", onLoanTo: "On loan to {borrower}", onLoan: "On loan", since: "since {date}", expected: "expected {date}", overdue: "overdue",
  returnedRecord: "Loaned {loaned} · returned {returned}", loanedTo: "Loaned to *", loanDate: "Loan date", optionalUnknown: "optional / unknown", expectedReturn: "Expected return", optional: "optional", privateNotes: "Private Owner notes",
  close: "Close", sharedCustody: "Shared physical custody", loans: "Loans", currentLoan: "Current loan", returnedDate: "Returned date", leaveBlankUnknown: "leave blank if unknown",
  cancelLoanConfirm: "Cancel this loan without retaining it in history?", cancelLoan: "Cancel loan", returnBook: "Return book", loanThisBook: "Loan this book", startLoan: "Start loan",
  correctHistorical: "Correct historical loan", addHistorical: "Add historical loan", cancelEdit: "Cancel edit", saveCorrection: "Save correction", addHistory: "Add history", returnedLoans: "Returned loans", edit: "Edit",
  deleteHistorical: "Delete historical loan", deleteHistoricalConfirm: "Permanently delete this historical loan?",
} as const;
export type LoanCopyKey = keyof typeof en;


export type LoanCopy = (key: LoanCopyKey, values?: Record<string, string | number>) => string;
const catalogues: Partial<Record<AppLocale, Record<LoanCopyKey, string>>> = { en };

export function registerLoanCatalogue(
  locale: AppLocale,
  catalogue: Record<LoanCopyKey, string>,
): void {
  catalogues[locale] = catalogue;
}
export function loanCopy(locale: AppLocale): LoanCopy {
  const catalogue = catalogues[locale];
  if (!catalogue) throw new Error(`Locale catalogue not loaded: ${locale}`);
  return (key, values = {}) => catalogue[key].replace(/\{(\w+)\}/g, (token, name: string) => Object.hasOwn(values, name) ? String(values[name]) : token);
}
