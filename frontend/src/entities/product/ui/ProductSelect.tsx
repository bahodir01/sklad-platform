import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { useActiveProducts } from "../api/queries";
import type { FieldAria } from "@/shared/ui/form-field";

interface ProductSelectProps {
  value: number | undefined;
  onChange: (value: number) => void;
  aria?: FieldAria;
  /** Уже выбранные id (в других строках) — скрываем, чтобы не задваивать. */
  excludeIds?: number[];
  disabled?: boolean;
}

/**
 * Селект товара для строк документов/заявок. Опции — активные товары
 * (choice_model контракта `GET /products?status=active`). Значение — product_id.
 */
export function ProductSelect({ value, onChange, aria, excludeIds = [], disabled }: ProductSelectProps) {
  const { data, isLoading } = useActiveProducts();
  const products = (data?.items ?? []).filter(
    (p) => p.id === value || !excludeIds.includes(p.id),
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
        <SelectValue placeholder={isLoading ? "Загрузка…" : "Выберите товар"} />
      </SelectTrigger>
      <SelectContent>
        {products.map((p) => (
          <SelectItem key={p.id} value={String(p.id)}>
            {p.name}
            {p.sku ? ` · ${p.sku}` : ""}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
