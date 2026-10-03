import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LocaleContext } from "./LocaleContext";
import {
  type AppLocale, LOCALE_STORAGE_KEY, resolveLocale, translate,
} from "./locale";
import { loadLocaleCatalogues } from "./localeCatalogues";

function initialLocale(): AppLocale {
  let saved: string | null = null;
  try { saved = window.localStorage.getItem(LOCALE_STORAGE_KEY); } catch { /* storage may be disabled */ }
  return resolveLocale(saved, navigator.languages);
}

export default function LocaleProvider({ children }: { children: ReactNode }) {
  const [requestedLocale] = useState<AppLocale>(initialLocale);
  const [locale, setActiveLocale] = useState<AppLocale>("en");
  const [ready, setReady] = useState(requestedLocale === "en");
  const requestId = useRef(0);

  const setLocale = useCallback(async (nextLocale: AppLocale): Promise<void> => {
    const currentRequest = requestId.current + 1;
    requestId.current = currentRequest;
    await loadLocaleCatalogues(nextLocale);
    if (requestId.current === currentRequest) setActiveLocale(nextLocale);
  }, []);

  useEffect(() => {
    if (requestedLocale === "en") return;
    void setLocale(requestedLocale)
      .catch(() => setActiveLocale("en"))
      .finally(() => setReady(true));
  }, [requestedLocale, setLocale]);

  useEffect(() => {
    if (!ready) return;
    try { window.localStorage.setItem(LOCALE_STORAGE_KEY, locale); } catch { /* storage may be disabled */ }
  }, [locale, ready]);

  const value = useMemo(() => ({
    locale,
    setLocale,
    t: (key: Parameters<typeof translate>[1], values?: Record<string, string | number>) =>
      translate(locale, key, values),
  }), [locale, setLocale]);

  if (!ready) return <div className="server-loading" role="status" aria-live="polite">BOOKPILE</div>;
  return <LocaleContext value={value}>{children}</LocaleContext>;
}
