import { useState } from "react";
import { PowerOff } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useUpdateIntegration, useDisableIntegration } from "@/entities/integration/api/mutations";
import type { Integration, IntegrationKind } from "@/entities/integration/model/types";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { PasswordInput } from "@/shared/ui/password-input";
import { FormField } from "@/shared/ui/form-field";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Skeleton } from "@/shared/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/ui/alert-dialog";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { formatDateTime } from "@/shared/lib/format";
import {
  integrationSecretSchema,
  type IntegrationSecretFormValues,
} from "./integration-secret.schema";

interface IntegrationCardProps {
  kind: IntegrationKind;
  /** Заголовок карточки (напр. «Telegram-бот»). */
  title: string;
  /** Строка данных с сервера для этого kind; undefined, пока список ещё грузится. */
  integration: Integration | undefined;
  isLoading: boolean;
  /** Пояснение под карточкой — откуда взять значение секрета (§5а). */
  hint: string;
}

const EMPTY: IntegrationSecretFormValues = { secret: "" };

/**
 * Карточка одной интеграции (спека15 §5а): статус + display_name/masked_secret/
 * updated_at из GET /admin/integrations, поле нового секрета + «Сохранить и
 * проверить» (PUT — сервер проверяет секрет ДО сохранения, 422 с текстом
 * ошибки сервера как есть — через applyApiError), «Отключить» (POST disable,
 * с подтверждением). Секрет никогда не приходит с сервера в открытом виде —
 * это поле всегда пустое при открытии, не «редактирование» существующего
 * значения.
 */
export function IntegrationCard({ kind, title, integration, isLoading, hint }: IntegrationCardProps) {
  const [disableOpen, setDisableOpen] = useState(false);
  const update = useUpdateIntegration();
  const disable = useDisableIntegration();
  const form = useForm<IntegrationSecretFormValues>({
    resolver: zodResolver(integrationSecretSchema),
    defaultValues: EMPTY,
  });
  const {
    register,
    formState: { errors },
  } = form;

  const onSubmit = (values: IntegrationSecretFormValues) => {
    update.mutate(
      { kind, secret: values.secret },
      {
        onSuccess: () => {
          toast.success(`«${title}»: секрет сохранён и проверен`);
          form.reset(EMPTY);
        },
        onError: (error) => applyApiError(error, form.setError),
      },
    );
  };

  const handleDisable = () => {
    disable.mutate(
      { kind },
      {
        onSuccess: () => {
          setDisableOpen(false);
          toast.success(`«${title}» отключена`);
        },
        onError: (error) => applyApiError(error),
      },
    );
  };

  if (isLoading || !integration) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-40" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-base">{title}</CardTitle>
        <Badge variant={integration.is_enabled ? "success" : "muted"}>
          {integration.is_enabled ? "Включена" : "Выключена"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="space-y-1 text-sm">
          {integration.display_name ? (
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Имя</dt>
              <dd className="font-medium">{integration.display_name}</dd>
            </div>
          ) : null}
          {integration.masked_secret ? (
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Секрет</dt>
              <dd className="font-mono">{integration.masked_secret}</dd>
            </div>
          ) : null}
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground">Обновлено</dt>
            <dd>{formatDateTime(integration.updated_at)}</dd>
          </div>
        </dl>

        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3" noValidate>
          <FormField
            id={`${kind}-secret`}
            label="Новый секрет"
            required
            error={errors.secret?.message}
          >
            {(aria) => (
              <PasswordInput
                {...aria}
                {...register("secret")}
                autoComplete="off"
                placeholder={integration.masked_secret ?? "Вставьте токен или ключ"}
              />
            )}
          </FormField>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={update.isPending}>
              {update.isPending ? "Проверка…" : "Сохранить и проверить"}
            </Button>

            {integration.is_enabled ? (
              <AlertDialog open={disableOpen} onOpenChange={setDisableOpen}>
                <AlertDialogTrigger asChild>
                  <Button type="button" variant="outline" size="sm">
                    <PowerOff />
                    Отключить
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Отключить «{title}»?</AlertDialogTitle>
                    <AlertDialogDescription>
                      Интеграция перестанет использоваться. Сохранённый секрет не удаляется —
                      его можно включить заново, повторно сохранив тот же или новый секрет.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel disabled={disable.isPending}>Отмена</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={(e) => {
                        e.preventDefault();
                        handleDisable();
                      }}
                      disabled={disable.isPending}
                    >
                      Отключить
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            ) : null}
          </div>
        </form>

        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}
