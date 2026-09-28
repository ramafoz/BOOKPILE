import type { AppLocale } from "./locale";

const en = {
  loadFailed: "Loan data could not be loaded.", unknown: "Unknown", loanHistory: "Loan history", onLoanTo: "On loan to {borrower}", onLoan: "On loan", since: "since {date}", expected: "expected {date}", overdue: "overdue",
  returnedRecord: "Loaned {loaned} · returned {returned}", loanedTo: "Loaned to *", loanDate: "Loan date", optionalUnknown: "optional / unknown", expectedReturn: "Expected return", optional: "optional", privateNotes: "Private Owner notes",
  close: "Close", sharedCustody: "Shared physical custody", loans: "Loans", currentLoan: "Current loan", returnedDate: "Returned date", leaveBlankUnknown: "leave blank if unknown",
  cancelLoanConfirm: "Cancel this loan without retaining it in history?", cancelLoan: "Cancel loan", returnBook: "Return book", loanThisBook: "Loan this book", startLoan: "Start loan",
  correctHistorical: "Correct historical loan", addHistorical: "Add historical loan", cancelEdit: "Cancel edit", saveCorrection: "Save correction", addHistory: "Add history", returnedLoans: "Returned loans", edit: "Edit",
  deleteHistorical: "Delete historical loan", deleteHistoricalConfirm: "Permanently delete this historical loan?",
} as const;
export type LoanCopyKey = keyof typeof en;
const gl = {
  loadFailed: "Non se puideron cargar os datos dos préstamos.", unknown: "Descoñecida", loanHistory: "Historial de préstamos", onLoanTo: "Prestado a {borrower}", onLoan: "Prestado", since: "desde o {date}", expected: "previsto para o {date}", overdue: "atrasado",
  returnedRecord: "Prestado o {loaned} · devolto o {returned}", loanedTo: "Prestado a *", loanDate: "Data do préstamo", optionalUnknown: "opcional / descoñecida", expectedReturn: "Devolución prevista", optional: "opcional", privateNotes: "Notas privadas das persoas propietarias",
  close: "Pechar", sharedCustody: "Custodia física compartida", loans: "Préstamos", currentLoan: "Préstamo actual", returnedDate: "Data de devolución", leaveBlankUnknown: "déixaa baleira se non se coñece",
  cancelLoanConfirm: "Cancelar este préstamo sen conservalo no historial?", cancelLoan: "Cancelar préstamo", returnBook: "Devolver libro", loanThisBook: "Prestar este libro", startLoan: "Iniciar préstamo",
  correctHistorical: "Corrixir préstamo histórico", addHistorical: "Engadir préstamo histórico", cancelEdit: "Cancelar edición", saveCorrection: "Gardar corrección", addHistory: "Engadir ao historial", returnedLoans: "Préstamos devoltos", edit: "Editar",
  deleteHistorical: "Eliminar préstamo histórico", deleteHistoricalConfirm: "Eliminar definitivamente este préstamo histórico?",
} satisfies Record<LoanCopyKey, string>;
export type LoanCopy = (key: LoanCopyKey, values?: Record<string, string | number>) => string;
const catalogues: Record<AppLocale, Record<LoanCopyKey, string>> = { en, gl };
export function loanCopy(locale: AppLocale): LoanCopy {
  const catalogue = catalogues[locale];
  return (key, values = {}) => catalogue[key].replace(/\{(\w+)\}/g, (token, name: string) => Object.hasOwn(values, name) ? String(values[name]) : token);
}
