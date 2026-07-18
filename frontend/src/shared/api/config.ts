/**
 * База API — относительный /api/v1 (префикс из backend core/config.py:21).
 *
 * Всегда относительный: в dev его перехватывает Vite-прокси (vite.config.ts),
 * в prod — один origin за nginx (архитектура §2). Кросс-оригинного VITE_API_URL
 * намеренно нет (Ф-7): это снимает вопросы SameSite/Secure у refresh-cookie.
 */
export const API_BASE = "/api/v1";
