import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import type { FieldAria } from "@/shared/ui/form-field";
import { useCashDesks } from "../api/queries";
import { CASH_DESK_LABEL } from "../model/types";

interface CashDeskSelectProps {
  value: number | undefined;
  onChange: (value: number) => void;
  aria?: FieldAria;
  disabled?: boolean;
}

/**
 * Селект кассы для прихода (admin, §7.2). Опции — ровно две seed-кассы
 * (teacher/worker) из GET /cash/desks; подпись — русское название типа кассы.
 * Только для прихода: у расхода сотрудника кассу определяет сервер (SV-6).
 */
export function CashDeskSelect({ value, onChange, aria, disabled }: CashDeskSelectProps) {
  const { data, isLoading } = useCashDesks();
  const desks = data ?? [];

  return (
    <Select
      value={value != null ? String(value) : undefined}
      onValueChange={(v) => onChange(Number(v))}
      disabled={disabled || isLoading}
    >
      <SelectTrigger
        id={aria?.id}
        aria-invalid={aria?.["aria-invalid"]}
        aria-describedby={aria?.["aria-describedby"]}
        aria-required={aria?.["aria-required"]}
      >
        <SelectValue placeholder={isLoading ? "Загрузка…" : "Выберите кассу"} />
      </SelectTrigger>
      <SelectContent>
        {desks.map((d) => (
          <SelectItem key={d.id} value={String(d.id)}>
            {CASH_DESK_LABEL[d.type]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
