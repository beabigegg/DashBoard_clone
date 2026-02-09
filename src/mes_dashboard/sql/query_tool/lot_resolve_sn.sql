-- Serial Number (流水號) to CONTAINERID Resolution
-- Converts finished product serial number to CONTAINERID list
--
-- Parameters:
--   :finished_names - List of FINISHEDNAME values (bind variable list)
--
-- Note: One FINISHEDNAME may correspond to multiple CONTAINERIDs (2-5 typical)

SELECT DISTINCT
    CONTAINERID,
    FINISHEDNAME
FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS
WHERE FINISHEDNAME IN ({{ FINISHED_NAMES }})
