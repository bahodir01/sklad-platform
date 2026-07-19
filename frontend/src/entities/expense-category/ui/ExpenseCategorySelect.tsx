import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import type { FieldAria } from "@/shared/ui/form-field";
import { useActiveExpenseCategories } from "../api/queries";

interface ExpenseCategorySelectProps {
  value: number | undefined;
  onChange: (value: number) => void;
  aria?: FieldAria;
  disabled?: boolean;
  /** Добавить пункт «Все» (фильтр ДДС). Значение сброса — undefined. */
  allowEmpty?: boolean;
}

const ALL = "__all__";

/**
 * Селект вида расхода денег (choice_model `GET /expense-categories?status=active`).
 * Используется в форме расхода (§5.4) и фильтре ДДС (§8.2). Значение — id.
 */
export function ExpenseCategorySelect({
  value,
  onChange,
  aria,
  disabled,
  allowEmpty,
}: ExpenseCategorySelectProps) {
  const { data, isLoading } = useActiveExpenseCategories();
  const items = data?.items ?? [];

  return (
    <Select
      value={value != null ? String(value) : allowEmpty ? ALL : undefined}
      onValueChange={(v) => {
        if (v === ALL) onChange(undefined as unknown as number);
        else onChange(Number(v));
      }}
      disabled={disabled || isLoading}
    >
      <SelectTrigger
        id={aria?.id}
        aria-invalid={aria?.["aria-invalid"]}
        aria-describedby={aria?.["aria-describedby"]}
        aria-required={aria?.["aria-required"]}
      >
        <SelectValue placeholder={isLoading ? "Загрузка…" : "Выберите вид расхода"} />
      </SelectTrigger>
      <SelectContent>
        {allowEmpty ? <SelectItem value={ALL}>Все виды</SelectItem> : null}
        {items.map((c) => (
          <SelectItem key={c.id} value={String(c.id)}>
            {c.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
