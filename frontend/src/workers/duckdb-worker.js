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

let db = null;
let conn = null;

/** Initialise DuckDB once using the single-threaded WASM bundle. */
async function initDuckDB() {
  if (db !== null) return;

  const JSDELIVR_BUNDLES = duckdb.getJsDelivrBundles();

  // Select the best available bundle (prefer eh, fall back to mvp)
  const bundle = await duckdb.selectBundle(JSDELIVR_BUNDLES);

  const worker_url = URL.createObjectURL(
    new Blob([`importScripts("${bundle.mainWorker}");`], { type: 'text/javascript' })
  );
  // We are already in a worker, so spawn a synchronous worker for DuckDB
  const duckdbWorker = new Worker(worker_url);
  const logger = new duckdb.ConsoleLogger();

  db = new duckdb.AsyncDuckDB(logger, duckdbWorker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
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
