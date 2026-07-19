import { Badge } from "@/shared/ui/badge";
import type { components } from "@/shared/api/schema";

type UserCategory = components["schemas"]["UserCategory"];

/**
 * Категория сотрудника бейджем (§6.3/§6.4). Цвет — никогда не единственный
 * сигнал (§11): в бейдже всегда текст «Учитель»/«Работник».
 *   teacher → info (синий) · worker → muted (серый).
 */
const CATEGORY: Record<UserCategory, { label: string; variant: "info" | "muted" }> = {
  teacher: { label: "Учитель", variant: "info" },
  worker: { label: "Работник", variant: "muted" },
};

export function CategoryBadge({ category }: { category: UserCategory | null | undefined }) {
  if (!category) return null;
  const c = CATEGORY[category];
  return <Badge variant={c.variant}>{c.label}</Badge>;
}

interface EmployeeCellProps {
  employeeId: number;
  /** Вычисляемое поле бэка (JOIN на users). Может быть null для старых записей. */
  fullName?: string | null;
  category?: UserCategory | null;
}

/**
 * Сотрудник в очереди «К печати» и реестре (§6.3/§6.4): реальное ФИО + бейдж
 * категории. Раньше рисовалось «Сотрудник #id» — теперь бэк отдаёт
 * employee_full_name / employee_category (JOIN на users, тот же приём, что в ДДС).
 * Если ФИО не пришло (например, историческая запись) — честный фолбэк на #id.
 */
export function EmployeeCell({ employeeId, fullName, category }: EmployeeCellProps) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-medium">{fullName?.trim() || `Сотрудник #${employeeId}`}</span>
      <CategoryBadge category={category} />
    </div>
  );
}
