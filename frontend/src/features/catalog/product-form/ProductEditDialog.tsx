import { useState } from "react";
import { Pencil } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useUpdateProduct } from "@/entities/product/api/mutations";
import { useUnitsForResolve } from "@/entities/unit/api/queries";
import type { Product } from "@/entities/product/model/types";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { FormField } from "@/shared/ui/form-field";
import { StatusSelect } from "@/shared/ui/status-select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { productUpdateSchema, toProductUpdate, type ProductUpdateValues } from "./product.schema";

/**
 * Правка товара. unit_id в правке ОТСУТСТВУЕТ (api.update=false, К-E): ЕИ
 * показываем СТАТИКОЙ (из кэша units), а не disabled-селектом — условия
 * разблокировки нет. status и остальные update-поля редактируются.
 */
export function ProductEditDialog({ row }: { row: Product }) {
  const [open, setOpen] = useState(false);
  const mutation = useUpdateProduct();
  const units = useUnitsForResolve();
  const unitLabel =
    units.data?.items.find((u) => u.id === row.unit_id)?.code ?? `#${row.unit_id}`;

  const form = useForm<ProductUpdateValues>({
    resolver: zodResolver(productUpdateSchema),
    defaultValues: { name: row.name, sku: row.sku ?? "", status: row.status },
  });

  const onSubmit = (values: ProductUpdateValues) => {
    mutation.mutate(
      { id: row.id, body: toProductUpdate(values) },
      {
        onSuccess: () => {
          toast.success("Изменения сохранены");
          setOpen(false);
        },
        onError: (error) => applyApiError(error, form.setError),
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) form.reset({ name: row.name, sku: row.sku ?? "", status: row.status });
      }}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={`Изменить товар ${row.name}`}>
          <Pencil />
          Изменить
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Товар</DialogTitle>
          <DialogDescription>Измените данные товара и сохраните.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <FormField id="name" label="Номенклатура" required error={form.formState.errors.name?.message}>
            {(aria) => <Input {...aria} {...form.register("name")} maxLength={255} autoFocus />}
          </FormField>

          {/* ЕИ — статикой: api.update=false, поля в форме нет (§8.2, К-E). */}
          <div className="space-y-1.5">
            <p className="text-sm font-medium leading-none">Единица измерения</p>
            <p className="text-sm text-muted-foreground">
              {unitLabel} <span className="italic">(после создания не меняется)</span>
            </p>
          </div>

          <FormField id="sku" label="Артикул" error={form.formState.errors.sku?.message}>
            {(aria) => <Input {...aria} {...form.register("sku")} maxLength={64} />}
          </FormField>

          <Controller
            control={form.control}
            name="status"
            render={({ field }) => (
              <FormField id="status" label="Статус" error={form.formState.errors.status?.message}>
                {(aria) => (
                  <StatusSelect value={field.value} onChange={field.onChange} aria={aria} />
                )}
              </FormField>
            )}
          />

          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Сохранение…" : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
