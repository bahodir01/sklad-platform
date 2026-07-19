import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { useActiveWarehouses, useIssuanceWarehouses } from "../api/queries";
import type { FieldAria } from "@/shared/ui/form-field";

interface WarehouseSelectProps {
  value: number | undefined;
  onChange: (value: number) => void;
  aria?: FieldAria;
  /** active — все активные (уведомление/перемещение); issuance — только склады
   *  списания (форма заявки, AP-12). */
  source: "active" | "issuance";
  excludeId?: number;
  placeholder?: string;
  disabled?: boolean;
}

/** Селект склада. Источник опций зависит от контекста (contract choice_model). */
export function WarehouseSelect({
  value,
  onChange,
  aria,
  source,
  excludeId,
  placeholder,
  disabled,
}: WarehouseSelectProps) {
  const active = useActiveWarehouses();
  const issuance = useIssuanceWarehouses();
  const query = source === "issuance" ? issuance : active;
  const items = (query.data?.items ?? []).filter((w) => w.id !== excludeId);

  return (
    <Select
      value={value != null ? String(value) : undefined}
      onValueChange={(v) => onChange(Number(v))}
      disabled={disabled || query.isLoading}
    >
      <SelectTrigger
        id={aria?.id}
        aria-invalid={aria?.["aria-invalid"]}
        aria-describedby={aria?.["aria-describedby"]}
        aria-required={aria?.["aria-required"]}
      >
        <SelectValue placeholder={query.isLoading ? "Загрузка…" : placeholder ?? "Выберите склад"} />
      </SelectTrigger>
      <SelectContent>
        {items.map((w) => (
          <SelectItem key={w.id} value={String(w.id)}>
            {w.code} — {w.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
