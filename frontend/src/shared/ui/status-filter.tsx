import { Label } from "./label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";

const ALL = "__all__";

interface StatusFilterProps {
  /** Текущее значение фильтра из URL (undefined = все). */
  value: string | undefined;
  onChange: (value: string | undefined) => void;
}

/**
 * Фильтр статуса active|archived (реализован в API — §1). Значение живёт в URL.
 */
export function StatusFilter({ value, onChange }: StatusFilterProps) {
  return (
    <div className="flex items-center gap-2">
      <Label htmlFor="filter-status" className="text-muted-foreground">
        Статус
      </Label>
      <Select
        value={value ?? ALL}
        onValueChange={(v) => onChange(v === ALL ? undefined : v)}
      >
        <SelectTrigger id="filter-status" className="w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Все</SelectItem>
          <SelectItem value="active">Активные</SelectItem>
          <SelectItem value="archived">В архиве</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}

interface BoolFilterProps {
  id: string;
  label: string;
  value: string | undefined;
  onChange: (value: string | undefined) => void;
  trueLabel?: string;
  falseLabel?: string;
}

/** Обобщённый булев фильтр (is_active у units, allows_issuance у warehouses). */
export function BoolFilter({
  id,
  label,
  value,
  onChange,
  trueLabel = "Да",
  falseLabel = "Нет",
}: BoolFilterProps) {
  return (
    <div className="flex items-center gap-2">
      <Label htmlFor={id} className="text-muted-foreground">
        {label}
      </Label>
      <Select value={value ?? ALL} onValueChange={(v) => onChange(v === ALL ? undefined : v)}>
        <SelectTrigger id={id} className="w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Все</SelectItem>
          <SelectItem value="true">{trueLabel}</SelectItem>
          <SelectItem value="false">{falseLabel}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
