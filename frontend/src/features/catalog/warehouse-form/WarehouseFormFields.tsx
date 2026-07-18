import { Controller, type UseFormReturn } from "react-hook-form";
import { Input } from "@/shared/ui/input";
import { Checkbox } from "@/shared/ui/checkbox";
import { FormField } from "@/shared/ui/form-field";
import { StatusSelect } from "@/shared/ui/status-select";
import type { WarehouseFormValues } from "./warehouse.schema";

interface Props {
  form: UseFormReturn<WarehouseFormValues>;
  mode: "create" | "update";
}

/**
 * Поля формы склада (§9.4). Общая разметка; состав по mode: status — только в
 * правке (api.create=false). allows_issuance «Склад списания» — с поясняющим
 * текстом (SV-9), Radix Checkbox → id/htmlFor и aria-describedby явные (§11).
 */
export function WarehouseFormFields({ form, mode }: Props) {
  const {
    register,
    control,
    formState: { errors },
  } = form;

  return (
    <div className="space-y-4">
      <FormField id="code" label="Код склада" required error={errors.code?.message}>
        {(aria) => <Input {...aria} {...register("code")} maxLength={32} autoFocus />}
      </FormField>

      <FormField id="name" label="Наименование склада" required error={errors.name?.message}>
        {(aria) => <Input {...aria} {...register("name")} maxLength={255} />}
      </FormField>

      <FormField id="address" label="Адрес" error={errors.address?.message}>
        {(aria) => <Input {...aria} {...register("address")} maxLength={500} />}
      </FormField>

      <Controller
        control={control}
        name="allows_issuance"
        render={({ field }) => (
          <FormField
            id="allows_issuance"
            label="Склад списания"
            inline
            description="Сотрудник может подать заявку только со склада с этим признаком. Отмеченных складов может быть несколько."
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
