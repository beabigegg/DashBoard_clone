/// <reference types="vite/client" />

/**
 * DuckDB-WASM client — thin wrapper over the Web Worker.
 *
 * Usage:
 *   import { getDuckDBClient } from '@/core/duckdb-client.js'
 *   const client = getDuckDBClient()
 *   await client.init()
 *   await client.registerParquet('my_table', arrayBuffer)
 *   const rows = await client.sendQuery('SELECT * FROM my_table LIMIT 10')
 *   client.destroy()
 */

import DuckDBWorker from '../workers/duckdb-worker.js?worker';

interface PendingCall {
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
}

interface WorkerMessage {
  id: number;
  type: string;
  [key: string]: unknown;
}

interface WorkerResponse {
  id: number;
  ok: boolean;
  result: unknown;
  error: string;
}

let _instance: DuckDBClient | null = null;

export class DuckDBClient {
  private _worker: Worker | null = null;
  private _pending: Map<number, PendingCall> = new Map();
  private _nextId = 1;
  private _ready = false;

  /** Lazy-init the Web Worker and DuckDB-WASM. */
  async init(): Promise<void> {
    if (this._ready) return;
    this._worker = new DuckDBWorker();
    this._worker.onmessage = (evt: MessageEvent<WorkerResponse>) =>
      this._handleMessage(evt.data);
    this._worker.onerror = (err: ErrorEvent) => {
      // Surface any unhandled worker errors to pending promises
      for (const [, { reject }] of this._pending) {
        reject(new Error(err.message));
      }
      this._pending.clear();
    };
    await this._send('init', {});
    this._ready = true;
  }

  /**
   * Register a Parquet ArrayBuffer as a named view in DuckDB.
   * @param tableName
   * @param buffer
   */
  async registerParquet(tableName: string, buffer: ArrayBuffer): Promise<void> {
    await this.init();
    await this._send('register', { tableName, buffer }, [buffer]);
  }

  /**
   * Execute a SQL query and return plain JS object rows.
   * @param sql
   * @returns rows
   */
  async sendQuery(sql: string): Promise<unknown[]> {
    await this.init();
    return this._send('query', { sql }) as Promise<unknown[]>;
  }

  /** Terminate the worker and release all resources. */
  destroy(): void {
    if (this._worker) {
      // Best-effort graceful shutdown
      try { this._send('destroy', {}).catch(() => {}); } catch (_) {}
      setTimeout(() => {
        try { this._worker?.terminate(); } catch (_) {}
        this._worker = null;
      }, 500);
    }
    this._ready = false;
    this._pending.clear();
    _instance = null;
  }

  // ── Private ─────────────────────────────────────────────────────────────

  private _send(
    type: string,
    payload: Record<string, unknown>,
    transferable: Transferable[] = []
  ): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const id = this._nextId++;
      this._pending.set(id, { resolve, reject });
      const msg: WorkerMessage = { id, type, ...payload };
      this._worker!.postMessage(msg, transferable);
    });
  }

  private _handleMessage({ id, ok, result, error }: WorkerResponse): void {
    const pending = this._pending.get(id);
    if (!pending) return;
    this._pending.delete(id);
    if (ok) {
      pending.resolve(result);
    } else {
      pending.reject(new Error(error));
    }
  }
}

/**
 * Return the singleton DuckDB client for this page.
 * Creates it on first call.
 */
export function getDuckDBClient(): DuckDBClient {
  if (!_instance) {
    _instance = new DuckDBClient();
  }
  return _instance;
}

/** Check if DuckDB-WASM is supported (Worker + WebAssembly available). */
export function isDuckDBSupported(): boolean {
  try {
    return (
      typeof Worker !== 'undefined' &&
      typeof WebAssembly !== 'undefined' &&
      typeof WebAssembly.instantiate === 'function'
    );
  } catch (_) {
    return false;
  }
}

/**
 * Download a Parquet spool file and return its ArrayBuffer.
 * Includes CSRF token and an optional timeout (default 120s).
 * @param url  - Spool download URL
 * @param timeout
 */
export async function fetchParquetBuffer(url: string, timeout = 120000): Promise<ArrayBuffer> {
  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeout);
  try {
    const csrfToken =
      (document.querySelector('meta[name="csrf-token"]') as HTMLMetaElement)?.content || '';
    const resp = await fetch(url, {
      method: 'GET',
      headers: { 'X-CSRF-Token': csrfToken },
      signal: controller.signal,
    });
    if (!resp.ok) throw new Error(`Spool download failed: HTTP ${resp.status}`);
    return await resp.arrayBuffer();
  } finally {
    clearTimeout(timerId);
  }
}
