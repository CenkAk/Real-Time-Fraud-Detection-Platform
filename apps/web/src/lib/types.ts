export type Decision = "APPROVE" | "MANUAL_REVIEW" | "BLOCK";

export interface Overview {
  transactions_24h: number;
  decisions: Partial<Record<Decision, number>>;
  confirmed_fraud_24h: number;
  confirmed_fraud_blocked_amount_24h: number;
  as_of: string;
}

export interface TrendPoint {
  key: string;
  transactions: number;
  review: number;
  blocked: number;
  amount: number;
}

export interface TransactionSummary {
  transaction_id: string;
  timestamp: string;
  user_id: string;
  merchant_id: string;
  merchant_category: string;
  amount: number;
  currency: string;
  country: string;
  risk_score: number;
  fraud_probability: number;
  decision: Decision;
  model_version: string;
  processing_time_ms: number;
  case_status: string | null;
  resolution: string | null;
}

export interface PageResult<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Alert {
  alert_id: number;
  transaction_id: string;
  severity: string;
  status: string;
  explanation: { top_risk_factors?: Array<{ feature: string; impact: number }> } | null;
  analyst_note: string | null;
  resolution: string | null;
  created_at: string;
}

export interface ModelPerformance {
  status: "available" | "awaiting_labels";
  labeled_transactions: number;
  precision?: number;
  recall?: number;
  f1?: number;
  pr_auc?: number;
  roc_auc?: number | null;
  brier_score?: number;
  minimum_retraining_labels?: number;
}

export interface ModelInfo {
  model_version: string;
  review_threshold: number;
  block_threshold: number;
  bootstrap_model: boolean;
}

export interface DriftReport {
  report_id: number;
  model_version: string;
  window_start: string;
  window_end: string;
  metrics: Record<string, unknown>;
  drift_detected: boolean;
  segment: string;
}

export interface PerformanceReport {
  report_id: number;
  model_version: string;
  window_start: string;
  window_end: string;
  label_count: number;
  metrics: Record<string, number>;
  degradation_detected: boolean;
}

export interface RetrainingJob {
  job_id: string;
  trigger_type: "DRIFT" | "PERFORMANCE" | "MANUAL";
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "PROMOTED" | "SUPERSEDED" | "FAILED";
  champion_version: string;
  challenger_version: string | null;
  promotion_recommended: boolean | null;
  requested_by: string;
  created_at: string;
  error: string | null;
}
