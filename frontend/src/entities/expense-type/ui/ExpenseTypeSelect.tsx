import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import type { FieldAria } from "@/shared/ui/form-field";
import { useActiveExpenseTypes } from "../api/queries";

interface ExpenseTypeSelectProps {
  value: number | undefined;
  onChange: (value: number) => void;
  aria?: FieldAria;
  disabled?: boolean;
  /**
   * true — показать только типы с requires_employee=false (Порча/Брак): прямое
   * списание §4.4 запрещает «Выдача»-типы (requires_employee=true), они проводятся
   * статусной машиной заявки. Фильтр по справочнику — на клиенте (API его не даёт).
   */
  requiresEmployeeFalseOnly?: boolean;
}

/**
 * Селект типа расхода товара. Для прямого списания порча/брак опции
 * ограничиваются requires_employee=false — «Выдачу» выбрать физически нельзя.
 */
export function ExpenseTypeSelect({
  value,
  onChange,
  aria,
  disabled,
  requiresEmployeeFalseOnly,
}: ExpenseTypeSelectProps) {
  const { data, isLoading } = useActiveExpenseTypes();
  const items = (data?.items ?? []).filter(
    (t) => !requiresEmployeeFalseOnly || t.requires_employee === false,
  );

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
        <SelectValue placeholder={isLoading ? "Загрузка…" : "Выберите тип расхода"} />
      </SelectTrigger>
      <SelectContent>
        {items.length === 0 && !isLoading ? (
          <div className="px-2 py-1.5 text-sm text-muted-foreground">
            Нет подходящих типов (Порча/Брак)
          </div>
        ) : null}
        {items.map((t) => (
          <SelectItem key={t.id} value={String(t.id)}>
            {t.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
