import { FormField } from "@/shared/ui/form-field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { roleLabel } from "@/shared/config/roles";
import { categoryLabel } from "@/entities/user/lib/category-label";
import type { UserCategory, UserRole } from "@/shared/api/model-types";

const ROLE_OPTIONS: UserRole[] = ["admin", "teacher", "worker"];
const CATEGORY_OPTIONS: UserCategory[] = ["teacher", "worker"];

interface Props {
  role: UserRole;
  category: UserCategory | undefined;
  onRoleChange: (role: UserRole) => void;
  onCategoryChange: (category: UserCategory) => void;
  roleError?: string;
  categoryError?: string;
}

/**
 * Роль + категория (§14, INV-9): category отображается только для role != admin
 * и обнуляется у admin (см. toUserCreate/toUserUpdate) — общий кусок между формой
 * создания и правки, чтобы правило «скрыть/обнулить для admin» не разошлось.
 */
export function RoleCategoryFields({
  role,
  category,
  onRoleChange,
  onCategoryChange,
  roleError,
  categoryError,
}: Props) {
  return (
    <>
      <FormField id="role" label="Роль" required error={roleError}>
        {(aria) => (
          <Select value={role} onValueChange={(v) => onRoleChange(v as UserRole)}>
            <SelectTrigger
              id={aria.id}
              aria-invalid={aria["aria-invalid"]}
              aria-describedby={aria["aria-describedby"]}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLE_OPTIONS.map((r) => (
                <SelectItem key={r} value={r}>
                  {roleLabel(r)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </FormField>

      {role !== "admin" ? (
        <FormField id="category" label="Категория (касса)" required error={categoryError}>
          {(aria) => (
            <Select value={category ?? undefined} onValueChange={(v) => onCategoryChange(v as UserCategory)}>
              <SelectTrigger
                id={aria.id}
                aria-invalid={aria["aria-invalid"]}
                aria-describedby={aria["aria-describedby"]}
              >
                <SelectValue placeholder="Выберите категорию" />
              </SelectTrigger>
              <SelectContent>
                {CATEGORY_OPTIONS.map((c) => (
                  <SelectItem key={c} value={c}>
                    {categoryLabel(c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </FormField>
      ) : null}
    </>
  );
}
