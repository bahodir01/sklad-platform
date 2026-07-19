import { useForm, useFieldArray, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { PageHeader } from "@/shared/ui/page-header";
import { Card } from "@/shared/ui/card";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { FormField } from "@/shared/ui/form-field";
import { WarehouseSelect } from "@/entities/warehouse/ui/WarehouseSelect";
import { ProductSelect } from "@/entities/product/ui/ProductSelect";
import { ExpenseTypeSelect } from "@/entities/expense-type/ui/ExpenseTypeSelect";
import { useCreateWriteoff } from "@/entities/writeoff/api/mutations";
import type { WriteoffCreate } from "@/entities/writeoff/model/types";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { todayIso } from "@/shared/lib/format";
import { writeoffSchema, type WriteoffFormValues } from "@/features/documents/writeoff-form/writeoff.schema";

const EMPTY: WriteoffFormValues = {
  date: todayIso(),
  warehouse_id: undefined as never,
  expense_type_id: undefined as never,
  items: [{ product_id: undefined as never, qty: undefined as never, reason: "" }],
};

/**
 * Прямое списание товара порча/брак (М2/ЭТАП 4, admin, §4.4). Списка списаний в
 * API нет — экран это форма проведения: склад + тип расхода (только
 * requires_employee=false, «Выдачу» выбрать нельзя) + строки товар/кол-во/причина.
 * При успехе товар списывается немедленно (ledger.post(−qty)), остатки/движения
 * обновляются. Недостаток остатка (InsufficientStock) и «Выдача»-тип отклоняет
 * сервер — сообщение выводится тостером через applyApiError.
 */
export function WriteoffsPage() {
  const create = useCreateWriteoff();

  const form = useForm<WriteoffFormValues>({
    resolver: zodResolver(writeoffSchema),
    defaultValues: EMPTY,
  });
  const {
    control,
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = form;
  const { fields, append, remove } = useFieldArray({ control, name: "items" });
  const items = watch("items");

  function onSubmit(values: WriteoffFormValues) {
    const payload: WriteoffCreate = {
      date: values.date,
      warehouse_id: values.warehouse_id,
      expense_type_id: values.expense_type_id,
      // employee_id НЕ отправляется: при порче/браке он обязан быть NULL (INV-4).
      items: values.items.map((it) => ({
        product_id: it.product_id,
        qty: it.qty,
        reason: it.reason?.trim() ? it.reason.trim() : null,
      })),
    };
    create.mutate(payload, {
      onSuccess: (w) => {
        toast.success(`Списание ${w.number} проведено`);
        reset(EMPTY);
      },
      onError: (e) => applyApiError(e, form.setError),
    });
  }

  return (
    <section className="max-w-3xl">
      <PageHeader
        breadcrumb="Документы › Списание (порча/брак)"
        title="Списание товара"
        subtitle="Прямое списание порчи или брака со склада без заявки сотрудника"
      />

      <Card className="p-5">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <FormField id="date" label="Дата" required error={errors.date?.message}>
              {(aria) => <Input {...aria} type="date" {...register("date")} />}
            </FormField>

            <Controller
              control={control}
              name="warehouse_id"
              render={({ field }) => (
                <FormField
                  id="warehouse_id"
                  label="Склад"
                  required
                  error={errors.warehouse_id?.message}
                >
                  {(aria) => (
                    <WarehouseSelect
                      source="active"
                      value={field.value}
                      onChange={field.onChange}
                      aria={aria}
                    />
                  )}
                </FormField>
              )}
            />

            <Controller
              control={control}
              name="expense_type_id"
              render={({ field }) => (
                <FormField
                  id="expense_type_id"
                  label="Тип расхода"
                  required
                  error={errors.expense_type_id?.message}
                  description="Только Порча/Брак (без сотрудника). «Выдача» проводится через заявку."
                >
                  {(aria) => (
                    <ExpenseTypeSelect
                      value={field.value}
                      onChange={field.onChange}
                      aria={aria}
                      requiresEmployeeFalseOnly
                    />
                  )}
                </FormField>
              )}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Позиции</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() =>
                  append({ product_id: undefined, qty: undefined, reason: "" } as never)
                }
              >
                <Plus className="h-4 w-4" />
                Добавить
              </Button>
            </div>

            {errors.items?.message ? (
              <p className="text-sm font-medium text-destructive">{errors.items.message}</p>
            ) : null}

            {fields.map((f, i) => {
              const excludeIds = (items ?? [])
                .map((it) => it?.product_id)
                .filter((id, idx): id is number => id != null && idx !== i);
              return (
                <div key={f.id} className="flex items-start gap-2">
                  <div className="flex-1">
                    <Controller
                      control={control}
                      name={`items.${i}.product_id`}
                      render={({ field }) => (
                        <FormField
                          id={`items.${i}.product_id`}
                          label="Товар"
                          required
                          error={errors.items?.[i]?.product_id?.message}
                        >
                          {(aria) => (
                            <ProductSelect
                              value={field.value}
                              onChange={field.onChange}
                              aria={aria}
                              excludeIds={excludeIds}
                            />
                          )}
                        </FormField>
                      )}
                    />
                  </div>
                  <div className="w-28">
                    <FormField
                      id={`items.${i}.qty`}
                      label="Кол-во"
                      required
                      error={errors.items?.[i]?.qty?.message}
                    >
                      {(aria) => (
                        <Input
                          {...aria}
                          type="number"
                          step="any"
                          min="0"
                          className="text-right"
                          {...register(`items.${i}.qty`)}
                        />
                      )}
                    </FormField>
                  </div>
                  <div className="flex-1">
                    <FormField
                      id={`items.${i}.reason`}
                      label="Причина"
                      error={errors.items?.[i]?.reason?.message}
                    >
                      {(aria) => (
                        <Input
                          {...aria}
                          {...register(`items.${i}.reason`)}
                          maxLength={500}
                          placeholder="Необязательно"
                        />
                      )}
                    </FormField>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="mt-6"
                    onClick={() => remove(i)}
                    disabled={fields.length <= 1}
                    aria-label="Удалить позицию"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              );
            })}
          </div>

          <div className="flex justify-end">
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Списание…" : "Списать товар"}
            </Button>
          </div>
        </form>
      </Card>
    </section>
  );
}
