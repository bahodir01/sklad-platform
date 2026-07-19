import type { ReactNode } from "react";
import { cn } from "@/shared/lib/utils";

interface KpiCardProps {
  label: string;
  value: ReactNode;
  meta?: string;
  /** Цвет точки-индикатора рядом с подписью. */
  dot?: "warning" | "success" | "accent" | "info";
  /** Акцентная карточка (мягкий бренд-фон). */
  accent?: boolean;
}

const DOT: Record<NonNullable<KpiCardProps["dot"]>, string> = {
  warning: "bg-warning",
  success: "bg-success",
  accent: "bg-primary",
  info: "bg-info",
};

/** KPI-карточка (макет «К печати»). */
export function KpiCard({ label, value, meta, dot, accent }: KpiCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border p-4 shadow-sm",
        accent ? "border-transparent bg-brand-soft" : "border-border bg-card",
      )}
    >
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        {dot ? <span className={cn("h-2 w-2 rounded-full", DOT[dot])} aria-hidden="true" /> : null}
        {label}
      </div>
      <div
        className={cn(
          "mt-2 text-3xl font-bold tabular-nums tracking-tight",
          accent && "text-brand-text",
        )}
      >
        {value}
      </div>
      {meta ? <div className="mt-1 text-xs text-muted-foreground">{meta}</div> : null}
    </div>
  );
}
