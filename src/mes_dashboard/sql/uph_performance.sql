-- UPH Performance — Oracle chunk read (add-uph-performance-page)
--
-- Extracts per-event UPH (units-per-hour) telemetry for Die-Bond (GDBA) and
-- Wire-Bond (GWBA) equipment families from DWH.EAP_EVENT LEFT JOIN'd to
-- DWH.EAP_EVENT_DETAIL (business-rules.md UPH-01..UPH-04; ADR-0017).
--
-- ADR-0017 Decision-1: PARAMETER_NAME is selected by a family-conditional CASE
-- predicate in the JOIN's ON clause (SUBSTR(EQUIPMENT_ID,1,4) -> BondUPH for
-- GDBA / fHCM_UPH for GWBA) -- NEVER a blanket `PARAMETER_NAME IN (...)`
-- (a blanket IN-list would let one family's parameter attach to the other
-- family's event row if they ever share a SEQ_ID -- silent cross-family
-- leakage forbidden by UPH-03). The LEFT JOIN keeps the event row even when
-- no matching detail row exists for the target parameter (data-shape-contract
-- §3.29: UPH_VALUE nullable "when the detail join finds no matching parameter
-- row for this event").
--
-- PARAMETER_NAME (the returned column) is computed directly from the
-- family CASE expression on e.EQUIPMENT_ID -- NOT read back from
-- d.PARAMETER_NAME -- so it is populated for every row this query can ever
-- return (equipment_filter already restricts rows to GDBA/GWBA only, so the
-- CASE always resolves; the parquet column is non-nullable per §3.29).
--
-- Chunking (UPH-01): caller MUST invoke this template once per <=6h
-- [chunk_start, chunk_end) window (BaseChunkedDuckDBJob, chunk_strategy=TIME).
-- A single unchunked full-range query is forbidden -- the detail JOIN against
-- this ~12M-row/day table previously timed out at >180s over a 24h window
-- (docs/architecture/eap-event-uph-collection-investigation.md).
--
-- UPH-04: PARAMETER_VALUE is fetched as-is (UPH_VALUE_RAW) -- NO scale
-- conversion (x100 / /100) is ever applied here or anywhere downstream. The
-- worker casts UPH_VALUE_RAW -> DOUBLE in DuckDB post_aggregate with a plain
-- TRY_CAST, no arithmetic.
--
-- Parameters (bound via oracledb named params):
--   :chunk_start - 'YYYY-MM-DD HH24:MI:SS' (inclusive)
--   :chunk_end   - 'YYYY-MM-DD HH24:MI:SS' (exclusive)
--
-- Dynamic placeholders (structural only, substituted by the worker via
-- SQLLoader.load_with_params -- never raw user input; user-supplied values
-- are always bound separately as named params). NOTE: the placeholder
-- tokens are deliberately NOT spelled out with their literal `{{ }}` braces
-- anywhere in this comment block -- SQLLoader.load_with_params does a plain
-- global string replace, so a literal "{{ NAME }}" mention here would also
-- get substituted, and a substituted value containing an embedded newline
-- would split this single `--` comment line in two, leaving the back half
-- uncommented and breaking the statement (this exact failure reproduced as
-- ORA-00900 in production during add-uph-performance-page's initial build --
-- see business-rules.md UPH-01 and the worker's builder-function docstrings):
--   FAMILY_FILTER placeholder - mandatory GDBA/GWBA family-scope predicate
--                         (UPH-02); one of:
--                           (e.EQUIPMENT_ID LIKE 'GDBA%' OR e.EQUIPMENT_ID LIKE 'GWBA%')
--                           e.EQUIPMENT_ID LIKE 'GDBA%'
--                           e.EQUIPMENT_ID LIKE 'GWBA%'
--   EXTRA_FILTERS placeholder - zero or more newline-prefixed "AND ..."
--                         clauses for the optional coarse dims
--                         (equipment_ids IN-list; pj_types / packages /
--                         workcenter_names EXISTS semi-joins per
--                         data-shape-contract.md §3.29 Oracle coarse-filter
--                         mapping table) -- empty string when none supplied.
--
-- Tables:
--   DWH.EAP_EVENT (alias e)         -- LOT_ID, EQUIPMENT_ID, EVENT_TYPE, LAST_UPDATE_TIME
--   DWH.EAP_EVENT_DETAIL (alias d)  -- SEQ_ID, PARAMETER_NAME, PARAMETER_VALUE
--   DWH.DW_MES_CONTAINER (alias c)  -- coarse pj_types/packages EXISTS filters
--                                      ONLY -- the product-dim enrichment
--                                      bridge (Package/Type/PJ_BOP/PJ_FUNCTION)
--                                      runs in the worker's post_aggregate,
--                                      NOT here (ADR-0017 Decision-3, mirrors
--                                      eap_alarm_worker.py's _safe_lot_product_df).
--   DWH.DW_MES_RESOURCE (alias r)   -- coarse workcenter_names EXISTS filter
--                                      ONLY -- the WORKCENTERNAME/DB-WB
--                                      enrichment bridge also runs in
--                                      post_aggregate (UPH-05).

SELECT
    e.LOT_ID                       AS LOT_ID,
    e.EQUIPMENT_ID                 AS EQUIPMENT_ID,
    SUBSTR(e.EQUIPMENT_ID, 1, 4)   AS EQUIPMENT_FAMILY,
    e.LAST_UPDATE_TIME             AS EVENT_TIME,
    CASE SUBSTR(e.EQUIPMENT_ID, 1, 4)
        WHEN 'GDBA' THEN 'BondUPH'
        WHEN 'GWBA' THEN 'fHCM_UPH'
    END                             AS PARAMETER_NAME,
    d.PARAMETER_VALUE              AS UPH_VALUE_RAW
FROM DWH.EAP_EVENT e
LEFT JOIN DWH.EAP_EVENT_DETAIL d
       ON d.SEQ_ID = e.SEQ_ID
      AND d.PARAMETER_NAME = CASE SUBSTR(e.EQUIPMENT_ID, 1, 4)
                                  WHEN 'GDBA' THEN 'BondUPH'
                                  WHEN 'GWBA' THEN 'fHCM_UPH'
                              END
WHERE e.LAST_UPDATE_TIME >= TO_DATE(:chunk_start, 'YYYY-MM-DD HH24:MI:SS')
  AND e.LAST_UPDATE_TIME <  TO_DATE(:chunk_end,   'YYYY-MM-DD HH24:MI:SS')
  AND {{ FAMILY_FILTER }}
  AND e.EVENT_TYPE LIKE '%_M[60]'
  AND e.LOT_ID IS NOT NULL
  {{ EXTRA_FILTERS }}
