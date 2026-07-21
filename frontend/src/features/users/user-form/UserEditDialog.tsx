import { useState } from "react";
import { Pencil } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useUpdateUser } from "@/entities/user/api/mutations";
import { useMe } from "@/entities/session/api/use-me";
import type { User } from "@/entities/user/model/types";
import { fieldByName } from "@/shared/lib/field-descriptor";
import { userFields } from "@/entities/user/model/fields";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Checkbox } from "@/shared/ui/checkbox";
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
import { RoleCategoryFields } from "./RoleCategoryFields";
import { toUserUpdate, userUpdateSchema, type UserUpdateFormValues } from "./user.schema";

const L = (name: string) => fieldByName(userFields, name).label;

function toFormValues(row: User): UserUpdateFormValues {
  return {
    full_name: row.full_name,
    email: row.email ?? "",
    role: row.role,
    category: row.category ?? undefined,
    is_active: row.is_active,
  };
}

/**
 * Правка пользователя (§14): PATCH /users/{id} — full_name/email/role/category/
 * is_active. username не входит (api.update=false) — показан readonly. UserList
 * уже несёт все поля, нужные форме (в отличие от warehouses, где address
 * get_index=false) — префилл из строки таблицы, без догрузки GET /users/{id}.
 *
 * Самозащита админа (зеркало серверной self_deactivation_forbidden, §14): если
 * редактируем СЕБЯ (id === useMe().id) — чекбокс "Активен" задизейблен, снять
 * его нельзя. Самоуничижение роли (self_demotion_forbidden) на клиенте не
 * блокируем — по ТЗ блокируется только is_active; попытка сменить свою роль
 * вернёт 422 с сервера, текст — тостом (apply-api-error).
 */
export function UserEditDialog({ row }: { row: User }) {
  const [open, setOpen] = useState(false);
  const { data: me } = useMe();
  const isSelf = me != null && me.id === row.id;
  const mutation = useUpdateUser();

  const form = useForm<UserUpdateFormValues>({
    resolver: zodResolver(userUpdateSchema),
    defaultValues: toFormValues(row),
  });
  const {
    register,
    control,
    watch,
    setValue,
    formState: { errors },
  } = form;
  const category = watch("category");

  const onSubmit = (values: UserUpdateFormValues) => {
    // Самозащита на клиенте зеркалит сервер: свою активность не трогаем, даже
    // если чекбокс каким-то образом получил бы иное значение.
    const safeValues = isSelf ? { ...values, is_active: true } : values;
    mutation.mutate(
      { id: row.id, body: toUserUpdate(safeValues) },
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
        if (next) form.reset(toFormValues(row));
      }}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={`Изменить пользователя ${row.full_name}`}>
          <Pencil />
          Изменить
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Пользователь: {row.full_name}</DialogTitle>
          <DialogDescription>Измените данные учётной записи и сохраните.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <FormField id="username-ro" label={L("username")}>
            {(aria) => <Input {...aria} value={row.username} disabled readOnly />}
          </FormField>

          <FormField id="full_name" label={L("full_name")} required error={errors.full_name?.message}>
            {(aria) => <Input {...aria} {...register("full_name")} maxLength={255} autoFocus />}
          </FormField>

          <FormField
            id="email"
            label={L("email")}
            error={errors.email?.message}
            description="Опционально, формат имя@npuu.uz"
          >
            {(aria) => <Input {...aria} {...register("email")} type="email" maxLength={255} />}
          </FormField>

          <Controller
            control={control}
            name="role"
            render={({ field }) => (
              <RoleCategoryFields
                role={field.value}
                category={category}
                onRoleChange={(v) => {
                  field.onChange(v);
                  if (v === "admin") setValue("category", undefined);
                }}
                onCategoryChange={(v) => setValue("category", v)}
                roleError={errors.role?.message}
                categoryError={errors.category?.message}
              />
            )}
          />

          <Controller
            control={control}
            name="is_active"
            render={({ field }) => (
              <FormField
                id="is_active"
                label={L("is_active")}
                inline
                description={
                  isSelf ? "Нельзя деактивировать собственную учётную запись" : undefined
                }
              >
                {(aria) => (
                  <Checkbox
                    id={aria.id}
                    aria-describedby={aria["aria-describedby"]}
                    checked={field.value}
                    disabled={isSelf}
                    onCheckedChange={(v) => field.onChange(v === true)}
                  />
                )}
              </FormField>
            )}
          />

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
