import { useCreateCatalog, useUpdateCatalog } from "@/shared/api/catalog-hooks";
import type { WarehouseCreate, WarehouseRead, WarehouseUpdate } from "../model/types";

export function useCreateWarehouse() {
  return useCreateCatalog<WarehouseRead, WarehouseCreate>("warehouses");
}

export function useUpdateWarehouse() {
  return useUpdateCatalog<WarehouseRead, WarehouseUpdate>("warehouses");
}
