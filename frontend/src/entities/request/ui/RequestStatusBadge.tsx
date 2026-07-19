import { Badge } from "@/shared/ui/badge";
import type { RequestStatus } from "../model/types";

/**
 * Статус заявки цветным бейджем (ADR-2: статус принадлежит заявке). Цвет —
 * никогда не единственный сигнал (§11): рядом всегда текст.
 *   draft → серый · to_print → жёлтый · printed → синий · issued → зелёный.
 */
const MAP: Record<RequestStatus, { label: string; variant: "muted" | "warning" | "info" | "success" }> = {
  draft: { label: "Черновик", variant: "muted" },
  to_print: { label: "Требует печати", variant: "warning" },
  printed: { label: "Напечатан", variant: "info" },
  issued: { label: "Выдано", variant: "success" },
};

export function RequestStatusBadge({ status }: { status: RequestStatus }) {
  const s = MAP[status];
  return <Badge variant={s.variant}>{s.label}</Badge>;
}

export const requestStatusLabel = (s: RequestStatus): string => MAP[s].label;
