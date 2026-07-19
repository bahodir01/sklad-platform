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
import { useCreateRequest } from "@/entities/request/api/mutations";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { requestSchema, type RequestFormValues } from "./request.schema";

/**
 * Создание заявки (teacher/worker, §5.1). Склад — только списания (AP-12),
 * строки товаров + причина. Создаётся черновик; подтверждение — отдельным
 * действием в «Мои заявки».
 */
export function RequestCreateDialog() {
  const [open, setOpen] = useState(false);
  const create = useCreateRequest();

  const form = useForm<RequestFormValues>({
    resolver: zodResolver(requestSchema),
    defaultValues: { warehouse_id: undefined, reason: "", items: [{ product_id: undefined, qty: undefined }] as never },
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

  function onSubmit(values: RequestFormValues) {
    create.mutate(values, {
      onSuccess: (req) => {
        toast.success(`Заявка ${req.number} создана (черновик). Подтвердите её в списке.`);
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
          Новая заявка
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Новая заявка на получение</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <Controller
            control={control}
            name="warehouse_id"
            render={({ field }) => (
              <FormField id="warehouse_id" label="Склад списания" required error={errors.warehouse_id?.message}>
                {(aria) => (
                  <WarehouseSelect
                    source="issuance"
                    value={field.value}
                    onChange={field.onChange}
                    aria={aria}
                    placeholder="Выберите склад списания"
                  />
                )}
              </FormField>
            )}
          />

          <FormField id="reason" label="Причина получения" required error={errors.reason?.message}>
            {(aria) => <Textarea {...aria} {...register("reason")} rows={2} />}
          </FormField>

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
                            {...register(`items.${i}.qty`, { valueAsNumber: true })}
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
          </div>

          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Сохранение…" : "Создать заявку"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
