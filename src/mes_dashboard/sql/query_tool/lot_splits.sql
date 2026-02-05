-- LOT Split/Merge Records (拆併批紀錄)
-- Shows what serial numbers were produced from this LOT
-- and what other LOTs were combined together
--
-- Parameters:
--   :container_id - Target CONTAINERID (16-char hex)
--
-- Returns:
--   - FINISHEDNAME: Serial number produced
--   - Related LOTs that were combined to create each serial number
--   - PJ_COMBINEDRATIO: Contribution ratio (1.0 = 100%)
--   - PJ_GOODDIEQTY: Good die quantity contributed

SELECT
    p.FINISHEDNAME,
    p.CONTAINERID,
    p.CONTAINERNAME AS LOT_ID,
    p.PJ_WORKORDER,
    p.PJ_COMBINEDRATIO,
    p.PJ_GOODDIEQTY,
    p.PJ_ORIGINALGOODDIEQTY,
    p.ORIGINALSTARTDATE
FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS p
WHERE p.FINISHEDNAME IN (
    -- Find all serial numbers that this LOT contributed to
    SELECT DISTINCT FINISHEDNAME
    FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS
    WHERE CONTAINERID = :container_id
)
ORDER BY p.FINISHEDNAME, p.ORIGINALSTARTDATE, p.CONTAINERNAME
