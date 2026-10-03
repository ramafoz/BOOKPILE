import type { StatisticsCopyKey } from "../../statisticsCopy";

export const statisticsEs = {
  loadFailed: "No se han podido cargar las estadísticas.", days: "{count} días", noUsableDates: "No hay fechas utilizables", durationSummary: "Mediana {median} · {measured} medidas · {excluded} excluidas",
  personalPerspective: "Perspectiva personal de lectura", usersStatistics: "Estadísticas de {username}", personalReadingHelp: "Los eventos de lectura son personales; la propiedad del catálogo sigue siendo compartida.",
  language: "Idioma", allLanguages: "Todos los idiomas", genre: "Género", allGenres: "Todos los géneros", publisher: "Editorial", allPublishers: "Todas las editoriales", finishedYear: "Terminado en el año", allYears: "Todos los años", clear: "Limpiar", apply: "Aplicar",
  uniqueBooks: "Libros distintos leídos", readingEvents: "Eventos de lectura", dated: "{count} con fecha", rereadings: "Relecturas", averagePagesDay: "Media de páginas/día", pendingTime: "Tiempo pendiente", readingDuration: "Duración de la lectura",
  readingPace: "Ritmo de lectura", pagesRead: "páginas leídas", pagesWeek: "páginas/semana", pagesMonth: "páginas/mes", medianPagesDay: "mediana de páginas/día por libro",
  readingByYear: "Lectura por año", year: "Año", books: "Libros", readings: "Lecturas", pages: "Páginas", noDatedReadings: "No hay lecturas con fecha que coincidan con estos filtros.", booksResult: "Libros de este resultado", book: "Libro", daysReading: "Días de lectura", pagesDay: "Páginas/día", noCompletedReadings: "No hay lecturas completadas que coincidan con estos filtros.",
  statisticsNote: "Las lecturas históricas sin fecha cuentan en el historial personal, pero no se pueden asignar a estadísticas de páginas o ritmo con fecha. Los libros sin número de páginas no aportan páginas.",
  sharedCustody: "Custodia física compartida", loanStatistics: "Estadísticas de préstamos", loanHelp: "Estos totales pertenecen a la biblioteca y no cambian con la perspectiva de lectura.", currentlyLoaned: "Prestados actualmente", overdue: "Atrasados", returnedLoans: "Préstamos devueltos", unknownDates: "Fechas desconocidas", unknownDateSummary: "{loaned} prestados · {returned} devueltos",
  loansByYear: "Préstamos por año", loaned: "Prestados", returned: "Devueltos", noDatedLoans: "No hay préstamos con fecha que coincidan con estos filtros.", mostLoaned: "Libros más prestados", loans: "Préstamos", noLoans: "No hay préstamos que coincidan con estos filtros.",
} satisfies Record<StatisticsCopyKey, string>;
