import { useState } from "react";
import { Plus } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useCreateUnit } from "@/entities/unit/api/mutations";
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
import { toUnitCreate, unitFormSchema, type UnitFormValues } from "./unit.schema";

const EMPTY: UnitFormValues = { code: "", name: "", is_active: true };

export function UnitCreateDialog() {
  const [open, setOpen] = useState(false);
  const mutation = useCreateUnit();
  const form = useForm<UnitFormValues>({
    resolver: zodResolver(unitFormSchema),
    defaultValues: EMPTY,
  });

  const onSubmit = (values: UnitFormValues) => {
    mutation.mutate(toUnitCreate(values), {
      onSuccess: () => {
        toast.success("Единица измерения создана");
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
          Добавить ЕИ
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новая единица измерения</DialogTitle>
          <DialogDescription>Например: шт — Штука.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <UnitFormFields form={form} mode="create" />
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
