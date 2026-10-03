import type { ReadingCopyKey } from "../../readingCopy";

export const readingGl = {
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
