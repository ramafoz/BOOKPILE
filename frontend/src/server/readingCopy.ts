import type { AppLocale } from "./locale";

const en = {
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
const gl = {
  pending: "Pendente", reading: "En lectura…", rereading: "En relectura…", read: "Lido", loading: "Cargando…",
  copyBeingRead: "Este exemplar físico está en lectura", updateStatus: "Actualizar o teu estado de lectura", readOnly: "Esta perspectiva de lectura é de só lectura",
  unknown: "Descoñecida", datesUnknown: "Datas de lectura descoñecidas", since: "Desde o {date}", dateRange: "{start} – {finish}",
  history: "Historial de lectura", personalRecord: "Rexistro persoal de lectura de {name}", readingNumber: "Lectura {number}", noSessions: "Non hai sesións de lectura rexistradas para esta perspectiva.",
  goodreadsReviews: "Recensións en Goodreads", usersReview: "Recensión de {username}",
  finishRereading: "Remataches a relectura?", didYouFinish: "Remataches?", rereadBook: "Reler este libro?", startReading: "Comezar a ler?",
  cancelActive: "Cancelar esta {kind} activa? A sesión activa eliminarase definitivamente.", kindReading: "lectura", kindRereading: "relectura",
  close: "Pechar", personalReading: "Lectura persoal", finished: "Rematada", started: "Comezada", cancelReading: "Cancelar lectura", back: "Volver", saving: "Gardando…", confirm: "Confirmar",
  requestFailed: "BOOKPILE non puido completar esa solicitude.", permanentDelete: "Eliminar definitivamente esta lectura ({description})? Esta acción non se pode desfacer.",
  myPersonalData: "Os meus datos persoais", myReading: "A miña lectura", loadingRecord: "Cargando o teu rexistro de lectura…", edit: "Editar", delete: "Eliminar", noReadings: "Aínda non hai lecturas rexistradas.",
  editHistorical: "Editar lectura histórica", addHistorical: "Engadir lectura histórica", cancelEdit: "Cancelar edición", saveReading: "Gardar lectura", addReading: "Engadir lectura",
  myGoodreadsReview: "A miña recensión en Goodreads", reviewUrl: "URL da recensión", removeReviewHelp: "Déixao baleiro para eliminar a ligazón gardada da recensión.", saveGoodreads: "Gardar ligazón de Goodreads",
} satisfies Record<ReadingCopyKey, string>;

export type ReadingCopy = (key: ReadingCopyKey, values?: Record<string, string | number>) => string;
const catalogues: Record<AppLocale, Record<ReadingCopyKey, string>> = { en, gl };
export function readingCopy(locale: AppLocale): ReadingCopy {
  const catalogue = catalogues[locale];
  return (key, values = {}) => catalogue[key].replace(/\{(\w+)\}/g, (token, name: string) => Object.hasOwn(values, name) ? String(values[name]) : token);
}
