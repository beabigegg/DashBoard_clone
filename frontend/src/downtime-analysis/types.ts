export interface DowntimeKpiShape {
  total_hours: number;
  udt_hours: number;
  sdt_hours: number;
  egt_hours: number;
  event_count: number;
  avg_event_min: number;
}

export interface DailyTrendRow {
  date: string;
  udt_hours: number;
  sdt_hours: number;
  egt_hours: number;
  total_hours: number;
}

export interface BigCategoryRow {
  category: string;
  hours: number;
  event_count: number;
  pct: number;
}

export interface TopReasonRow {
  reason: string;
  status: string;
  hours: number;
  event_count: number;
  avg_min: number;
}

export interface EquipmentDetailRow {
  resource_id: string;
  resource_name: string | null;
  workcenter: string | null;
  family: string | null;
  udt_hours: number;
  sdt_hours: number;
  egt_hours: number;
  total_hours: number;
  event_count: number;
  top_reason: string | null;
}

export interface JobEnrichment {
  job_order_name: string | null;
  job_model: string | null;
  symptom: string | null;
  cause: string | null;
  repair: string | null;
  wait_min: number | null;
  repair_min: number | null;
  handler: string | null;
  match_ambiguous: boolean;
}

export type MatchSource = 'jobid' | 'overlap' | 'none';

export interface EventDetailRow {
  event_id: string;
  resource_id: string;
  resource_name: string | null;
  status: string;
  reason: string | null;
  category: string;
  start_ts: string;
  end_ts: string;
  hours: number;
  match_source: MatchSource;
  job: JobEnrichment | null;
}

export interface Pagination {
  page: number;
  page_size: number;
  total_rows: number;
  total_pages: number;
}

export interface FilterOptions {
  workcenter_groups: string[];
  families: string[];
  resources: string[];
  package_groups: string[];
  big_categories: string[];
  reasons: string[];
}

export interface FilterState {
  workcenter_groups: string[];
  families: string[];
  resource_ids: string[];
  package_groups: string[];
  big_categories: string[];
  status_types: string[];
  start_date: string;
  end_date: string;
  granularity: string;
  is_production: boolean;
  is_key: boolean;
  is_monitor: boolean;
}
