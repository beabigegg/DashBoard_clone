WITH spec_map AS (
    SELECT
        SPEC,
        MIN(WORK_CENTER_GROUP) KEEP (
            DENSE_RANK FIRST ORDER BY WORKCENTERSEQUENCE_GROUP
        ) AS WORKCENTER_GROUP
    FROM DWH.DW_MES_SPEC_WORKCENTER_V
    WHERE SPEC IS NOT NULL
    GROUP BY SPEC
),
wc_group_map AS (
    SELECT
        TRIM(WORK_CENTER) AS WORK_CENTER,
        MIN(WORK_CENTER_GROUP) KEEP (
            DENSE_RANK FIRST ORDER BY WORKCENTERSEQUENCE_GROUP
        ) AS WORKCENTER_GROUP
    FROM DWH.DW_MES_SPEC_WORKCENTER_V
    WHERE WORK_CENTER IS NOT NULL
    GROUP BY TRIM(WORK_CENTER)
)
SELECT
    r.TXNDATE                                                    AS TXN_TIME,
    NVL(TRIM(c.CONTAINERNAME), TRIM(r.CONTAINERID))             AS CONTAINERNAME,
    r.WORKCENTERNAME,
    NVL(TRIM(sm.WORKCENTER_GROUP), NVL(TRIM(wm.WORKCENTER_GROUP), NVL(TRIM(r.WORKCENTERNAME), '(NA)'))) AS WORKCENTER_GROUP,
    NVL(TRIM(r.SPECNAME), '')                                   AS SPECNAME,
    NVL(TRIM(r.EQUIPMENTNAME), '')                              AS EQUIPMENTNAME,
    NVL(TRIM(c.PRODUCTNAME), '')                                AS PRODUCTNAME,
    NVL(TRIM(c.PJ_FUNCTION), '')                                AS PJ_FUNCTION,
    NVL(TRIM(c.PJ_TYPE), '')                                    AS PJ_TYPE,
    NVL(TRIM(c.PRODUCTLINENAME), '')                            AS PACKAGE_NAME,
    NVL(TRIM(c.OBJECTTYPE), '')                                 AS SCRAP_OBJECTTYPE,
    NVL(TRIM(r.LOSSREASONNAME), '(未填寫)')                    AS LOSSREASONNAME,
    NVL(
        TRIM(REGEXP_SUBSTR(NVL(TRIM(r.LOSSREASONNAME), '(未填寫)'), '^[^_[:space:]-]+')),
        NVL(TRIM(r.LOSSREASONNAME), '(未填寫)')
    )                                                            AS LOSSREASON_CODE,
    NVL(TRIM(r.REJECTCOMMENT), '')                              AS REJECTCOMMENT,
    NVL(r.REJECTQTY, 0)                                         AS REJECT_QTY,
    NVL(r.STANDBYQTY, 0)                                        AS STANDBY_QTY,
    NVL(r.QTYTOPROCESS, 0)                                      AS QTYTOPROCESS_QTY,
    NVL(r.INPROCESSQTY, 0)                                      AS INPROCESS_QTY,
    NVL(r.PROCESSEDQTY, 0)                                      AS PROCESSED_QTY,
    (
        NVL(r.REJECTQTY, 0)
        + NVL(r.STANDBYQTY, 0)
        + NVL(r.QTYTOPROCESS, 0)
        + NVL(r.INPROCESSQTY, 0)
        + NVL(r.PROCESSEDQTY, 0)
    )                                                            AS REJECT_TOTAL_QTY,
    NVL(r.DEFECTQTY, 0)                                         AS DEFECT_QTY
FROM DWH.DW_MES_LOTREJECTHISTORY r
LEFT JOIN DWH.DW_MES_CONTAINER c
    ON c.CONTAINERID = r.CONTAINERID
LEFT JOIN spec_map sm
    ON sm.SPEC = r.SPECNAME
LEFT JOIN wc_group_map wm
    ON wm.WORK_CENTER = TRIM(r.WORKCENTERNAME)
WHERE UPPER(TRIM(r.PJ_WORKORDER)) = UPPER(TRIM(:workorder))
  AND TRUNC(r.TXNDATE) >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND TRUNC(r.TXNDATE) <= TO_DATE(:end_date, 'YYYY-MM-DD')
  AND (
      :reason_code IS NULL
      OR NVL(
          TRIM(REGEXP_SUBSTR(NVL(TRIM(r.LOSSREASONNAME), '(未填寫)'), '^[^_[:space:]-]+')),
          NVL(TRIM(r.LOSSREASONNAME), '(未填寫)')
      ) = UPPER(TRIM(:reason_code))
  )
ORDER BY
    r.WORKCENTERNAME ASC,
    REJECT_TOTAL_QTY DESC,
    CONTAINERNAME ASC
FETCH FIRST 200 ROWS ONLY
