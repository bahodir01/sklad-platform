import { Badge } from "./badge";
import type { CatalogStatus } from "@/shared/api/schema";

/**
 * Статус active|archived текстом + цветом (§11: цвет никогда не единственный
 * сигнал — разница читается в ч/б). Один компонент на все справочники со
 * status, чтобы бейдж не расходился между экранами.
 */
export function CatalogStatusBadge({ status }: { status: CatalogStatus }) {
  // Токены status.catalog: active=success, archived=muted.
  return (
    <Badge variant={status === "active" ? "success" : "muted"}>
      {status === "active" ? "Активен" : "В архиве"}
    </Badge>
  );
}

/** Аналог для units, у которых архивация выражена boolean is_active (К-D). */
export function ActiveBadge({ isActive }: { isActive: boolean }) {
  return (
    <Badge variant={isActive ? "success" : "muted"}>
      {isActive ? "Активна" : "В архиве"}
    </Badge>
  );
}
