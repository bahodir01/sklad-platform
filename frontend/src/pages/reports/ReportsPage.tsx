import { useState } from "react";
import { PageHeader } from "@/shared/ui/page-header";
import { cn } from "@/shared/lib/utils";
import { BalancesReport } from "./BalancesReport";
import { UnpurchasedReport } from "./UnpurchasedReport";
import { MovementsReport } from "./MovementsReport";
import { CashflowReport } from "./CashflowReport";

type Tab = "balances" | "unpurchased" | "movements" | "cashflow";

const TABS: { id: Tab; label: string }[] = [
  { id: "balances", label: "Остатки" },
  { id: "unpurchased", label: "Недокупленное" },
  { id: "movements", label: "История движений" },
  { id: "cashflow", label: "ДДС (деньги)" },
];

/**
 * Отчёты (М6, admin, §8). Четыре отчёта в табах: остатки, недокупленное,
 * история движений, ДДС. Каждый — свои фильтры, таблица и экспорт xlsx/pdf.
 * Активный отчёт рендерится один — чтобы не бить бэкенд всеми запросами разом.
 */
export function ReportsPage() {
  const [tab, setTab] = useState<Tab>("balances");

  return (
    <section>
      <PageHeader
        breadcrumb="Отчёты"
        title="Отчёты"
        subtitle="Остатки, недокупленное, история движений и движение денежных средств"
      />

      <div className="mb-5 flex flex-wrap gap-1 border-b" role="tablist" aria-label="Отчёты">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              tab === t.id
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "balances" && <BalancesReport />}
      {tab === "unpurchased" && <UnpurchasedReport />}
      {tab === "movements" && <MovementsReport />}
      {tab === "cashflow" && <CashflowReport />}
    </section>
  );
}
