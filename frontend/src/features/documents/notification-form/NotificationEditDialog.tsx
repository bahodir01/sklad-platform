import { useEffect, useMemo } from "react";
import { useForm, useFieldArray, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Plus, Trash2, Lock } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Textarea } from "@/shared/ui/textarea";
import { Skeleton } from "@/shared/ui/skeleton";
import { FormField } from "@/shared/ui/form-field";
import { WarehouseSelect } from "@/entities/warehouse/ui/WarehouseSelect";
import { ProductSelect } from "@/entities/product/ui/ProductSelect";
import { useNotification } from "@/entities/notification/api/queries";
import { useUpdateNotification } from "@/entities/notification/api/mutations";
import type { NotificationUpdate } from "@/entities/notification/model/types";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { formatQty } from "@/shared/lib/format";
import { notificationSchema, type NotificationFormValues } from "./notification.schema";

interface NotificationEditDialogProps {
  id: number | null;
  onClose: () => void;
}

/**
 * Редактирование уведомления (PATCH /notifications/{id}, SV-10 / ОВ-11).
 *
 * Гейтинг — UX-слой (сервер проверяет всё равно):
 *   • Черновик  — полная форма: склад, дата, тексты, строки (add/remove, менять
 *                 товар и количество).
 *   • В работе  — только аддитивно: добавлять строки, увеличивать qty, править
 *                 тексты. Склад и дата — disabled. Строки с приобретениями
 *                 (qty_purchased > 0): товар не меняется, удаление запрещено,
 *                 qty нельзя опустить ниже приобретённого (min = приобретено).
 *   • Закрыт    — редактирование недоступно (диалог не открывается).
 *
 * Ошибку сервера (напр. «нельзя ниже купленного») показываем тостером.
 */
