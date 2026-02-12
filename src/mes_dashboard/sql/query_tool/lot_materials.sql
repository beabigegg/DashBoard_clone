-- LOT Materials Consumption Query
-- Retrieves material consumption records for a LOT
--
-- Parameters:
--   container_id - CONTAINERID to query (16-char hex)
--
-- Note: Uses MATERIALPARTNAME (NOT MATERIALNAME)
--       Uses QTYCONSUMED (NOT CONSUMEQTY)
--       Uses TXNDATE (NOT TXNDATETIME)

SELECT
    CONTAINERID,
    MATERIALPARTNAME,
    MATERIALLOTNAME,
    QTYCONSUMED,
    WORKCENTERNAME,
    EQUIPMENTNAME,
    TXNDATE
FROM DWH.DW_MES_LOTMATERIALSHISTORY
WHERE CONTAINERID = :container_id
ORDER BY TXNDATE
