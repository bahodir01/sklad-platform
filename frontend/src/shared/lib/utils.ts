import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Слияние классов Tailwind (shadcn-конвенция). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
