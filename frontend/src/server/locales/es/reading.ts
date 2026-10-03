import type { ReadingCopyKey } from "../../readingCopy";

export const readingEs = {
  pending: "Pendiente", reading: "En lectura…", rereading: "En relectura…", read: "Leído", loading: "Cargando…",
  copyBeingRead: "Este ejemplar físico está en lectura", updateStatus: "Actualizar tu estado de lectura", readOnly: "Esta perspectiva de lectura es de solo lectura",
  unknown: "Desconocida", datesUnknown: "Fechas de lectura desconocidas", since: "Desde el {date}", dateRange: "{start} – {finish}",
  history: "Historial de lectura", personalRecord: "Registro personal de lectura de {name}", readingNumber: "Lectura {number}", noSessions: "No hay sesiones de lectura registradas para esta perspectiva.",
  goodreadsReviews: "Reseñas en Goodreads", usersReview: "Reseña de {username}",
  finishRereading: "¿Has terminado la relectura?", didYouFinish: "¿Has terminado?", rereadBook: "¿Volver a leer este libro?", startReading: "¿Empezar a leer?",
  cancelActive: "¿Cancelar esta {kind} activa? La sesión activa se eliminará definitivamente.", kindReading: "lectura", kindRereading: "relectura",
  close: "Cerrar", personalReading: "Lectura personal", finished: "Terminada", started: "Iniciada", cancelReading: "Cancelar lectura", back: "Volver", saving: "Guardando…", confirm: "Confirmar",
  requestFailed: "BOOKPILE no ha podido completar esa solicitud.", permanentDelete: "¿Eliminar definitivamente esta lectura ({description})? Esta acción no se puede deshacer.",
  myPersonalData: "Mis datos personales", myReading: "Mi lectura", loadingRecord: "Cargando tu registro de lectura…", edit: "Editar", delete: "Eliminar", noReadings: "Todavía no hay lecturas registradas.",
  editHistorical: "Editar lectura histórica", addHistorical: "Añadir lectura histórica", cancelEdit: "Cancelar edición", saveReading: "Guardar lectura", addReading: "Añadir lectura",
  myGoodreadsReview: "Mi reseña en Goodreads", reviewUrl: "URL de la reseña", removeReviewHelp: "Déjalo vacío para eliminar el enlace guardado de la reseña.", saveGoodreads: "Guardar enlace de Goodreads",
} satisfies Record<ReadingCopyKey, string>;
