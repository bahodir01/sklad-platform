import { Controller, type UseFormReturn } from "react-hook-form";
import { Input } from "@/shared/ui/input";
import { FormField } from "@/shared/ui/form-field";
import { StatusSelect } from "@/shared/ui/status-select";
import type { ExpenseCategoryFormValues } from "./expense-category.schema";

interface Props {
  form: UseFormReturn<ExpenseCategoryFormValues>;
  mode: "create" | "update";
}

/** Поля вида расхода денег (§9.4). status — только в правке (api.create=false). */
export function ExpenseCategoryFormFields({ form, mode }: Props) {
  const {
    register,
    control,
    formState: { errors },
  } = form;

  return (
    <div className="space-y-4">
      <FormField id="name" label="Вид расхода денег" required error={errors.name?.message}>
        {(aria) => <Input {...aria} {...register("name")} maxLength={100} autoFocus />}
      </FormField>

      {mode === "update" ? (
        <Controller
          control={control}
          name="status"
          render={({ field }) => (
            <FormField id="status" label="Статус" error={errors.status?.message}>
              {(aria) => <StatusSelect value={field.value} onChange={field.onChange} aria={aria} />}
            </FormField>
          )}
        />
      ) : null}
    </div>
  );
}
