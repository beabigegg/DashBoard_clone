-- Resource detail with pagination
-- Placeholders:
--   LATEST_STATUS_SUBQUERY - Base subquery for latest resource status
--   WHERE_CLAUSE          - Dynamic WHERE conditions (e.g., AND ...)
-- Parameters:
--   :start_row - Pagination start row
--   :end_row   - Pagination end row

SELECT * FROM (
    SELECT
        RESOURCENAME,
        WORKCENTERNAME,
        RESOURCEFAMILYNAME,
        NEWSTATUSNAME,
        NEWREASONNAME,
        LASTSTATUSCHANGEDATE,
        PJ_DEPARTMENT,
        VENDORNAME,
        VENDORMODEL,
        PJ_ASSETSSTATUS,
        AVAILABILITY,
        PJ_ISPRODUCTION,
        PJ_ISKEY,
        PJ_ISMONITOR,
        ROW_NUMBER() OVER (
            ORDER BY LASTSTATUSCHANGEDATE DESC NULLS LAST
        ) AS rn
    FROM ({{ LATEST_STATUS_SUBQUERY }}) rs
    WHERE 1=1 {{ WHERE_CLAUSE }}
) WHERE rn BETWEEN :start_row AND :end_row
