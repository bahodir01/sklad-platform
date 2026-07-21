import { useState } from "react";
import { Plus } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useCreateUser } from "@/entities/user/api/mutations";
import { fieldByName } from "@/shared/lib/field-descriptor";
import { userFields } from "@/entities/user/model/fields";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
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
import { RoleCategoryFields } from "./RoleCategoryFields";
import { toUserCreate, userCreateSchema, type UserCreateFormValues } from "./user.schema";

const L = (name: string) => fieldByName(userFields, name).label;

const EMPTY: UserCreateFormValues = {
  full_name: "",
  username: "",
  email: "",
  role: "worker",
  category: "worker",
  password: "",
};

/**
 * Создание пользователя (§14 backend): POST /users — full_name, username,
 * email (опц.), role, category (скрыт/не отправляется для admin, INV-9),
 * password (мин. 8, показать/скрыть). is_active в create не входит
 * (api.create=false) — новый пользователь всегда активен на сервере.
 */
export function UserCreateDialog() {
  const [open, setOpen] = useState(false);
  const mutation = useCreateUser();
  const form = useForm<UserCreateFormValues>({
    resolver: zodResolver(userCreateSchema),
    defaultValues: EMPTY,
  });
  const {
    register,
    control,
    watch,
    setValue,
    formState: { errors },
  } = form;
  const category = watch("category");

  const onSubmit = (values: UserCreateFormValues) => {
    mutation.mutate(toUserCreate(values), {
      onSuccess: () => {
        toast.success("Пользователь создан");
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
          Добавить пользователя
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новый пользователь</DialogTitle>
          <DialogDescription>Заполните данные учётной записи и сохраните.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <FormField id="full_name" label={L("full_name")} required error={errors.full_name?.message}>
            {(aria) => <Input {...aria} {...register("full_name")} maxLength={255} autoFocus />}
          </FormField>

          <FormField id="username" label={L("username")} required error={errors.username?.message}>
            {(aria) => (
              <Input {...aria} {...register("username")} maxLength={150} autoComplete="username" />
            )}
          </FormField>

          <FormField
            id="email"
            label={L("email")}
            error={errors.email?.message}
            description="Опционально, формат имя@npuu.uz"
          >
            {(aria) => (
              <Input
                {...aria}
                {...register("email")}
                type="email"
                maxLength={255}
                placeholder="ivanov@npuu.uz"
              />
            )}
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

          {/* Контракт называет колонку "Хеш пароля" (password_hash, наружу не выходит,
             все API-флаги false) — на форме показываем пользователю осмысленную
             подпись "Пароль" для сырого ввода, а не подпись колонки. */}
          <FormField id="password" label="Пароль" required error={errors.password?.message}>
            {(aria) => (
              <PasswordInput {...aria} {...register("password")} autoComplete="new-password" />
            )}
          </FormField>

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
