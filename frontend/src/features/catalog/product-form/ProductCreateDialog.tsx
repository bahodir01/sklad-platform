import { useState } from "react";
import { Plus } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useCreateProduct } from "@/entities/product/api/mutations";
import { UnitSelect } from "@/entities/unit/ui/UnitSelect";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { FormField } from "@/shared/ui/form-field";
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
import { productCreateSchema, toProductCreate, type ProductCreateValues } from "./product.schema";

const EMPTY: ProductCreateValues = { name: "", unit_id: 0, sku: "" };

export function ProductCreateDialog() {
  const [open, setOpen] = useState(false);
  const mutation = useCreateProduct();
  const form = useForm<ProductCreateValues>({
    resolver: zodResolver(productCreateSchema),
    defaultValues: EMPTY,
  });

  const onSubmit = (values: ProductCreateValues) => {
    mutation.mutate(toProductCreate(values), {
      onSuccess: () => {
        toast.success("Товар создан");
        form.reset(EMPTY);
        setOpen(false);
      },
      onError: (error) => applyApiError(error, form.setError),
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) form.reset(EMPTY);
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus />
          Добавить товар
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новый товар</DialogTitle>
          <DialogDescription>
            Единицу измерения после создания изменить нельзя — выберите внимательно.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <FormField id="name" label="Номенклатура" required error={form.formState.errors.name?.message}>
            {(aria) => <Input {...aria} {...form.register("name")} maxLength={255} autoFocus />}
          </FormField>

          <Controller
            control={form.control}
            name="unit_id"
            render={({ field }) => (
              <FormField
                id="unit_id"
                label="Единица измерения"
                required
                error={form.formState.errors.unit_id?.message}
              >
                {(aria) => (
                  <UnitSelect
                    value={field.value || undefined}
                    onChange={field.onChange}
                    aria={aria}
                  />
                )}
              </FormField>
            )}
          />

          <FormField id="sku" label="Артикул" error={form.formState.errors.sku?.message}>
            {(aria) => <Input {...aria} {...form.register("sku")} maxLength={64} />}
          </FormField>

          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Сохранение…" : "Создать"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
