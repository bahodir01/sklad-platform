import { useCreateCatalog, useUpdateCatalog } from "@/shared/api/catalog-hooks";
import type { ProductCreate, ProductRead, ProductUpdate } from "../model/types";

export function useCreateProduct() {
  return useCreateCatalog<ProductRead, ProductCreate>("products");
}

export function useUpdateProduct() {
  return useUpdateCatalog<ProductRead, ProductUpdate>("products");
}
