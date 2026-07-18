import { useState } from "react";
import { Plus } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useCreateExpenseCategory } from "@/entities/expense-category/api/mutations";
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
  toExpenseCategoryCreate,
  type ExpenseCategoryFormValues,
} from "./expense-category.schema";

const EMPTY: ExpenseCategoryFormValues = { name: "", status: "active" };

export function ExpenseCategoryCreateDialog() {
  const [open, setOpen] = useState(false);
  const mutation = useCreateExpenseCategory();
  const form = useForm<ExpenseCategoryFormValues>({
    resolver: zodResolver(expenseCategoryFormSchema),
    defaultValues: EMPTY,
  });

  const onSubmit = (values: ExpenseCategoryFormValues) => {
    mutation.mutate(toExpenseCategoryCreate(values), {
      onSuccess: () => {
        toast.success("Вид расхода денег создан");
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
          Добавить вид
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новый вид расхода денег</DialogTitle>
          <DialogDescription>Например: Аренда, Коммунальные услуги, Зарплата.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <ExpenseCategoryFormFields form={form} mode="create" />
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
