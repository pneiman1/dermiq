// Typed API client. One function per endpoint. Injects the X-Tenant-ID header and
// the configured base URL. Throws on non-2xx.
import type {
  AcquisitionByMonthRow,
  ChannelAttributionRow,
  DispositionDailyRow,
  FlowByHourRow,
  Health,
  NoShowByProviderRow,
  PatientSegment,
  PatientSegmentMember,
  PatientTierSummary,
  Priority,
  ProviderRevenueDailyRow,
  ProviderScorecardRow,
  RecallQueueRow,
  RecallSummary,
  RevenueDailyRow,
  Tenant,
  ExpiringItem,
  InventoryStatusRow,
  InventorySummary,
  TrueMarginRow,
  WasteBySkuRow,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const TENANT = process.env.NEXT_PUBLIC_TENANT_ID ?? "del_mar";

type Params = Record<string, string | number | undefined>;

function qs(params?: Params): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function get<T>(path: string, params?: Params): Promise<T> {
  const res = await fetch(`${BASE}${path}${qs(params)}`, {
    headers: { "X-Tenant-ID": TENANT },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API ${res.status} ${res.statusText} on ${path}`);
  }
  return (await res.json()) as T;
}

interface DateRange {
  startDate?: string;
  endDate?: string;
}

export const api = {
  getHealth: () => get<Health>("/health"),
  getTenant: () => get<Tenant>("/meta/tenant"),

  getRevenueDaily: (p?: DateRange) =>
    get<RevenueDailyRow[]>("/revenue/daily", { start_date: p?.startDate, end_date: p?.endDate }),

  // The freshest data point in the warehouse — the single anchor for "Data through".
  getMaxDataDate: async (): Promise<string | null> => {
    const today = new Date();
    const start = new Date(today);
    start.setDate(start.getDate() - 120);
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    const rows = await get<RevenueDailyRow[]>("/revenue/daily", {
      start_date: iso(start),
      end_date: iso(today),
    });
    if (rows.length === 0) return null;
    return rows.reduce((m, r) => (r.date_day > m ? r.date_day : m), rows[0].date_day);
  },

  getProviderScorecard: () => get<ProviderScorecardRow[]>("/providers/scorecard"),

  getProviderRevenueDaily: (providerId: string, p?: DateRange) =>
    get<ProviderRevenueDailyRow[]>(`/providers/${providerId}/revenue-daily`, {
      start_date: p?.startDate,
      end_date: p?.endDate,
    }),

  getChannelAttribution: () => get<ChannelAttributionRow[]>("/channels/attribution"),

  getAcquisitionByMonth: (months?: number) =>
    get<AcquisitionByMonthRow[]>("/channels/acquisition-by-month", { months }),

  getRecallQueue: (p?: { limit?: number; minPriority?: Priority }) =>
    get<RecallQueueRow[]>("/recall/queue", { limit: p?.limit, min_priority: p?.minPriority }),

  getRecallSummary: () => get<RecallSummary>("/recall/summary"),

  getFlowDispositions: (p?: DateRange) =>
    get<DispositionDailyRow[]>("/flow/dispositions", { start_date: p?.startDate, end_date: p?.endDate }),

  getFlowByHour: (p?: DateRange) =>
    get<FlowByHourRow[]>("/flow/by-hour", { start_date: p?.startDate, end_date: p?.endDate }),

  getNoShowByProvider: () => get<NoShowByProviderRow[]>("/flow/no-show-by-provider"),

  getPatientTierSummary: () => get<PatientTierSummary>("/patients/tier-summary"),

  getSegments: () => get<PatientSegment[]>("/segments"),

  getSegmentMembers: (clusterId: number, limit?: number) =>
    get<PatientSegmentMember[]>(`/segments/${clusterId}/members`, { limit }),

  // Inventory tab (chunk-11).
  getInventorySummary: () => get<InventorySummary>("/inventory/summary"),
  getInventoryStatus: () => get<InventoryStatusRow[]>("/inventory/status"),
  getInventoryWaste: (limit?: number) => get<WasteBySkuRow[]>("/inventory/waste", { limit }),
  getInventoryTrueMargin: () => get<TrueMarginRow[]>("/inventory/true-margin"),
  getInventoryExpiring: (days?: number) => get<ExpiringItem[]>("/inventory/expiring", { days }),
};
