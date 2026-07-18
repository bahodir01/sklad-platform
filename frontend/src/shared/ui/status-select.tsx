import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";
import type { CatalogStatus } from "@/shared/api/schema";
import type { FieldAria } from "./form-field";

interface StatusSelectProps {
  value: CatalogStatus;
  onChange: (value: CatalogStatus) => void;
  aria: FieldAria;
}

/** Селект статуса active|archived для форм правки (§8). */
export function StatusSelect({ value, onChange, aria }: StatusSelectProps) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as CatalogStatus)}>
      <SelectTrigger
        id={aria.id}
        aria-invalid={aria["aria-invalid"]}
        aria-describedby={aria["aria-describedby"]}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="active">Активен</SelectItem>
        <SelectItem value="archived">В архиве</SelectItem>
      </SelectContent>
    </Select>
  );
}
