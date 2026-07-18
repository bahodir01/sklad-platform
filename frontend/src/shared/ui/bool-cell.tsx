import { formatBool } from "@/shared/lib/format";

/** Булева колонка — «Да»/«Нет» текстом (§11). */
export function BoolCell({ value }: { value: boolean }) {
  return <span>{formatBool(value)}</span>;
}
