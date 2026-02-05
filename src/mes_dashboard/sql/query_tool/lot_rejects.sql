-- LOT Reject Records Query
-- Retrieves reject (defect) records for a LOT
--
-- Parameters:
--   :container_id - CONTAINERID to query (16-char hex)
--
-- Note: Uses LOSSREASONNAME (NOT REJECTREASONNAME)
--       Uses TXNDATE (NOT TXNDATETIME)
--       Only has EQUIPMENTNAME, NO EQUIPMENTID field

SELECT
    CONTAINERID,
    REJECTCATEGORYNAME,
    LOSSREASONNAME,
    REJECTQTY,
    WORKCENTERNAME,
    EQUIPMENTNAME,
    TXNDATE,
    COMMENTS,
    REJECTCAUSE,
    REJECTCOMMENT
FROM DWH.DW_MES_LOTREJECTHISTORY
WHERE CONTAINERID = :container_id
ORDER BY TXNDATE
