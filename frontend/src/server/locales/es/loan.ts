import type { LoanCopyKey } from "../../loanCopy";

export const loanEs = {
  loadFailed: "No se han podido cargar los datos de los préstamos.", unknown: "Desconocida", loanHistory: "Historial de préstamos", onLoanTo: "Prestado a {borrower}", onLoan: "Prestado", since: "desde el {date}", expected: "previsto para el {date}", overdue: "atrasado",
  returnedRecord: "Prestado el {loaned} · devuelto el {returned}", loanedTo: "Prestado a *", loanDate: "Fecha del préstamo", optionalUnknown: "opcional / desconocida", expectedReturn: "Devolución prevista", optional: "opcional", privateNotes: "Notas privadas de las personas propietarias",
  close: "Cerrar", sharedCustody: "Custodia física compartida", loans: "Préstamos", currentLoan: "Préstamo actual", returnedDate: "Fecha de devolución", leaveBlankUnknown: "déjala vacía si no se conoce",
  cancelLoanConfirm: "¿Cancelar este préstamo sin conservarlo en el historial?", cancelLoan: "Cancelar préstamo", returnBook: "Devolver libro", loanThisBook: "Prestar este libro", startLoan: "Iniciar préstamo",
  correctHistorical: "Corregir préstamo histórico", addHistorical: "Añadir préstamo histórico", cancelEdit: "Cancelar edición", saveCorrection: "Guardar corrección", addHistory: "Añadir al historial", returnedLoans: "Préstamos devueltos", edit: "Editar",
  deleteHistorical: "Eliminar préstamo histórico", deleteHistoricalConfirm: "¿Eliminar definitivamente este préstamo histórico?",
} satisfies Record<LoanCopyKey, string>;
