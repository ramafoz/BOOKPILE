import { type ReactNode, useEffect, useMemo, useState } from "react";
import { LocaleContext } from "./LocaleContext";
import {
  type AppLocale, LOCALE_STORAGE_KEY, resolveLocale, translate,
} from "./locale";

function initialLocale(): AppLocale {
  let saved: string | null = null;
  try { saved = window.localStorage.getItem(LOCALE_STORAGE_KEY); } catch { /* storage may be disabled */ }
  return resolveLocale(saved, navigator.languages);
}

export default function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<AppLocale>(initialLocale);

  useEffect(() => {
    try { window.localStorage.setItem(LOCALE_STORAGE_KEY, locale); } catch { /* storage may be disabled */ }
  }, [locale]);

  const value = useMemo(() => ({
    locale,
    setLocale,
    t: (key: Parameters<typeof translate>[1], values?: Record<string, string | number>) =>
      translate(locale, key, values),
  }), [locale]);

  return <LocaleContext value={value}>{children}</LocaleContext>;
}
