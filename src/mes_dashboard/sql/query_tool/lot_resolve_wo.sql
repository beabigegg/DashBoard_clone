-- GA Work Order to CONTAINERID Resolution
-- Expands work order to all associated CONTAINERIDs
--
-- Parameters:
--   :work_orders - List of PJ_WORKORDER values (bind variable list)
--
-- Note: One work order may expand to many CONTAINERIDs (can be 100+)
--       Using LOTWIPHISTORY because PJ_WORKORDER has 100% completeness there

SELECT DISTINCT
    CONTAINERID,
    PJ_WORKORDER
FROM DWH.DW_MES_LOTWIPHISTORY
WHERE PJ_WORKORDER IN ({{ WORK_ORDERS }})
