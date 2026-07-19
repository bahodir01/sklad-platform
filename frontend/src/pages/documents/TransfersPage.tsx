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
import { useCreateTransfer, type TransferCreate } from "@/entities/transfer/api/mutations";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { todayIso } from "@/shared/lib/format";
import { transferSchema, type TransferFormValues } from "@/features/documents/transfer-form/transfer.schema";

/**
 * Перемещение между складами (М2, admin, §6.3). Списка перемещений в API нет —
 * экран это форма проведения: источник → получатель + строки. При успехе
 * товар переносится (две записи ledger, SV-3), остатки/движения обновляются.
 */
export function TransfersPage() {
  const create = useCreateTransfer();

  const form = useForm<TransferFormValues>({
    resolver: zodResolver(transferSchema),
    defaultValues: {
      date: todayIso(),
      from_warehouse_id: undefined,
      to_warehouse_id: undefined,
      items: [{ product_id: undefined, qty: undefined }] as never,
    },
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
  const fromId = watch("from_warehouse_id");
  const toId = watch("to_warehouse_id");

  function onSubmit(values: TransferFormValues) {
    const payload: TransferCreate = {
      date: values.date,
      from_warehouse_id: values.from_warehouse_id,
      to_warehouse_id: values.to_warehouse_id,
      items: values.items.map((it) => ({ product_id: it.product_id, qty: it.qty })),
    };
    create.mutate(payload, {
      onSuccess: (t) => {
        toast.success(`Перемещение ${t.number} проведено`);
        reset({
          date: todayIso(),
          from_warehouse_id: undefined,
          to_warehouse_id: undefined,
          items: [{ product_id: undefined, qty: undefined }] as never,
        });
      },
      onError: (e) => applyApiError(e, form.setError),
    });
  }

  return (
    <section className="max-w-3xl">
      <PageHeader
        breadcrumb="Документы › Перемещения"
        title="Перемещение между складами"
        subtitle="Перенос товара со склада-источника на склад-получатель"
      />

      <Card className="p-5">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <FormField id="date" label="Дата" required error={errors.date?.message}>
              {(aria) => <Input {...aria} type="date" {...register("date")} />}
            </FormField>

            <Controller
              control={control}
              name="from_warehouse_id"
              render={({ field }) => (
                <FormField
                  id="from_warehouse_id"
                  label="Склад-источник"
                  required
                  error={errors.from_warehouse_id?.message}
                >
                  {(aria) => (
                    <WarehouseSelect
                      source="active"
                      value={field.value}
                      onChange={field.onChange}
                      aria={aria}
                      excludeId={toId}
                    />
                  )}
                </FormField>
              )}
            />

            <Controller
              control={control}
              name="to_warehouse_id"
              render={({ field }) => (
                <FormField
                  id="to_warehouse_id"
                  label="Склад-получатель"
                  required
                  error={errors.to_warehouse_id?.message}
                >
                  {(aria) => (
                    <WarehouseSelect
                      source="active"
                      value={field.value}
                      onChange={field.onChange}
                      aria={aria}
                      excludeId={fromId}
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
                onClick={() => append({ product_id: undefined, qty: undefined } as never)}
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
                  <div className="w-32">
                    <FormField
                      id={`items.${i}.qty`}
                      label="Кол-во"
                      required
                      error={errors.items?.[i]?.qty?.message}
                    >
                      {(aria) => (
                        <Input {...aria} type="number" step="any" min="0" className="text-right" {...register(`items.${i}.qty`)} />
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
              {create.isPending ? "Проведение…" : "Провести перемещение"}
            </Button>
          </div>
        </form>
      </Card>
    </section>
  );
}
