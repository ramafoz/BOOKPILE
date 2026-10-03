import type { AppLocale } from "./locale";
import { statisticsPt } from "./locales/pt/statistics";

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
const gl = {
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
export const es = {
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
export const pt = statisticsPt;

export type StatisticsCopy = (key: StatisticsCopyKey, values?: Record<string, string | number>) => string;
const catalogues: Record<AppLocale, Record<StatisticsCopyKey, string>> = { en, gl, es, pt };
export function statisticsCopy(locale: AppLocale): StatisticsCopy {
  const catalogue = catalogues[locale];
  return (key, values = {}) => catalogue[key].replace(/\{(\w+)\}/g, (token, name: string) => Object.hasOwn(values, name) ? String(values[name]) : token);
}
