import { useState } from "react";
import { useForm, useFieldArray, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Textarea } from "@/shared/ui/textarea";
import { FormField } from "@/shared/ui/form-field";
import { WarehouseSelect } from "@/entities/warehouse/ui/WarehouseSelect";
import { ProductSelect } from "@/entities/product/ui/ProductSelect";
import { useCreateNotification } from "@/entities/notification/api/mutations";
import type { NotificationCreate } from "@/entities/notification/model/types";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { todayIso } from "@/shared/lib/format";
import { notificationSchema, type NotificationFormValues } from "./notification.schema";

/**
 * Создание уведомления BILDIRISHNOMA (admin, §6.1). Шапка (дата, склад, текст
 * обращения, подразделение, комментарий) + строки товаров. После создания —
 * уведомление появляется в списке со статусом «Черновик/В работе».
 */
export function NotificationCreateDialog() {
  const [open, setOpen] = useState(false);
  const create = useCreateNotification();

  const form = useForm<NotificationFormValues>({
    resolver: zodResolver(notificationSchema),
    defaultValues: {
      date: todayIso(),
      warehouse_id: undefined,
      division_name: "",
      body_text: "",
      comment: "",
      items: [{ product_id: undefined, qty_requested: undefined }] as never,
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

  function onSubmit(values: NotificationFormValues) {
    const payload: NotificationCreate = {
      date: values.date,
      warehouse_id: values.warehouse_id,
      body_text: values.body_text,
      division_name: values.division_name,
      comment: values.comment?.trim() ? values.comment.trim() : null,
      items: values.items.map((it) => ({
        product_id: it.product_id,
        qty_requested: it.qty_requested,
      })),
    };
    create.mutate(payload, {
      onSuccess: (n) => {
        toast.success(`Уведомление ${n.number} создано`);
        reset();
        setOpen(false);
      },
      onError: (e) => applyApiError(e, form.setError),
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4" />
          Новое уведомление
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Новое уведомление о потребности</DialogTitle>
        </DialogHeader>

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
                  label="Склад назначения"
                  required
                  error={errors.warehouse_id?.message}
                >
                  {(aria) => (
                    <WarehouseSelect
                      source="active"
                      value={field.value}
                      onChange={field.onChange}
                      aria={aria}
                      placeholder="Склад поступления"
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
                        id={`items.${i}.qty_requested`}
                        label="Кол-во"
                        required
                        error={errors.items?.[i]?.qty_requested?.message}
                      >
                        {(aria) => (
                          <Input {...aria} type="number" step="any" min="0" {...register(`items.${i}.qty_requested`)} />
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
          </div>

          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Сохранение…" : "Создать уведомление"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