export function NotificationEditDialog({ id, onClose }: NotificationEditDialogProps) {
  const { data, isLoading, isError } = useNotification(id);
  const update = useUpdateNotification();

  const form = useForm<NotificationFormValues>({
    resolver: zodResolver(notificationSchema),
    defaultValues: {
      date: "",
      warehouse_id: undefined,
      division_name: "",
      body_text: "",
      comment: "",
      items: [],
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

  const status = data?.status;
  const isDraft = status === "draft";
  const isInProgress = status === "in_progress";

  /** Приобретено по каждому товару (по product_id) — источник гейтинга строк. */
  const purchasedByProduct = useMemo(() => {
    const map = new Map<number, number>();
    for (const it of data?.items ?? []) {
      map.set(it.product_id, Number(it.qty_purchased ?? 0) || 0);
    }
    return map;
  }, [data]);

  // Заполняем форму текущим состоянием уведомления при открытии/смене id.
  useEffect(() => {
    if (!data) return;
    reset({
      date: data.date,
      warehouse_id: data.warehouse_id,
      division_name: data.division_name,
      body_text: data.body_text,
      comment: data.comment ?? "",
      items: data.items.map((it) => ({
        product_id: it.product_id,
        qty_requested: Number(it.qty_requested),
      })),
    });
  }, [data, reset]);

  function onSubmit(values: NotificationFormValues) {
    if (id == null || !status) return;

    const mappedItems = values.items.map((it) => ({
      product_id: it.product_id,
      qty_requested: it.qty_requested,
    }));

    // Черновик — можно всё; в работе — только тексты + аддитивные правки строк
    // (склад/дата не шлём, они не редактируются и disabled).
    const payload: NotificationUpdate = isDraft
      ? {
          date: values.date,
          warehouse_id: values.warehouse_id,
          body_text: values.body_text,
          division_name: values.division_name,
          comment: values.comment?.trim() ? values.comment.trim() : null,
          items: mappedItems,
        }
      : {
          body_text: values.body_text,
          division_name: values.division_name,
          comment: values.comment?.trim() ? values.comment.trim() : null,
          items: mappedItems,
        };

    update.mutate(
      { id, body: payload },
      {
        onSuccess: (n) => {
          toast.success(`Уведомление ${n.number} сохранено`);
          onClose();
        },
        onError: (e) => applyApiError(e, form.setError),
      },
    );
  }

  const canEdit = isDraft || isInProgress;

  return (
    <Dialog open={id != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{data ? `Редактирование ${data.number}` : "Редактирование уведомления"}</DialogTitle>
          {isInProgress ? (
            <DialogDescription>
              Уведомление в работе: можно добавлять позиции, увеличивать количество и править тексты.
              Склад, дату, а также строки с приобретениями изменить нельзя.
            </DialogDescription>
          ) : null}
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : isError || !data ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Не удалось загрузить уведомление.
          </p>
        ) : !canEdit ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Закрытое уведомление редактировать нельзя.
          </p>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField
                id="date"
                label="Дата"
                required
                error={errors.date?.message}
                description={isInProgress ? "Нельзя изменить у уведомления в работе." : undefined}
              >
                {(aria) => <Input {...aria} type="date" {...register("date")} disabled={isInProgress} />}
              </FormField>

              <Controller
                control={control}
                name="warehouse_id"
                render={({ field }) => (
                  <FormField
                    id="warehouse_id"
                    label="Склад назначения"
                    required
                    error={errors.warehouse_id?.message}
                    description={isInProgress ? "Нельзя изменить у уведомления в работе." : undefined}
                  >
                    {(aria) => (
                      <WarehouseSelect
                        source="active"
                        value={field.value}
                        onChange={field.onChange}
                        aria={aria}
                        placeholder="Склад поступления"
                        disabled={isInProgress}
                      />
                    )}
                  </FormField>
                )}
              />
            </div>

            <FormField
              id="division_name"
              label="Наименование подразделения"
              required
              error={errors.division_name?.message}
            >
              {(aria) => <Input {...aria} {...register("division_name")} maxLength={255} />}
            </FormField>

            <FormField
              id="body_text"
              label="Текст обращения"
              required
              error={errors.body_text?.message}
              description="Абзац-обращение бланка BILDIRISHNOMA (Sizdan… so‘rayman)."
            >
              {(aria) => <Textarea {...aria} {...register("body_text")} rows={3} />}
            </FormField>

            <FormField
              id="comment"
              label="Комментарий (обоснование)"
              error={errors.comment?.message}
              description="Печатается на бланке как «Ehtiyojning asoslanishi». Необязательно."
            >
              {(aria) => <Textarea {...aria} {...register("comment")} rows={2} />}
            </FormField>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Позиции</span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => append({ product_id: undefined, qty_requested: undefined } as never)}
                >
                  <Plus className="h-4 w-4" />
                  Добавить
                </Button>
              </div>

              {errors.items?.message ? (
                <p className="text-sm font-medium text-destructive">{errors.items.message}</p>
              ) : null}

              <div className="space-y-2">
                {fields.map((f, i) => {
                  const rowProductId = items?.[i]?.product_id;
                  const purchased =
                    rowProductId != null ? purchasedByProduct.get(rowProductId) ?? 0 : 0;
                  // Строка «заблокирована», только если уведомление в работе и по её
                  // товару уже есть приобретения: товар не меняется, удалять нельзя,
                  // qty не ниже приобретённого.
                  const locked = isInProgress && purchased > 0;
                  const excludeIds = (items ?? [])
                    .map((it) => it?.product_id)
                    .filter((pid, idx): pid is number => pid != null && idx !== i);

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
                                  disabled={locked}
                                />
                              )}
                            </FormField>
                          )}
                        />
                      </div>
                      <div className="w-32">
                        <FormField
                          id={`items.${i}.qty_requested`}
                          label="Кол-во"
                          required
                          error={errors.items?.[i]?.qty_requested?.message}
                          description={
                            locked ? `Приобретено: ${formatQty(purchased)}` : undefined
                          }
                        >
                          {(aria) => (
                            <Input
                              {...aria}
                              type="number"
                              step="any"
                              min={locked ? purchased : 0}
                              {...register(`items.${i}.qty_requested`)}
                            />
                          )}
                        </FormField>
                      </div>
                      {locked ? (
                        <span
                          className="mt-8 inline-flex h-9 w-9 items-center justify-center text-muted-foreground"
                          title="Есть приобретения: строку удалить нельзя"
                          aria-label="Есть приобретения: строку удалить нельзя"
                        >
                          <Lock className="h-4 w-4" />
                        </span>
                      ) : (
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
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose} disabled={update.isPending}>
                Отмена
              </Button>
              <Button type="submit" disabled={update.isPending}>
                {update.isPending ? "Сохранение…" : "Сохранить"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
