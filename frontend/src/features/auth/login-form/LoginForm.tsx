import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { login } from "@/entities/session/api/auth-api";
import { tokenStore } from "@/entities/session/model/token-store";
import { useSessionStore } from "@/entities/session/model/session-store";
import { authKeys } from "@/shared/api/query-keys";
import { ApiError } from "@/shared/api/errors";
import { HOME_ROUTE } from "@/shared/config/routes";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { FormField } from "@/shared/ui/form-field";
import { loginSchema, type LoginFormValues } from "./login.schema";

export function LoginForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setStatus = useSessionStore((s) => s.setStatus);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  });

  const onSubmit = async (values: LoginFormValues) => {
    setFormError(null);
    try {
      const res = await login(values);
      tokenStore.set(res.access_token);
      setStatus("authenticated");
      // Логин: инвалидируем ['auth','me'], чтобы шапка подтянула пользователя.
      await queryClient.invalidateQueries({ queryKey: authKeys.me });
      navigate(HOME_ROUTE, { replace: true });
    } catch (error) {
      // 401 invalid_credentials → общий текст под формой, без подсветки поля:
      // не подсказываем, что именно не так (§6).
      if (error instanceof ApiError && error.status === 401) {
        setFormError(error.message);
      } else if (error instanceof ApiError) {
        setFormError(error.message);
      } else {
        setFormError("Не удалось выполнить вход. Попробуйте позже");
      }
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <FormField id="username" label="Логин" required error={errors.username?.message}>
        {(aria) => (
          <Input
            {...aria}
            {...register("username")}
            autoComplete="username"
            autoFocus
          />
        )}
      </FormField>

      <FormField id="password" label="Пароль" required error={errors.password?.message}>
        {(aria) => (
          <Input
            {...aria}
            {...register("password")}
            type="password"
            autoComplete="current-password"
          />
        )}
      </FormField>

      {formError ? (
        <p className="text-sm font-medium text-destructive" role="alert">
          {formError}
        </p>
      ) : null}

      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Вход…" : "Войти"}
      </Button>
    </form>
  );
}
