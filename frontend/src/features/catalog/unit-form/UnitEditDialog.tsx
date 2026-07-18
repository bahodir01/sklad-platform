import { useState } from "react";
import { Pencil } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useUpdateUnit } from "@/entities/unit/api/mutations";
import type { Unit } from "@/entities/unit/model/types";
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
import { UnitFormFields } from "./UnitFormFields";
import { toUnitUpdate, unitFormSchema, type UnitFormValues } from "./unit.schema";

/**
 * Правка ЕИ. UnitRead == UnitList → отдельного экрана детали нет, префилл из
 * строки таблицы (§8.1); догрузка не нужна.
 */
export function UnitEditDialog({ row }: { row: Unit }) {
  const [open, setOpen] = useState(false);
  const mutation = useUpdateUnit();
  const form = useForm<UnitFormValues>({
    resolver: zodResolver(unitFormSchema),
    defaultValues: { code: row.code, name: row.name, is_active: row.is_active },
  });

  const onSubmit = (values: UnitFormValues) => {
    mutation.mutate(
      { id: row.id, body: toUnitUpdate(values) },
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
        if (next) form.reset({ code: row.code, name: row.name, is_active: row.is_active });
      }}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={`Изменить ЕИ ${row.code}`}>
          <Pencil />
          Изменить
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Единица измерения: {row.code}</DialogTitle>
          <DialogDescription>Измените данные и сохраните.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <UnitFormFields form={form} mode="update" />
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
