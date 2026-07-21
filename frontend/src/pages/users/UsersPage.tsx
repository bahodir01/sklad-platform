import { useEffect, useState } from "react";
import { useUsers } from "@/entities/user/api/queries";
import { userFields } from "@/entities/user/model/fields";
import type { User } from "@/entities/user/model/types";
import { fieldByName } from "@/shared/lib/field-descriptor";
import { usePageParams } from "@/shared/lib/use-page-params";
import { CatalogScreen } from "@/shared/ui/catalog-screen";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { ActiveBadge } from "@/shared/ui/catalog-status-badge";
import { Label } from "@/shared/ui/label";
import { Input } from "@/shared/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { RoleBadge } from "@/entities/user/ui/RoleBadge";
import { categoryLabel } from "@/entities/user/lib/category-label";
import { roleLabel } from "@/shared/config/roles";
import { UserCreateDialog } from "@/features/users/user-form/UserCreateDialog";
import { UserEditDialog } from "@/features/users/user-form/UserEditDialog";
import { ResetPasswordDialog } from "@/features/users/reset-password/ResetPasswordDialog";

const L = (name: string) => fieldByName(userFields, name).label;
const ALL = "__all__";
const ROLE_OPTIONS = ["admin", "teacher", "worker"] as const;

/**
 * Пользователи → /admin/users (М7, ОВ-12, backend §14). Только admin
 * (RequireRole в роутере). Фильтры — те, что реально реализованы на бэке:
 * role, is_active, q (ФИО/логин/email, ilike). Деактивация/реактивация —
 * через чекбокс "Активен" в диалоге правки (self_deactivation_forbidden на
 * себе задизейблен там же), отдельной кнопки "В архив" нет — DELETE и общий
 * archive-паттерн справочников здесь неприменимы (у users нет status).
 */
export function UsersPage() {
  const { page, size, get, setFilter, setPage } = usePageParams();
  const role = get("role");
  const isActive = get("is_active");
  const qParam = get("q");

  // Поиск — с локальным дебаунсом 400мс, чтобы не дёргать API на каждый символ.
  const [qInput, setQInput] = useState(qParam ?? "");
  useEffect(() => setQInput(qParam ?? ""), [qParam]);
  useEffect(() => {
    const t = setTimeout(() => {
      if (qInput !== (qParam ?? "")) setFilter("q", qInput || undefined);
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);

  const query = useUsers({ page, size, role, is_active: isActive, q: qParam });
  const data = query.data;

  const columns: Column<User>[] = [
    { key: "full_name", header: L("full_name"), render: (r) => r.full_name },
    {
      key: "username",
      header: L("username"),
      render: (r) => <span className="font-mono text-[12.5px]">{r.username}</span>,
    },
    { key: "email", header: L("email"), render: (r) => r.email ?? "—" },
    { key: "role", header: L("role"), render: (r) => <RoleBadge role={r.role} /> },
    { key: "category", header: L("category"), render: (r) => categoryLabel(r.category) },
    {
      key: "is_active",
      header: L("is_active"),
      render: (r) => <ActiveBadge isActive={r.is_active} />,
    },
  ];

  return (
    <CatalogScreen
      title="Пользователи"
      actions={<UserCreateDialog />}
      filters={
        <>
          <div className="flex items-center gap-2">
            <Label htmlFor="filter-role" className="text-muted-foreground">
              Роль
            </Label>
            <Select
              value={role ?? ALL}
              onValueChange={(v) => setFilter("role", v === ALL ? undefined : v)}
            >
              <SelectTrigger id="filter-role" className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Все</SelectItem>
                {ROLE_OPTIONS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {roleLabel(r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <Label htmlFor="filter-is_active" className="text-muted-foreground">
              Статус
            </Label>
            <Select
              value={isActive ?? ALL}
              onValueChange={(v) => setFilter("is_active", v === ALL ? undefined : v)}
            >
              <SelectTrigger id="filter-is_active" className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Все</SelectItem>
                <SelectItem value="true">Активные</SelectItem>
                <SelectItem value="false">В архиве</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <Label htmlFor="filter-q" className="text-muted-foreground">
              Поиск
            </Label>
            <Input
              id="filter-q"
              className="w-56"
              placeholder="ФИО, логин или email"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
            />
          </div>
        </>
      }
      pagination={
        data ? (
          <TablePagination
            page={data.page}
            size={data.size}
            total={data.total}
            pages={data.pages}
            onPageChange={setPage}
          />
        ) : null
      }
    >
      <DataTable
        caption="Пользователи системы"
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(r) => r.id}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => query.refetch()}
        emptyText="Пользователей пока нет"
        emptyAction={<UserCreateDialog />}
        rowActions={(r) => (
          <>
            <UserEditDialog row={r} />
            <ResetPasswordDialog row={r} />
          </>
        )}
      />
    </CatalogScreen>
  );
}
