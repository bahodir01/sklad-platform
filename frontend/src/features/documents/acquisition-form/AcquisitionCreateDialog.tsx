import { useEffect } from "react";
import { useForm, useFieldArray, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Skeleton } from "@/shared/ui/skeleton";
import { FormField } from "@/shared/ui/form-field";
import { WarehouseSelect } from "@/entities/warehouse/ui/WarehouseSelect";
import { useNotification } from "@/entities/notification/api/queries";
import { useProductLookup } from "@/entities/product/lib/use-product-lookup";
import { useCreateAcquisition, type AcquisitionCreate } from "@/entities/acquisition/api/mutations";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { todayIso, formatQty } from "@/shared/lib/format";
import { acquisitionSchema, type AcquisitionFormValues } from "./acquisition.schema";

interface AcquisitionCreateDialogProps {
  /** Уведомление-основание. null — диалог закрыт. */
  notificationId: number | null;
  onClose: () => void;
}

/**
 * Проведение приобретения на основании уведомления (admin, §6.2). Строки
 * прогружаются из остатка к приобретению (qty_remaining) выбранного уведомления;
 * количество по умолчанию = остаток, цена — необязательна. Перезакуп (§4.2)
 * отклоняет сервер (SV-1) — его сообщение выводится тостером.
 */
export function AcquisitionCreateDialog({ notificationId, onClose }: AcquisitionCreateDialogProps) {
  const detail = useNotification(notificationId);
  const products = useProductLookup();
  const create = useCreateAcquisition();

  const form = useForm<AcquisitionFormValues>({
    resolver: zodResolver(acquisitionSchema),
    defaultValues: { date: todayIso(), warehouse_id: undefined, supplier: "", items: [] },
  });
  const {
    control,
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = form;
  const { fields, remove } = useFieldArray({ control, name: "items" });

  // Прогружаем строки из остатка к приобретению, когда деталь загрузилась.
  useEffect(() => {
    if (!detail.data) return;
    const open = detail.data.items.filter((it) => Number(it.qty_remaining ?? 0) > 0);
    reset({
      date: todayIso(),
      warehouse_id: detail.data.warehouse_id,
      supplier: "",
      items: open.map((it) => ({
        product_id: it.product_id,
        qty: Number(it.qty_remaining ?? 0),
        price: undefined,
      })) as never,
    });
  }, [detail.data, reset]);

  function onSubmit(values: AcquisitionFormValues) {
    if (notificationId == null) return;
    const payload: AcquisitionCreate = {
      date: values.date,
      notification_id: notificationId,
      warehouse_id: values.warehouse_id,
      supplier: values.supplier?.trim() ? values.supplier.trim() : null,
      items: values.items.map((it) => ({
        product_id: it.product_id,
        qty: it.qty,
        price: it.price ?? null,
      })),
    };
    create.mutate(payload, {
      onSuccess: (a) => {
        toast.success(`Приобретение ${a.number} проведено`);
        onClose();
      },
      onError: (e) => applyApiError(e, form.setError),
    });
  }

  const remaining = detail.data?.items.filter((it) => Number(it.qty_remaining ?? 0) > 0) ?? [];

  return (
    <Dialog open={notificationId != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {detail.data ? `Приобретение по ${detail.data.number}` : "Приобретение"}
          </DialogTitle>
        </DialogHeader>

        {detail.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : detail.isError || !detail.data ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Не удалось загрузить уведомление.
          </p>
        ) : remaining.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            По этому уведомлению всё приобретено — остатка к приобретению нет.
          </p>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField id="date" label="Дата" required error={errors.date?.message}>
                {(aria) => <Input {...aria} type="date" {...register("date")} />}
              </FormField>

              <Controller
                control={control}
                name="warehouse_id"
                render={({ field }) => (
                  <FormField
                    id="warehouse_id"
                    label="Склад поступления"
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
            </div>

            <FormField id="supplier" label="Поставщик" error={errors.supplier?.message}>
              {(aria) => <Input {...aria} {...register("supplier")} maxLength={255} placeholder="Необязательно" />}
            </FormField>

            <div className="space-y-2">
              <span className="text-sm font-medium">Позиции к приобретению</span>
              {fields.map((f, i) => {
                const src = remaining[i];
                return (
                  <div key={f.id} className="flex items-start gap-2">
                    <div className="flex-1 pt-1">
                      <p className="text-xs text-muted-foreground">Товар</p>
                      <p className="text-sm">
                        {src ? products.name(src.product_id) : ""}
                        <span className="ml-1 text-xs text-muted-foreground">
                          (ост. {formatQty(src?.qty_remaining)})
                        </span>
                      </p>
                    </div>
                    <div className="w-28">
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
                    <div className="w-28">
                      <FormField id={`items.${i}.price`} label="Цена, UZS" error={errors.items?.[i]?.price?.message}>
                        {(aria) => (
                          <Input {...aria} type="number" step="any" min="0" className="text-right" {...register(`items.${i}.price`)} />
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
                      aria-label="Убрать позицию"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                );
              })}
              {errors.items?.message ? (
                <p className="text-sm font-medium text-destructive">{errors.items.message}</p>
              ) : null}
            </div>

            <DialogFooter>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Проведение…" : "Провести приобретение"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
