import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Textarea } from "@/shared/ui/textarea";
import { FormField } from "@/shared/ui/form-field";
import { CashDeskSelect } from "@/entities/cash/ui/CashDeskSelect";
import { useCreateIncome } from "@/entities/cash/api/mutations";
import type { MoneyIncomeCreate } from "@/entities/cash/model/types";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { todayIso } from "@/shared/lib/format";
import { incomeSchema, type IncomeFormValues } from "./income.schema";

/**
 * Форма прихода денег в кассу (admin, §7.2). При успехе — балансы касс
 * пересчитываются (инвалидация в мутации), форма сбрасывается.
 */
export function IncomeForm() {
  const create = useCreateIncome();
  const form = useForm<IncomeFormValues>({
    resolver: zodResolver(incomeSchema),
    defaultValues: { cash_desk_id: undefined, amount: undefined, date: todayIso(), comment: "" },
  });
  const {
    control,
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = form;

  function onSubmit(values: IncomeFormValues) {
    const payload: MoneyIncomeCreate = {
      cash_desk_id: values.cash_desk_id,
      amount: values.amount,
      date: values.date,
      comment: values.comment?.trim() ? values.comment.trim() : null,
    };
    create.mutate(payload, {
      onSuccess: () => {
        toast.success("Приход проведён, баланс кассы обновлён");
        reset({ cash_desk_id: undefined, amount: undefined, date: todayIso(), comment: "" });
      },
      onError: (e) => applyApiError(e, form.setError),
    });
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Controller
          control={control}
          name="cash_desk_id"
          render={({ field }) => (
            <FormField id="cash_desk_id" label="Касса" required error={errors.cash_desk_id?.message}>
              {(aria) => <CashDeskSelect value={field.value} onChange={field.onChange} aria={aria} />}
            </FormField>
          )}
        />
        <FormField id="amount" label="Сумма, UZS" required error={errors.amount?.message}>
          {(aria) => <Input {...aria} type="number" step="any" min="0" className="text-right" {...register("amount")} />}
        </FormField>
        <FormField id="income-date" label="Дата" required error={errors.date?.message}>
          {(aria) => <Input {...aria} type="date" {...register("date")} />}
        </FormField>
      </div>

      <FormField id="income-comment" label="Комментарий" error={errors.comment?.message}>
        {(aria) => <Textarea {...aria} {...register("comment")} rows={2} placeholder="Необязательно" />}
      </FormField>

      <div className="flex justify-end">
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? "Проведение…" : "Провести приход"}
        </Button>
      </div>
    </form>
  );
}
