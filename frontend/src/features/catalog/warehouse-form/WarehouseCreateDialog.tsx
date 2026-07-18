import { useState } from "react";
import { Plus } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useCreateWarehouse } from "@/entities/warehouse/api/mutations";
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
import { applyApiError } from "@/shared/lib/apply-api-error";
import { WarehouseFormFields } from "./WarehouseFormFields";
import { toWarehouseCreate, warehouseFormSchema, type WarehouseFormValues } from "./warehouse.schema";

const EMPTY: WarehouseFormValues = {
  code: "",
  name: "",
  address: "",
  allows_issuance: false,
  status: "active",
};

export function WarehouseCreateDialog() {
  const [open, setOpen] = useState(false);
  const mutation = useCreateWarehouse();
  const form = useForm<WarehouseFormValues>({
    resolver: zodResolver(warehouseFormSchema),
    defaultValues: EMPTY,
  });

  const onSubmit = (values: WarehouseFormValues) => {
    mutation.mutate(toWarehouseCreate(values), {
      onSuccess: () => {
        toast.success("Склад создан");
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
          Добавить склад
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новый склад</DialogTitle>
          <DialogDescription>Заполните данные склада и сохраните.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <WarehouseFormFields form={form} mode="create" />
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
