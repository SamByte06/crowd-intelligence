/** TypeScript types for the application. */

export interface Venue {
  id: string;
  name: string;
  description?: string;
  location?: string;
  usable_area_sqm?: number;
  max_capacity?: number;
  density_per_sqm: number;
  warning_threshold: number;
  critical_threshold: number;
  current_occupancy: number;
  total_entries: number;
  total_exits: number;
  baseline_established: boolean;
  baseline_established_at?: string;
  baseline_established_by?: string;
  effective_capacity?: number;
  capacity_is_estimated: boolean;
  timezone: string;
  is_active: boolean;
  monitoring_active?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface Gate {
  id: string;
  venue_id: string;
  display_name: string;
  gate_type: 'ENTRY' | 'EXIT';
  camera_source_type: 'WEBCAM' | 'VIDEO_FILE' | 'RTSP' | 'HTTP';
  camera_source: string;
  line_start_x: number;
  line_start_y: number;
  line_end_x: number;
  line_end_y: number;
  counting_direction: string;
  confidence_threshold: number;
  frame_skip: number;
  is_enabled: boolean;
  status: string;
  last_frame_at?: string;
  last_count_at?: string;
  error_message?: string;
  reconnect_attempts: number;
  entry_count: number;
  exit_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface Occupancy {
  venue_id: string;
  current_occupancy: number;
  effective_capacity?: number;
  capacity_is_estimated: boolean;
  remaining_capacity?: number;
  occupancy_percentage?: number;
  total_entries: number;
  total_exits: number;
  baseline_established: boolean;
  occupancy_is_uncertain?: boolean;
  reconciliation_needed?: boolean;
  last_updated?: string;
}

export interface FlowRate {
  venue_id: string;
  window_seconds: number;
  entry_rate_per_min: number;
  exit_rate_per_min: number;
  net_inflow_per_min: number;
  total_entries_in_window: number;
  total_exits_in_window: number;
  measured_at: string;
}

export interface ForecastPoint {
  horizon_minutes: number;
  forecast_occupancy: number;
  is_above_warning: boolean;
  is_above_critical: boolean;
  is_above_capacity: boolean;
}

export interface Forecast {
  venue_id: string;
  current_occupancy: number;
  net_inflow_rate: number;
  effective_capacity?: number;
  time_to_warning_minutes?: number;
  time_to_critical_minutes?: number;
  time_to_capacity_minutes?: number;
  forecasts: ForecastPoint[];
  data_quality: string;
  measured_at: string;
}

export interface Alert {
  id: string;
  venue_id: string;
  severity: 'NORMAL' | 'WARNING' | 'CRITICAL' | 'DATA_UNRELIABLE';
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';
  title: string;
  message: string;
  recommended_action?: string;
  occupancy_at_trigger?: number;
  capacity_at_trigger?: number;
  entry_rate_at_trigger?: number;
  exit_rate_at_trigger?: number;
  forecast_occupancy?: number;
  trigger_reason?: string;
  alert_type_key?: string;
  triggered_at: string;
  acknowledged_at?: string;
  acknowledged_by?: string;
  resolved_at?: string;
  resolved_by?: string;
  resolution_note?: string;
}

export interface DashboardState {
  venue?: Venue;
  monitoring_active?: boolean;
  occupancy: Occupancy;
  flow: FlowRate;
  forecast: Forecast;
  alerts: Alert[];
  gates: Gate[];
  camera_health: any[];
  timestamp: string;
}

export interface OccupancySnapshot {
  timestamp: string;
  occupancy: number;
  entry_rate: number;
  exit_rate: number;
  net_inflow: number;
  capacity_utilization?: number;
}
