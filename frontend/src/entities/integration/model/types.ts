import type { components } from "@/shared/api/schema";

/**
 * Спека15 §5а: таблица `integration_settings`, одна строка на тип интеграции.
 * `kind` в контракте — обычный varchar (не enum, набор может расшириться), но
 * бэкенд §5а фиксирует ровно два значения — сужаем строкой-литералом на
 * клиенте для безопасной адресации `PUT /admin/integrations/{kind}`.
 */
export type IntegrationKind = "telegram" | "ai_search";

/** GET /admin/integrations — секрет только маской, никогда не в открытом виде. */
export type Integration = components["schemas"]["IntegrationRead"];

/** PUT /admin/integrations/{kind} — новый секрет в открытом виде (входной параметр). */
export type IntegrationUpdate = components["schemas"]["IntegrationUpdate"];
