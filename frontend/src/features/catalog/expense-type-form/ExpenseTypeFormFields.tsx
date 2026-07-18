import { Controller, type UseFormReturn } from "react-hook-form";
import { Input } from "@/shared/ui/input";
import { Checkbox } from "@/shared/ui/checkbox";
import { FormField } from "@/shared/ui/form-field";
import { StatusSelect } from "@/shared/ui/status-select";
import type { ExpenseTypeFormValues } from "./expense-type.schema";

interface Props {
  form: UseFormReturn<ExpenseTypeFormValues>;
  mode: "create" | "update";
}

/**
 * Поля типа расхода товара (§9.4). requires_employee — обычный чекбокс с
 * пояснением; блокировка «при наличии проводок» на этапе 1 нереализуема (К-A),
 * запрет обеспечивает бэкенд. status — только в правке.
 */
export function ExpenseTypeFormFields({ form, mode }: Props) {
  const {
    register,
    control,
    formState: { errors },
  } = form;

  return (
    <div className="space-y-4">
      <FormField id="name" label="Тип расхода товара" required error={errors.name?.message}>
        {(aria) => <Input {...aria} {...register("name")} maxLength={100} autoFocus />}
      </FormField>

      <Controller
        control={control}
        name="requires_employee"
        render={({ field }) => (
          <FormField
            id="requires_employee"
            label="Требует сотрудника"
            inline
            description="Отметьте для «Выдачи сотруднику». Для «Порчи»/«Брака» оставьте пустым."
          >
            {(aria) => (
              <Checkbox
                id={aria.id}
                aria-describedby={aria["aria-describedby"]}
                checked={field.value}
                onCheckedChange={(v) => field.onChange(v === true)}
              />
            )}
          </FormField>
        )}
      />

      {mode === "update" ? (
        <Controller
          control={control}
          name="status"
          render={({ field }) => (
            <FormField id="status" label="Статус" error={errors.status?.message}>
              {(aria) => (
                <StatusSelect value={field.value} onChange={field.onChange} aria={aria} />
              )}
            </FormField>
          )}
        />
      ) : null}
    </div>
  );
}
