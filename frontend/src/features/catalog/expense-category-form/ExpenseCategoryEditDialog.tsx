import { useState } from "react";
import { Pencil } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useUpdateExpenseCategory } from "@/entities/expense-category/api/mutations";
import type { ExpenseCategory } from "@/entities/expense-category/model/types";
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
import { ExpenseCategoryFormFields } from "./ExpenseCategoryFormFields";
import {
  expenseCategoryFormSchema,
  toExpenseCategoryUpdate,
  type ExpenseCategoryFormValues,
} from "./expense-category.schema";

export function ExpenseCategoryEditDialog({ row }: { row: ExpenseCategory }) {
  const [open, setOpen] = useState(false);
  const mutation = useUpdateExpenseCategory();
  const initial: ExpenseCategoryFormValues = { name: row.name, status: row.status };
  const form = useForm<ExpenseCategoryFormValues>({
    resolver: zodResolver(expenseCategoryFormSchema),
    defaultValues: initial,
  });

  const onSubmit = (values: ExpenseCategoryFormValues) => {
    mutation.mutate(
      { id: row.id, body: toExpenseCategoryUpdate(values) },
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
        <Button variant="ghost" size="sm" aria-label={`Изменить вид расхода ${row.name}`}>
          <Pencil />
          Изменить
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Вид расхода денег</DialogTitle>
          <DialogDescription>Измените данные и сохраните.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <ExpenseCategoryFormFields form={form} mode="update" />
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
