import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

/**
 * Переключатель тем (дизайн-токены: светлая И тёмная). Тема — UI-предпочтение,
 * НЕ секрет: хранить её в localStorage допустимо (запрет §6 касается только
 * access-токена). Провайдер применяет к <html> и класс .dark (для Tailwind
 * dark:), и атрибут data-theme (паритет с макетом заказчика и CSS-фолбэком).
 */
export type ThemePref = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "sklad-theme";

interface ThemeContextValue {
  theme: ThemePref;
  resolved: ResolvedTheme;
  setTheme: (t: ThemePref) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemTheme(): ResolvedTheme {
  return typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function readStored(): ThemePref {
  if (typeof window === "undefined") return "system";
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === "light" || v === "dark" || v === "system" ? v : "system";
}

function apply(resolved: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.classList.toggle("light", resolved === "light");
  root.setAttribute("data-theme", resolved);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePref>(readStored);
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    theme === "system" ? systemTheme() : theme,
  );

  useEffect(() => {
    const next = theme === "system" ? systemTheme() : theme;
    setResolved(next);
    apply(next);
  }, [theme]);

  // При системном режиме — реагируем на смену системной темы.
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const next = systemTheme();
      setResolved(next);
      apply(next);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((t: ThemePref) => {
    window.localStorage.setItem(STORAGE_KEY, t);
    setThemeState(t);
  }, []);

  const toggle = useCallback(() => {
    setTheme(resolved === "dark" ? "light" : "dark");
  }, [resolved, setTheme]);

  return (
    <ThemeContext.Provider value={{ theme, resolved, setTheme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme должен использоваться внутри ThemeProvider");
  return ctx;
}
