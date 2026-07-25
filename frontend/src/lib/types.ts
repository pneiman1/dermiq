// TypeScript mirror of the API's Pydantic response models.
// Monetary / rate fields are `string` — they arrive as Decimal-as-string and must
// be parsed with decimal.js (see lib/money.ts) to avoid precision loss. Counts are
// `number`; dates are ISO `string`; nullable fields are `| null`.

export type Priority = "urgent" | "high" | "medium" | "low";
export type RecencyTier = "active" | "lapsing" | "lapsed" | "dormant";
export type LtvTier = "vip" | "high" | "standard" | "low" | "unknown";
export type ChannelHealth =
  | "organic"
  | "excellent"
  | "healthy"
  | "marginal"
  | "unprofitable";

export interface Health {
  status: string;
  snowflake_reachable: boolean;
}

export interface Tenant {
  tenant_id: string;
  tenant_name: string;
}

export interface RevenueDailyRow {
  date_day: string;
  completed_visits: number;
  net_revenue: string;
  avg_ticket: string | null;
  rev_injectable: string;
  rev_device: string;
  rev_skincare: string;
  rev_membership: string;
  rev_surgical: string;
  rev_consult: string;
  line_items: number;
  distinct_patients: number;
  distinct_providers: number;
  new_patients: number;
  scheduled_appointments: number;
  no_show_count: number;
  cancelled_count: number;
  no_show_rate: string | null;
}

export interface ProviderScorecardRow {
  provider_id: string;
  provider_name: string;
  provider_role: string;
  specialties: string | null;
  visits_ttm: number;
  revenue_ttm: string;
  avg_ticket_ttm: string | null;
  revenue_per_hour_ttm: string | null;
  cross_sell_rate_ttm: string | null;
  skincare_attach_rate_ttm: string | null;
  productive_hours_ttm: string;
  active_days_ttm: number;
  total_visits_alltime: number;
  total_revenue_alltime: string;
  last_visit_date: string | null;
  revenue_rank: number;
}

export interface ProviderRevenueDailyRow {
  provider_id: string;
  date_key: string;
  visit_count: number;
  total_revenue: string;
  avg_ticket: string | null;
  productive_hours: string;
  revenue_per_hour: string | null;
  cross_sell_rate: string | null;
  skincare_attach_rate: string | null;
}

export interface ChannelAttributionRow {
  acquisition_channel: string;
  patients_acquired_ttm: number;
  total_revenue_ttm: string;
  avg_ltv_run_rate_ttm: string | null;
  vip_count: number;
  high_count: number;
  standard_count: number;
  low_count: number;
  unknown_count: number;
  total_patients_alltime: number;
  spend_ttm: string;
  cac_ttm: string | null;
  ltv_cac_ratio_ttm: string | null;
  channel_health: ChannelHealth;
}

export interface AcquisitionByMonthRow {
  month_start: string;
  channel: string;
  patient_count: number;
}

export interface RecallQueueRow {
  patient_id: string;
  first_name: string;
  last_name: string;
  primary_email: string | null;
  primary_phone: string | null;
  acquisition_channel: string;
  last_visit_date: string;
  recency_days: number;
  recency_tier: RecencyTier;
  total_visits: number;
  total_revenue: string;
  annual_revenue_run_rate: string | null;
  ltv_tier: LtvTier;
  last_provider_id: string | null;
  last_provider_name: string | null;
  recall_priority: Priority;
}

export interface DispositionDailyRow {
  day: string;
  completed: number;
  no_show: number;
  cancelled: number;
  total: number;
  no_show_rate: string | null;
  cancel_rate: string | null;
}

export interface FlowByHourRow {
  dow: number; // ISO day-of-week: 1=Mon … 7=Sun
  hour: number; // 0 … 23
  appointment_count: number;
  completed_count: number;
}

export interface PatientSegment {
  cluster_id: number;
  cluster_name: string;
  patient_count: number;
  avg_ltv: string;
  avg_annual_run_rate: string;
  dominant_category: string;
  top_provider_name: string | null;
  avg_recency_days: number | null;
  urgent_recall_count: number;
  active_patient_count: number;
}

export interface PatientSegmentMember {
  patient_id: string;
  first_name: string;
  last_name: string;
  total_revenue: string;
  annual_revenue_run_rate: string | null;
  ltv_tier: string;
  recency_tier: string | null;
  last_visit_date: string | null;
  dominant_provider_name: string | null;
}

export interface NoShowByProviderRow {
  provider_id: string;
  provider_name: string;
  scheduled: number;
  completed: number;
  no_show: number;
  cancelled: number;
  no_show_rate: string | null;
  cancel_rate: string | null;
}

export interface PatientTierSummary {
  active: number;
  lapsing: number;
  lapsed: number;
  dormant: number;
  total: number;
}

export interface RecallSummary {
  total: number;
  urgent: number;
  high: number;
  medium: number;
  low: number;
  avg_recency_days: number | null;
  max_last_visit_date: string | null;
}

// ----- inventory (chunk-11) -----
export interface InventorySummary {
  total_inventory_value: string;
  waste_rate_ttm: string | null;
  waste_value_ttm: string;
  items_below_par: number;
  expiring_30d_count: number;
  expiring_30d_value: string;
}

export interface InventoryStatusRow {
  sku: string;
  sku_name: string;
  service_code: string;
  category: string;
  unit_of_measure: string;
  on_hand_quantity: string;
  par_level: string;
  unit_cost: string;
  on_hand_value: string;
  units_consumed_ttm: string;
  days_of_supply: string | null;
  oldest_lot_expiry: string | null;
  last_transaction_at: string | null;
  on_hand_lots: string | null;
  stock_status: "out" | "low" | "adequate" | "overstock";
}

export interface TrueMarginRow {
  service_code: string;
  service_name: string;
  service_category: string;
  transactions_ttm: number;
  units_consumed_ttm: string;
  revenue_ttm: string;
  consumables_cost_ttm: string;
  true_margin_ttm: string;
  true_margin_pct: string | null;
  catalog_margin_pct: string | null;
}

export interface WasteBySkuRow {
  service_code: string;
  service_name: string;
  category: string;
  consumed_units_ttm: string;
  waste_units_ttm: string;
  waste_cost_ttm: string;
  waste_rate: string | null;
}

export interface ExpiringItem {
  lot_id: string;
  sku: string;
  sku_name: string;
  category: string;
  lot_number: string;
  expiry_date: string;
  days_to_expiry: number;
  quantity_remaining: string;
  estimated_value_at_risk: string;
  urgency_level: "critical" | "warning" | "watch" | "future";
}
