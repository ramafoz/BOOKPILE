import type { StatisticsCopyKey } from "../../statisticsCopy";

export const statisticsGl = {
  loadFailed: "Non se puideron cargar as estatísticas.", days: "{count} días", noUsableDates: "Non hai datas utilizables", durationSummary: "Mediana {median} · {measured} medidas · {excluded} excluídas",
  personalPerspective: "Perspectiva persoal de lectura", usersStatistics: "Estatísticas de {username}", personalReadingHelp: "Os eventos de lectura son persoais; a propiedade do catálogo segue sendo compartida.",
  language: "Idioma", allLanguages: "Todos os idiomas", genre: "Xénero", allGenres: "Todos os xéneros", publisher: "Editorial", allPublishers: "Todas as editoriais", finishedYear: "Rematado no ano", allYears: "Todos os anos", clear: "Limpar", apply: "Aplicar",
  uniqueBooks: "Libros distintos lidos", readingEvents: "Eventos de lectura", dated: "{count} con data", rereadings: "Relecturas", averagePagesDay: "Media de páxinas/día", pendingTime: "Tempo pendente", readingDuration: "Duración da lectura",
  readingPace: "Ritmo de lectura", pagesRead: "páxinas lidas", pagesWeek: "páxinas/semana", pagesMonth: "páxinas/mes", medianPagesDay: "mediana de páxinas/día por libro",
  readingByYear: "Lectura por ano", year: "Ano", books: "Libros", readings: "Lecturas", pages: "Páxinas", noDatedReadings: "Non hai lecturas con data que coincidan con estes filtros.", booksResult: "Libros deste resultado", book: "Libro", daysReading: "Días de lectura", pagesDay: "Páxinas/día", noCompletedReadings: "Non hai lecturas completadas que coincidan con estes filtros.",
  statisticsNote: "As lecturas históricas sen data contan no historial persoal, pero non se poden asignar a estatísticas de páxinas ou ritmo con data. Os libros sen número de páxinas non achegan páxinas.",
  sharedCustody: "Custodia física compartida", loanStatistics: "Estatísticas de préstamos", loanHelp: "Estes totais pertencen á biblioteca e non cambian coa perspectiva de lectura.", currentlyLoaned: "Actualmente prestados", overdue: "Atrasados", returnedLoans: "Préstamos devoltos", unknownDates: "Datas descoñecidas", unknownDateSummary: "{loaned} prestados · {returned} devoltos",
  loansByYear: "Préstamos por ano", loaned: "Prestados", returned: "Devoltos", noDatedLoans: "Non hai préstamos con data que coincidan con estes filtros.", mostLoaned: "Libros máis prestados", loans: "Préstamos", noLoans: "Non hai préstamos que coincidan con estes filtros.",
} satisfies Record<StatisticsCopyKey, string>;
