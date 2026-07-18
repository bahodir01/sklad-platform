import { Controller, type UseFormReturn } from "react-hook-form";
import { Input } from "@/shared/ui/input";
import { Checkbox } from "@/shared/ui/checkbox";
import { FormField } from "@/shared/ui/form-field";
import type { UnitFormValues } from "./unit.schema";

interface Props {
  form: UseFormReturn<UnitFormValues>;
  mode: "create" | "update";
}

/** Поля ЕИ (§9.4). is_active — только в правке (api.create=false). */
export function UnitFormFields({ form, mode }: Props) {
  const {
    register,
    control,
    formState: { errors },
  } = form;

  return (
    <div className="space-y-4">
      <FormField id="code" label="Код ЕИ" required error={errors.code?.message}>
        {(aria) => <Input {...aria} {...register("code")} maxLength={16} autoFocus />}
      </FormField>

      <FormField id="name" label="Наименование ЕИ" required error={errors.name?.message}>
        {(aria) => <Input {...aria} {...register("name")} maxLength={100} />}
      </FormField>

      {mode === "update" ? (
        <Controller
          control={control}
          name="is_active"
          render={({ field }) => (
            <FormField id="is_active" label="Активна" inline>
              {(aria) => (
                <Checkbox
                  id={aria.id}
                  checked={field.value}
                  onCheckedChange={(v) => field.onChange(v === true)}
                />
              )}
            </FormField>
          )}
        />
      ) : null}
    </div>
  );
}
