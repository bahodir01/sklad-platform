import { useState } from "react";
import { Plus } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useCreateExpenseType } from "@/entities/expense-type/api/mutations";
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
  toExpenseTypeCreate,
  type ExpenseTypeFormValues,
} from "./expense-type.schema";

const EMPTY: ExpenseTypeFormValues = { name: "", requires_employee: false, status: "active" };

export function ExpenseTypeCreateDialog() {
  const [open, setOpen] = useState(false);
  const mutation = useCreateExpenseType();
  const form = useForm<ExpenseTypeFormValues>({
    resolver: zodResolver(expenseTypeFormSchema),
    defaultValues: EMPTY,
  });

  const onSubmit = (values: ExpenseTypeFormValues) => {
    mutation.mutate(toExpenseTypeCreate(values), {
      onSuccess: () => {
        toast.success("Тип расхода товара создан");
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
          Добавить тип
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новый тип расхода товара</DialogTitle>
          <DialogDescription>Например: Выдача сотруднику, Порча, Брак.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <ExpenseTypeFormFields form={form} mode="create" />
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
