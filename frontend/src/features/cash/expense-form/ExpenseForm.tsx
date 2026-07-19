import { useRef } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Textarea } from "@/shared/ui/textarea";
import { FormField } from "@/shared/ui/form-field";
import { ExpenseCategorySelect } from "@/entities/expense-category/ui/ExpenseCategorySelect";
import { useCreateExpense } from "@/entities/cash/api/mutations";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { todayIso } from "@/shared/lib/format";
import { expenseSchema, type ExpenseFormValues } from "./expense.schema";

/**
 * Форма расхода денег с чеком (teacher/worker, §5.4). Кассу и сотрудника НЕ
 * показываем — их определяет сервер (SV-6). Чек — обязательный файл (INV-7);
 * сумма/описание валидируются клиентом и повторно сервером. Amount уходит
 * строкой (Decimal), чтобы не терять точность.
 */
export function ExpenseForm() {
  const create = useCreateExpense();
  const fileRef = useRef<HTMLInputElement>(null);

  const form = useForm<ExpenseFormValues>({
    resolver: zodResolver(expenseSchema),
    defaultValues: {
      expense_category_id: undefined,
      amount: undefined,
      description: "",
      date: todayIso(),
      receipt: undefined as unknown as File,
    },
  });
  const {
    control,
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = form;

  function onSubmit(values: ExpenseFormValues) {
    create.mutate(
      {
        expense_category_id: values.expense_category_id,
        amount: String(values.amount),
        description: values.description.trim(),
        date: values.date,
        receipt: values.receipt,
      },
      {
        onSuccess: () => {
          toast.success("Расход проведён, чек загружен");
          reset({
            expense_category_id: undefined,
            amount: undefined,
            description: "",
            date: todayIso(),
            receipt: undefined as unknown as File,
          });
          if (fileRef.current) fileRef.current.value = "";
        },
        onError: (e) => applyApiError(e, form.setError),
      },
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Controller
          control={control}
          name="expense_category_id"
          render={({ field }) => (
            <FormField
              id="expense_category_id"
              label="Вид расхода"
              required
              error={errors.expense_category_id?.message}
            >
              {(aria) => <ExpenseCategorySelect value={field.value} onChange={field.onChange} aria={aria} />}
            </FormField>
          )}
        />
        <FormField id="expense-amount" label="Сумма, UZS" required error={errors.amount?.message}>
          {(aria) => <Input {...aria} type="number" step="any" min="0" className="text-right" {...register("amount")} />}
        </FormField>
        <FormField id="expense-date" label="Дата" required error={errors.date?.message}>
          {(aria) => <Input {...aria} type="date" {...register("date")} />}
        </FormField>
      </div>

      <FormField id="expense-description" label="Описание" required error={errors.description?.message}>
        {(aria) => <Textarea {...aria} {...register("description")} rows={2} placeholder="На что потрачено" />}
      </FormField>

      <Controller
        control={control}
        name="receipt"
        render={({ field }) => (
          <FormField
            id="receipt"
            label="Чек"
            required
            error={errors.receipt?.message}
            description="Обязательно: фото или скан чека (jpg/png/pdf, до 10 МБ)."
          >
            {(aria) => (
              <Input
                {...aria}
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,application/pdf"
                onChange={(e) => field.onChange(e.target.files?.[0])}
                className="cursor-pointer file:mr-3 file:cursor-pointer file:rounded file:border-0 file:bg-muted file:px-3 file:py-1 file:text-sm"
              />
            )}
          </FormField>
        )}
      />

      <div className="flex justify-end">
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? "Проведение…" : "Провести расход"}
        </Button>
      </div>
    </form>
  );
}
