import { Badge } from "@/shared/ui/badge";
import type { NotificationStatus } from "../model/types";

/**
 * Статус уведомления цветным бейджем (§4). Автозакрытие при остатке 0 (SV-7).
 *   draft → серый · in_progress → синий · closed → зелёный.
 * Цвет не единственный сигнал — рядом текст (§11).
 */
const MAP: Record<NotificationStatus, { label: string; variant: "muted" | "info" | "success" }> = {
  draft: { label: "Черновик", variant: "muted" },
  in_progress: { label: "В работе", variant: "info" },
  closed: { label: "Закрыто", variant: "success" },
};

export function NotificationStatusBadge({ status }: { status: NotificationStatus }) {
  const s = MAP[status];
  return <Badge variant={s.variant}>{s.label}</Badge>;
}

export const notificationStatusLabel = (s: NotificationStatus): string => MAP[s].label;
