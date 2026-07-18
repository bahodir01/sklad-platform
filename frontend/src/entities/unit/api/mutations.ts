import { useCreateCatalog, useUpdateCatalog } from "@/shared/api/catalog-hooks";
import type { UnitCreate, UnitRead, UnitUpdate } from "../model/types";

export function useCreateUnit() {
  return useCreateCatalog<UnitRead, UnitCreate>("units");
}

export function useUpdateUnit() {
  return useUpdateCatalog<UnitRead, UnitUpdate>("units");
}
