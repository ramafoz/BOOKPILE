import type { LocaleContextValue } from "./LocaleContext";
import { ServerApiError } from "./serverApi";

export function friendlyError(error: unknown, t: LocaleContextValue["t"]): string {
  if (error instanceof ServerApiError) {
    if (error.status === 429) {
      const minutes = error.retryAfter
        ? Math.max(1, Math.ceil(error.retryAfter / 60))
        : null;
      return minutes
        ? t(minutes === 1 ? "tooManyAttemptsMinutesOne" : "tooManyAttemptsMinutesMany", { minutes })
        : t("tooManyAttempts");
    }
    return error.message;
  }
  return t("serverUnavailable");
}
