import type { ReactNode } from "react";
import { Label } from "./label";
import { cn } from "@/shared/lib/utils";

export interface FieldAria {
  id: string;
  "aria-invalid"?: true;
  "aria-required"?: true;
  "aria-describedby"?: string;
}

interface FormFieldProps {
  id: string;
  label: string;
  required?: boolean;
  error?: string;
  /** Поясняющий текст под контролом (напр. про «Склад списания»). */
  description?: string;
  /** true — метка идёт справа от контрола (чекбоксы). */
  inline?: boolean;
  children: (aria: FieldAria) => ReactNode;
}

/**
 * Обёртка поля с доступностью (§11): видимый label с htmlFor, `*` + aria-required
 * у обязательных, aria-invalid + aria-describedby на текст ошибки рядом с полем.
 */
export function FormField({
  id,
  label,
  required,
  error,
  description,
  inline,
  children,
}: FormFieldProps) {
  const errorId = error ? `${id}-error` : undefined;
  const descId = description ? `${id}-desc` : undefined;
  const describedBy = [descId, errorId].filter(Boolean).join(" ") || undefined;

  const aria: FieldAria = {
    id,
    ...(error ? { "aria-invalid": true as const } : {}),
    ...(required ? { "aria-required": true as const } : {}),
    ...(describedBy ? { "aria-describedby": describedBy } : {}),
  };

  const labelEl = (
    <Label htmlFor={id}>
      {label}
      {required ? (
        <span className="ml-0.5 text-destructive" aria-hidden="true">
          *
        </span>
      ) : null}
    </Label>
  );

  return (
    <div className={cn("space-y-1.5", inline && "space-y-0")}>
      {inline ? (
        <div className="flex items-center gap-2">
          {children(aria)}
          {labelEl}
        </div>
      ) : (
        <>
          {labelEl}
          {children(aria)}
        </>
      )}
      {description ? (
        <p id={descId} className="text-sm text-muted-foreground">
          {description}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-sm font-medium text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
