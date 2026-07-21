import { z } from "zod";

/**
 * Тело PUT /admin/integrations/{kind} (спека15 §5а): `secret` — сырой текст
 * (bot-токен / API-ключ), контракт не задаёт длину для `secret_encrypted`
 * (`text NULL`, шифротекст) — реальная проверка формата/валидности идёт на
 * сервере (Telegram `getMe` / формат `sk-ant-...`). На клиенте — только
 * «поле не пустое», чтобы не гонять заведомо пустой ввод на сервер.
 */
export const integrationSecretSchema = z.object({
  secret: z.string().min(1, "Введите секрет"),
});

export type IntegrationSecretFormValues = z.infer<typeof integrationSecretSchema>;
