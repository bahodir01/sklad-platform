import { useIntegrations } from "@/entities/integration/api/queries";
import type { IntegrationKind } from "@/entities/integration/model/types";
import { IntegrationCard } from "@/features/integrations/integration-card/IntegrationCard";
import { PageHeader } from "@/shared/ui/page-header";
import { Card, CardContent } from "@/shared/ui/card";
import { Button } from "@/shared/ui/button";

const CARDS: { kind: IntegrationKind; title: string; hint: string }[] = [
  {
    kind: "telegram",
    title: "Telegram-бот",
    hint: "Токен от @BotFather в Telegram: создайте бота командой /newbot и вставьте выданный токен.",
  },
  {
    kind: "ai_search",
    title: "ИИ-поиск товаров",
    hint: "API-ключ Google Gemini (aistudio.google.com/apikey) — используется для поиска товаров по смыслу, если сотрудник написал название на другом языке.",
  },
];

/**
 * Интеграции (спека15 §5а, admin). Единое место для внешних ключей: бот
 * Telegram (заявки/расходы через чат вместо веб-формы) и ИИ-поиск товара по
 * смыслу (§3a). Одна строка на kind в `integration_settings`, секрет никогда
 * не приходит с сервера в открытом виде — только маска (`masked_secret`).
 */
export function IntegrationsPage() {
  const query = useIntegrations();
  const byKind = (kind: IntegrationKind) => query.data?.find((i) => i.kind === kind);

  return (
    <section>
      <PageHeader
        breadcrumb="Администрирование › Интеграции"
        title="Интеграции"
        subtitle="Ключи Telegram-бота и ИИ-поиска товаров — единое место настройки"
      />

      {query.isError ? (
        <Card className="p-5">
          <CardContent className="p-0">
            <p className="mb-3 text-sm text-muted-foreground">Не удалось загрузить интеграции.</p>
            <Button variant="outline" size="sm" onClick={() => query.refetch()}>
              Повторить
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {CARDS.map((c) => (
            <IntegrationCard
              key={c.kind}
              kind={c.kind}
              title={c.title}
              hint={c.hint}
              integration={byKind(c.kind)}
              isLoading={query.isLoading}
            />
          ))}
        </div>
      )}
    </section>
  );
}
