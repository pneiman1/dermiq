import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

/** Cached "Data through" date — max(date_day) from /revenue/daily, shared by all tabs. */
export function useMaxDataDate() {
  return useQuery({ queryKey: ["max-data-date"], queryFn: api.getMaxDataDate });
}
