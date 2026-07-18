import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { useActiveUnits } from "../api/queries";
import type { FieldAria } from "@/shared/ui/form-field";

interface UnitSelectProps {
  value: number | undefined;
  onChange: (value: number) => void;
  aria: FieldAria;
  disabled?: boolean;
}

/**
 * Селект ЕИ для формы товара. Опции — только активные ЕИ (choice_model контракта
 * `GET /units?is_active=true`). Значение — unit_id (число).
 */
export function UnitSelect({ value, onChange, aria, disabled }: UnitSelectProps) {
  const { data, isLoading } = useActiveUnits();
  const units = data?.items ?? [];

  return (
    <Select
      value={value != null ? String(value) : undefined}
      onValueChange={(v) => onChange(Number(v))}
      disabled={disabled || isLoading}
    >
      <SelectTrigger id={aria.id} aria-invalid={aria["aria-invalid"]} aria-describedby={aria["aria-describedby"]} aria-required={aria["aria-required"]}>
        <SelectValue placeholder={isLoading ? "Загрузка…" : "Выберите единицу измерения"} />
      </SelectTrigger>
      <SelectContent>
        {units.map((u) => (
          <SelectItem key={u.id} value={String(u.id)}>
            {u.code} — {u.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
