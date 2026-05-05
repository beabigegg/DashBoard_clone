/**
 * Shared TypeScript types for the MES Dashboard API layer.
 *
 * ApiResponse<T> mirrors the canonical runtime envelope used by all Flask
 * endpoints.  The runtime guard (schema-guard.ts) and unwrap utility
 * (unwrap-api-result.ts) both operate on this shape at runtime.
 */

// ---------------------------------------------------------------------------
// API envelope
// ---------------------------------------------------------------------------

export interface ApiResponseMeta {
  timestamp?: string;
  app_version?: string;
  retry_after_seconds?: number;
  [key: string]: unknown; // meta may contain additional server-specific fields
}

export type ApiResponse<T> =
  | {
      success: true;
      data: T;
      meta?: ApiResponseMeta;
    }
  | {
      success: false;
      error: ApiErrorPayload;
      meta?: ApiResponseMeta;
    };

export interface ApiErrorPayload {
  code?: string;
  message?: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

export interface PaginationMeta {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

// ---------------------------------------------------------------------------
// Pending job entry (shared between pending-jobs-registry and consumers)
// ---------------------------------------------------------------------------

export interface PendingJobEntry {
  job_id: string;
  prefix: string;
  endpoint: string;
  queued_at: number;
}
