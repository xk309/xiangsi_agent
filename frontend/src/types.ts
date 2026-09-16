export type DailyLabel = {
  evaluation_concentration: number;
  air_quality_subindex: number;
  band: number;
  is_above_threshold: boolean;
  is_above_index_table: boolean;
};
export type Batch = {
  forecast_start_time: string;
  dates: string[];
  incomplete_dates: string[];
  has_full_seven_days: boolean;
};
export type Health = {
  database_ready: boolean;
  weather_ready: boolean;
  model_configured: boolean;
  model_name: string;
  warning: string;
};
export type Images = Record<string, string>;
export type ProcessFeature = {
  grid_id: string;
  pollutant_name: string;
  pattern: string;
  directions: string[];
  peak_positions: number[];
  peak_concentration: number;
  exceedance_days: number;
  longest_run: number;
  has_stable_stage: boolean;
};
export type DailyReview = {
  relative_day: number;
  wind_score: number;
  pressure_score: number;
  temperature_humidity_score: number;
  circulation_500_score: number;
  similarities: string;
  differences: string;
  shanghai_position: string;
};
export type Candidate = {
  history_start_date: string;
  history_end_date: string;
  coarse_rank: number;
  fine_rank: number;
  final_rank?: number;
  numeric_score: number;
  daily_band_score: number;
  transition_score: number | null;
  process_score: number | null;
  coarse_pollutant_score: number;
  coarse_score: number;
  fine_pollutant_score: number;
  meteorology_label_score: number;
  meteorology_score: number;
  fine_score: number;
  image_score?: number;
  final_score?: number;
  historical_labels: DailyLabel[][][];
  historical_values: number[][][];
  historical_weather: number[][][];
  historical_weather_labels: string[][];
  historical_features: ProcessFeature[];
  images?: Images;
  is_low_similarity: boolean;
  review_error?: string;
  review_cache_key?: string;
  review?: {
    summary: string;
    days: DailyReview[];
    evolution_score: number | null;
  };
};
export type ResidualRow = {
  station_id: number;
  station_name: string;
  pollutant_name: string;
  valid_date: string;
  history_date: string;
  current_forecast: number;
  historical_observed: number;
  historical_forecast: number;
  residual: number;
};
export type Task = {
  task_id: string;
  status: string;
  stage: string;
  progress: number;
  dates: string[];
  forecast_start_time: string;
  warning: string;
  model_name: string;
  created_at: string;
  candidates: Candidate[];
  current_values?: number[][][];
  current_weather?: number[][][];
  current_weather_labels?: string[][];
  current_features?: ProcessFeature[];
  current_labels?: DailyLabel[][][];
  current_images?: Images;
  result_message?: string;
  error?: string;
  baseline?: {
    qualified_window_count: number;
    skipped: Record<string, number>;
    change_baseline: { source: string; sample_count: number };
  };
  residuals?: {
    reason: string;
    comparability_assumption: string;
    rows: ResidualRow[];
  };
  review_failures: {
    history_start_date: string;
    attempt: number;
    reason: string;
  }[];
};
export type TaskSummary = {
  task_id: string;
  status: string;
  stage: string;
  window_start_date: string;
  window_end_date: string;
  created_at: string;
};
