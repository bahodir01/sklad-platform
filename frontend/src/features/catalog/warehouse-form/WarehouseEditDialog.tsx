import { useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useUpdateWarehouse } from "@/entities/warehouse/api/mutations";
import { useWarehouse } from "@/entities/warehouse/api/queries";
import type { Warehouse } from "@/entities/warehouse/model/types";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog";
import { Skeleton } from "@/shared/ui/skeleton";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { WarehouseFormFields } from "./WarehouseFormFields";
import { toWarehouseUpdate, warehouseFormSchema, type WarehouseFormValues } from "./warehouse.schema";

/**
 * Правка склада. ОБЯЗАТЕЛЬНО догружает GET /warehouses/{id} ради address
 * (в списке его нет — get_index=false, К-H). Пока грузится — скелет в теле.
 */
export function WarehouseEditDialog({ row }: { row: Warehouse }) {
  const [open, setOpen] = useState(false);
  const detail = useWarehouse(row.id, open);
  const mutation = useUpdateWarehouse();

  const form = useForm<WarehouseFormValues>({
    resolver: zodResolver(warehouseFormSchema),
    defaultValues: {
      code: row.code,
      name: row.name,
      address: "",
      allows_issuance: row.allows_issuance,
      status: row.status,
    },
  });

  // Префилл из детали, как только она пришла (address есть только здесь).
  useEffect(() => {
    if (detail.data) {
      form.reset({
        code: detail.data.code,
        name: detail.data.name,
        address: detail.data.address ?? "",
        allows_issuance: detail.data.allows_issuance,
        status: detail.data.status,
      });
    }
  }, [detail.data, form]);

  const onSubmit = (values: WarehouseFormValues) => {
    mutation.mutate(
      { id: row.id, body: toWarehouseUpdate(values) },
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
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={`Изменить склад ${row.code}`}>
          <Pencil />
          Изменить
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Склад: {row.code}</DialogTitle>
          <DialogDescription>Измените данные склада и сохраните.</DialogDescription>
        </DialogHeader>
        {detail.isLoading ? (
          <div className="space-y-4" aria-busy="true">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-6 w-2/3" />
          </div>
        ) : detail.isError ? (
          <div className="py-6 text-center">
            <p className="mb-3 text-sm text-muted-foreground">Не удалось загрузить склад.</p>
            <Button variant="outline" size="sm" onClick={() => detail.refetch()}>
              Повторить
            </Button>
          </div>
        ) : (
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <WarehouseFormFields form={form} mode="update" />
            <DialogFooter>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Сохранение…" : "Сохранить"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
