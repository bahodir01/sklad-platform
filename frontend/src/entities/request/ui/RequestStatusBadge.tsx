import { Badge } from "@/shared/ui/badge";
import type { RequestStatus } from "../model/types";

/**
 * Статус заявки цветным бейджем (ADR-2: статус принадлежит заявке). Цвет —
 * никогда не единственный сигнал (§11): рядом всегда текст. Статусная модель
 * фичи 13 (спека §2): draft → to_issue → issued → signed → submitted.
 */
const MAP: Record<
  RequestStatus,
  { label: string; variant: "muted" | "warning" | "info" | "success" | "secondary" }
> = {
  draft: { label: "Черновик", variant: "muted" },
  to_issue: { label: "К выдаче", variant: "warning" },
  issued: { label: "К подписи", variant: "info" },
  signed: { label: "Подписано", variant: "success" },
  submitted: { label: "Передано", variant: "secondary" },
};

export function RequestStatusBadge({ status }: { status: RequestStatus }) {
  const s = MAP[status];
  return <Badge variant={s.variant}>{s.label}</Badge>;
}

export const requestStatusLabel = (s: RequestStatus): string => MAP[s].label;
