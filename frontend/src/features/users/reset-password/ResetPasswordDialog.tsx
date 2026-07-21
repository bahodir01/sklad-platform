import { useState } from "react";
import { KeyRound } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useResetPassword } from "@/entities/user/api/mutations";
import type { User } from "@/entities/user/model/types";
import { Button } from "@/shared/ui/button";
import { PasswordInput } from "@/shared/ui/password-input";
import { FormField } from "@/shared/ui/form-field";
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
import { resetPasswordSchema, type ResetPasswordFormValues } from "./reset-password.schema";

const EMPTY: ResetPasswordFormValues = { password: "", confirm: "" };

/**
 * Сброс пароля (§14 backend): POST /users/{id}/reset-password → 204. Гасит все
 * refresh-сессии пользователя в Redis (сервер) — отдельная операция от PATCH,
 * поэтому отдельный диалог. Подтверждение пароля — клиентская проверка (не
 * контрактное поле, в теле запроса не участвует).
 */
export function ResetPasswordDialog({ row }: { row: User }) {
  const [open, setOpen] = useState(false);
  const mutation = useResetPassword();
  const form = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: EMPTY,
  });
  const {
    register,
    formState: { errors },
  } = form;

  const onSubmit = (values: ResetPasswordFormValues) => {
    mutation.mutate(
      { id: row.id, password: values.password },
      {
        onSuccess: () => {
          toast.success(`Пароль пользователя «${row.username}» сброшен`);
          form.reset(EMPTY);
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
        if (!next) form.reset(EMPTY);
      }}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={`Сбросить пароль пользователя ${row.username}`}>
          <KeyRound />
          Сбросить пароль
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Сброс пароля: {row.username}</DialogTitle>
          <DialogDescription>
            Все активные сессии пользователя «{row.full_name}» будут завершены.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <FormField id="password" label="Новый пароль" required error={errors.password?.message}>
            {(aria) => (
              <PasswordInput {...aria} {...register("password")} autoComplete="new-password" autoFocus />
            )}
          </FormField>

          <FormField id="confirm" label="Подтверждение пароля" required error={errors.confirm?.message}>
            {(aria) => (
              <PasswordInput {...aria} {...register("confirm")} autoComplete="new-password" />
            )}
          </FormField>

          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Сохранение…" : "Сбросить пароль"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
