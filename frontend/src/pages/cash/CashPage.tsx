import { useCashDesks } from "@/entities/cash/api/queries";
import { CASH_DESK_LABEL } from "@/entities/cash/model/types";
import { IncomeForm } from "@/features/cash/income-form/IncomeForm";
import { PageHeader } from "@/shared/ui/page-header";
import { KpiCard } from "@/shared/ui/kpi-card";
import { Card } from "@/shared/ui/card";
import { Skeleton } from "@/shared/ui/skeleton";
import { Button } from "@/shared/ui/button";
import { formatMoneyStr } from "@/shared/lib/format";

/**
 * Кассы (М5, admin, §7.2). Балансы обеих касс (учителей/работников, GET
 * /cash/desks) + форма прихода. Расход проводит сотрудник у себя («Мои расходы»);
 * здесь его нет — деньги тратит не администратор (§7.3).
 */
export function CashPage() {
  const desks = useCashDesks();

  return (
    <section>
      <PageHeader
        breadcrumb="Деньги › Кассы"
        title="Кассы"
        subtitle="Балансы касс и пополнение (приход проводит только администратор)"
      />

      <div className="mb-6 grid grid-cols-1 gap-3.5 sm:grid-cols-2">
        {desks.isLoading ? (
          <>
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-24 w-full rounded-xl" />
          </>
        ) : desks.isError ? (
          <Card className="p-5 sm:col-span-2">
            <p className="mb-3 text-sm text-muted-foreground">Не удалось загрузить балансы касс.</p>
            <Button variant="outline" size="sm" onClick={() => desks.refetch()}>
              Повторить
            </Button>
          </Card>
        ) : (
          (desks.data ?? []).map((d) => (
            <KpiCard
              key={d.id}
              label={CASH_DESK_LABEL[d.type]}
              value={formatMoneyStr(d.balance)}
              meta="текущий баланс"
              dot="accent"
              accent
            />
          ))
        )}
      </div>

      <Card className="max-w-3xl p-5">
        <h2 className="mb-4 text-sm font-semibold">Пополнить кассу</h2>
        <IncomeForm />
      </Card>
    </section>
  );
}
