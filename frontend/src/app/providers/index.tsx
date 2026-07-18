import type { ReactNode } from "react";
import { Toaster } from "@/shared/ui/sonner";
import { QueryProvider } from "./QueryProvider";
import { AuthBootstrap } from "./AuthBootstrap";
import { ThemeProvider } from "./ThemeProvider";

/**
 * Композиция провайдеров (§9.1). Toaster — вне роутера, переживает навигацию.
 * ThemeProvider снаружи, чтобы тема применялась и к лоадеру AuthBootstrap.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <QueryProvider>
        <AuthBootstrap>{children}</AuthBootstrap>
        <Toaster />
      </QueryProvider>
    </ThemeProvider>
  );
}
