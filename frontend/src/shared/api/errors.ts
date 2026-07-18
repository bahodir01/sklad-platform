import type { ErrorEnvelope, FieldValidationError } from "./types";

/**
 * ApiError — единый носитель ответа {code, message, details} (§10).
 *
 * `message` — уже готовый русский текст с бэкенда (core/exceptions.py, §4.2 ТЗ)
 * и НИКОГДА не переписывается на клиенте: дублировать формулировки — значит
 * завести второй словарь ошибок, который разойдётся с бэкендом.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, envelope: ErrorEnvelope) {
    super(envelope.message);
    this.name = "ApiError";
    this.status = status;
    this.code = envelope.code;
    this.details = envelope.details ?? {};
  }

  /** Ошибка сети / нераспознанный ответ (не {code,message,details}). */
  static network(message = "Не удалось связаться с сервером"): ApiError {
    return new ApiError(0, { code: "network_error", message, details: {} });
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }

  /**
   * Полевые ошибки валидации (422 с details.errors). Пусто, если это доменная
   * ошибка (duplicate и т.п.) — она несёт готовый текст в message, не в поля.
   */
  fieldErrors(): FieldValidationError[] {
    const errors = (this.details as { errors?: unknown }).errors;
    if (!Array.isArray(errors)) return [];
    return errors.filter(
      (e): e is FieldValidationError =>
        typeof e === "object" && e !== null && Array.isArray((e as FieldValidationError).loc),
    );
  }
}

/** true для 4xx — Query не должен их ретраить (§7.1). */
export function isClientError(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 400 && error.status < 500;
}
