/**
 * Реэкспорт синглтона access-токена под именем из архитектуры (§6).
 * Низкоуровневая реализация — в shared/api/token-store.ts, чтобы client.ts
 * не импортировал вверх по слоям FSD.
 */
export { tokenStore } from "@/shared/api/token-store";
