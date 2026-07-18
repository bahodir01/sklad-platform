import { useState } from "react";
import { Pencil } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useUpdateExpenseType } from "@/entities/expense-type/api/mutations";
import type { ExpenseType } from "@/entities/expense-type/model/types";
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
import { ExpenseTypeFormFields } from "./ExpenseTypeFormFields";
import {
  expenseTypeFormSchema,
  toExpenseTypeUpdate,
  type ExpenseTypeFormValues,
} from "./expense-type.schema";

export function ExpenseTypeEditDialog({ row }: { row: ExpenseType }) {
  const [open, setOpen] = useState(false);
  const mutation = useUpdateExpenseType();
  const initial: ExpenseTypeFormValues = {
    name: row.name,
    requires_employee: row.requires_employee,
    status: row.status,
  };
  const form = useForm<ExpenseTypeFormValues>({
    resolver: zodResolver(expenseTypeFormSchema),
    defaultValues: initial,
  });

  const onSubmit = (values: ExpenseTypeFormValues) => {
    mutation.mutate(
      { id: row.id, body: toExpenseTypeUpdate(values) },
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
        if (next) form.reset(initial);
      }}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={`Изменить тип ${row.name}`}>
          <Pencil />
          Изменить
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Тип расхода товара</DialogTitle>
          <DialogDescription>Измените данные и сохраните.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <ExpenseTypeFormFields form={form} mode="update" />
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
