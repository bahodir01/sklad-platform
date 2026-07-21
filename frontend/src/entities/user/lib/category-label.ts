import type { UserCategory } from "@/shared/api/model-types";

/** category NULL ⟺ role=admin (INV-9) — «—» в таблице/деталях для админа. */
const CATEGORY_LABELS: Record<UserCategory, string> = {
  teacher: "Учитель",
  worker: "Работник",
};

export function categoryLabel(category: UserCategory | null | undefined): string {
  if (!category) return "—";
  return CATEGORY_LABELS[category] ?? category;
}
