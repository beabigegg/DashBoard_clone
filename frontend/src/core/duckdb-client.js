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
 *
 * The client is a lazy singleton per page — calling getDuckDBClient() multiple
 * times returns the same instance. Call destroy() to release resources.
 */

import DuckDBWorker from '../workers/duckdb-worker.js?worker';

let _instance = null;

export class DuckDBClient {
  constructor() {
    this._worker = null;
    this._pending = new Map();   // id → { resolve, reject }
    this._nextId = 1;
    this._ready = false;
  }

  /** Lazy-init the Web Worker and DuckDB-WASM. */
  async init() {
    if (this._ready) return;
    this._worker = new DuckDBWorker();
    this._worker.onmessage = (evt) => this._handleMessage(evt.data);
    this._worker.onerror  = (err) => {
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
   * @param {string} tableName
   * @param {ArrayBuffer} buffer
   */
  async registerParquet(tableName, buffer) {
    await this.init();
    await this._send('register', { tableName, buffer }, [buffer]);
  }

  /**
   * Execute a SQL query and return plain JS object rows.
   * @param {string} sql
   * @returns {Promise<Array<object>>}
   */
  async sendQuery(sql) {
    await this.init();
    return this._send('query', { sql });
  }

  /** Terminate the worker and release all resources. */
  destroy() {
    if (this._worker) {
      // Best-effort graceful shutdown
      try { this._send('destroy', {}).catch(() => {}); } catch (_) {}
      setTimeout(() => {
        try { this._worker.terminate(); } catch (_) {}
        this._worker = null;
      }, 500);
    }
    this._ready = false;
    this._pending.clear();
    _instance = null;
  }

  // ── Private ─────────────────────────────────────────────────────────────

  _send(type, payload, transferable = []) {
    return new Promise((resolve, reject) => {
      const id = this._nextId++;
      this._pending.set(id, { resolve, reject });
      this._worker.postMessage({ id, type, ...payload }, transferable);
    });
  }

  _handleMessage({ id, ok, result, error }) {
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
export function getDuckDBClient() {
  if (!_instance) {
    _instance = new DuckDBClient();
  }
  return _instance;
}

/** Check if DuckDB-WASM is supported (Worker + WebAssembly available). */
export function isDuckDBSupported() {
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
 * @param {string} url  - Spool download URL
 * @param {number} [timeout=120000]
 * @returns {Promise<ArrayBuffer>}
 */
export async function fetchParquetBuffer(url, timeout = 120000) {
  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeout);
  try {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
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
