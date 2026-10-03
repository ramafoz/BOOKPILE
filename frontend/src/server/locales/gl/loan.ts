import type { LoanCopyKey } from "../../loanCopy";

export const loanGl = {
  loadFailed: "Non se puideron cargar os datos dos préstamos.", unknown: "Descoñecida", loanHistory: "Historial de préstamos", onLoanTo: "Prestado a {borrower}", onLoan: "Prestado", since: "desde o {date}", expected: "previsto para o {date}", overdue: "atrasado",
  returnedRecord: "Prestado o {loaned} · devolto o {returned}", loanedTo: "Prestado a *", loanDate: "Data do préstamo", optionalUnknown: "opcional / descoñecida", expectedReturn: "Devolución prevista", optional: "opcional", privateNotes: "Notas privadas das persoas propietarias",
  close: "Pechar", sharedCustody: "Custodia física compartida", loans: "Préstamos", currentLoan: "Préstamo actual", returnedDate: "Data de devolución", leaveBlankUnknown: "déixaa baleira se non se coñece",
  cancelLoanConfirm: "Cancelar este préstamo sen conservalo no historial?", cancelLoan: "Cancelar préstamo", returnBook: "Devolver libro", loanThisBook: "Prestar este libro", startLoan: "Iniciar préstamo",
  correctHistorical: "Corrixir préstamo histórico", addHistorical: "Engadir préstamo histórico", cancelEdit: "Cancelar edición", saveCorrection: "Gardar corrección", addHistory: "Engadir ao historial", returnedLoans: "Préstamos devoltos", edit: "Editar",
  deleteHistorical: "Eliminar préstamo histórico", deleteHistoricalConfirm: "Eliminar definitivamente este préstamo histórico?",
} satisfies Record<LoanCopyKey, string>;
