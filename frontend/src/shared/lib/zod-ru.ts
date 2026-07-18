import { z } from "zod";

/**
 * Русская локализация сообщений Zod по умолчанию. Клиентская валидация —
 * подсказка; истину по правилам всё равно обеспечивает бэкенд (§10).
 */
const ruErrorMap: z.ZodErrorMap = (issue, ctx) => {
  switch (issue.code) {
    case z.ZodIssueCode.too_small:
      if (issue.type === "string") {
        return {
          message: issue.minimum === 1 ? "Обязательное поле" : `Минимум ${issue.minimum} символ(ов)`,
        };
      }
      return { message: `Значение слишком мало` };
    case z.ZodIssueCode.too_big:
      if (issue.type === "string") {
        return { message: `Не более ${issue.maximum} символ(ов)` };
      }
      return { message: `Значение слишком велико` };
    case z.ZodIssueCode.invalid_type:
      if (issue.received === "undefined" || issue.received === "null") {
        return { message: "Обязательное поле" };
      }
      return { message: "Неверное значение" };
    case z.ZodIssueCode.invalid_enum_value:
      return { message: "Выберите значение из списка" };
    default:
      return { message: ctx.defaultError };
  }
};

export function installZodRu(): void {
  z.setErrorMap(ruErrorMap);
}
