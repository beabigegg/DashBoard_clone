/**
 * DuckDB-WASM Web Worker
 *
 * Runs in a dedicated worker thread. Handles:
 *   - init: initialise DuckDB-WASM (lazy, once)
 *   - register: register a Parquet buffer as a named DuckDB table
 *   - query: execute SQL and return result rows
 *   - destroy: close the DuckDB connection
 *
 * All messages follow the shape { id, type, ...payload }.
 * Responses: { id, ok: true, result } on success
 *            { id, ok: false, error: string } on failure.
 */

import * as duckdb from '@duckdb/duckdb-wasm';
import duckdb_wasm_eh from '@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url';
import duckdb_worker_eh from '@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url';
import duckdb_wasm_mvp from '@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url';
import duckdb_worker_mvp from '@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url';

let db = null;
let conn = null;

/** Initialise DuckDB once using locally-bundled WASM files (CSP-safe). */
async function initDuckDB() {
  if (db !== null) return;

  const LOCAL_BUNDLES = {
    mvp: {
      mainModule: duckdb_wasm_mvp,
      mainWorker: duckdb_worker_mvp,
      pthreadWorker: null,
    },
    eh: {
      mainModule: duckdb_wasm_eh,
      mainWorker: duckdb_worker_eh,
      pthreadWorker: null,
    },
  };

  // Select the best available bundle (prefer eh, fall back to mvp)
  const bundle = await duckdb.selectBundle(LOCAL_BUNDLES);

  // importScripts inside a blob worker requires absolute URLs
  const workerAbsUrl = new URL(bundle.mainWorker, self.location.origin).href;
  const worker_url = URL.createObjectURL(
    new Blob([`importScripts("${workerAbsUrl}");`], { type: 'text/javascript' })
  );
  // We are already in a worker, so spawn a synchronous worker for DuckDB
  const duckdbWorker = new Worker(worker_url);
  const logger = new duckdb.ConsoleLogger();

  const moduleAbsUrl = new URL(bundle.mainModule, self.location.origin).href;
  db = new duckdb.AsyncDuckDB(logger, duckdbWorker);
  await db.instantiate(moduleAbsUrl, bundle.pthreadWorker);
  conn = await db.connect();

  URL.revokeObjectURL(worker_url);
}

/**
 * Register a Parquet ArrayBuffer as a named DuckDB view.
 * @param {string} tableName - Name to use in SQL queries
 * @param {ArrayBuffer} buffer - Raw Parquet bytes
 */
async function registerParquet(tableName, buffer) {
  const uint8 = new Uint8Array(buffer);
  const fileName = `${tableName}.parquet`;
  await db.registerFileBuffer(fileName, uint8);
  await conn.query(`
    CREATE OR REPLACE VIEW ${JSON.stringify(tableName)} AS
    SELECT * FROM read_parquet('${fileName}')
  `);
}

/**
 * Execute a SQL query and return plain JS objects.
 * @param {string} sql
 * @returns {Array<object>}
 */
async function execQuery(sql) {
  const result = await conn.query(sql);
  const schema = result.schema.fields.map(f => f.name);
  const rows = [];
  for (const batch of result.batches) {
    const length = batch.numRows;
    for (let i = 0; i < length; i++) {
      const row = {};
      for (const col of schema) {
        const val = batch.getChildAt(schema.indexOf(col)).get(i);
        // Convert BigInt to Number for JSON serialisability
        row[col] = typeof val === 'bigint' ? Number(val) : val;
      }
      rows.push(row);
    }
  }
  return rows;
}

async function destroyDuckDB() {
  try {
    if (conn) { await conn.close(); conn = null; }
    if (db)   { await db.terminate(); db = null; }
  } catch (_) { /* ignore */ }
}

// ── Message handler ─────────────────────────────────────────────────────────

self.onmessage = async function (evt) {
  const { id, type, ...payload } = evt.data;

  try {
    switch (type) {
      case 'init': {
        await initDuckDB();
        self.postMessage({ id, ok: true, result: null });
        break;
      }

      case 'register': {
        await initDuckDB();
        const { tableName, buffer } = payload;
        await registerParquet(tableName, buffer);
        self.postMessage({ id, ok: true, result: null });
        break;
      }

      case 'query': {
        await initDuckDB();
        const rows = await execQuery(payload.sql);
        self.postMessage({ id, ok: true, result: rows });
        break;
      }

      case 'destroy': {
        await destroyDuckDB();
        self.postMessage({ id, ok: true, result: null });
        break;
      }

      default:
        self.postMessage({ id, ok: false, error: `Unknown message type: ${type}` });
    }
  } catch (err) {
    self.postMessage({ id, ok: false, error: String(err?.message ?? err) });
  }
};
