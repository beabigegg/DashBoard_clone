# -*- coding: utf-8 -*-
"""Table configuration metadata for MES Dashboard.

Row counts updated from data/table_schema_info.json (2026-01-29)
"""

# 19 core tables config (with categories)
TABLES_CONFIG = {
    '即時數據表 (View)': [
        {
            'name': 'DWH.DW_MES_LOT_V',
            'display_name': 'WIP 即時批次 (DWH.DW_MES_LOT_V)',
            'row_count': 9468,  # 動態變化，約 9000-12000
            'time_field': 'SYS_DATE',
            'description': 'MES 即時 WIP View - 每 5 分鐘更新，包含完整批次狀態、工站、設備、Hold 原因等 70 欄位'
        },
        {
            'name': 'DWH.DW_MES_EQUIPMENTSTATUS_WIP_V',
            'display_name': '設備狀態+WIP 視圖 (DWH.DW_MES_EQUIPMENTSTATUS_WIP_V)',
            'row_count': 2631,
            'time_field': None,
            'description': '設備狀態與 WIP 關聯視圖 - 設備當前狀態、維修工單、資產狀態等 32 欄位'
        },
        {
            'name': 'DWH.DW_MES_SPEC_WORKCENTER_V',
            'display_name': '規格工站對照 (DWH.DW_MES_SPEC_WORKCENTER_V)',
            'row_count': 230,
            'time_field': None,
            'description': '規格與工站對照視圖 - 規格順序、工站群組、工站順序等 9 欄位'
        }
    ],
    '現況快照表': [
        {
            'name': 'DWH.DW_MES_WIP',
            'display_name': 'WIP (DWH.DW_MES_WIP)',
            'row_count': 79058085,
            'time_field': 'TXNDATE',
            'description': '在製品現況表（含歷史累積）- 當前 WIP 狀態/數量'
        },
        {
            'name': 'DWH.DW_MES_RESOURCE',
            'display_name': 'RESOURCE (DWH.DW_MES_RESOURCE)',
            'row_count': 91329,
            'time_field': None,
            'description': '資源表 - 設備/載具等資源基本資料（OBJECTCATEGORY=ASSEMBLY 時，RESOURCENAME 為設備編號）'
        },
        {
            'name': 'DWH.DW_MES_CONTAINER',
            'display_name': 'CONTAINER (DWH.DW_MES_CONTAINER)',
            'row_count': 5218406,
            'time_field': 'LASTMOVEOUTTIMESTAMP',
            'description': '容器/批次主檔 - 目前在製容器狀態、數量與流程資訊'
        },
        {
            'name': 'DWH.DW_MES_JOB',
            'display_name': 'JOB (DWH.DW_MES_JOB)',
            'row_count': 1248622,
            'time_field': 'CREATEDATE',
            'description': '設備維修工單表 - 維修工單的當前狀態與流程'
        }
    ],
    '歷史累積表': [
        {
            'name': 'DWH.DW_MES_RESOURCESTATUS',
            'display_name': 'RESOURCESTATUS (DWH.DW_MES_RESOURCESTATUS)',
            'row_count': 65742614,
            'time_field': 'OLDLASTSTATUSCHANGEDATE',
            'description': '設備狀態變更歷史表 - 狀態切換與原因'
        },
        {
            'name': 'DWH.DW_MES_RESOURCESTATUS_SHIFT',
            'display_name': 'RESOURCESTATUS_SHIFT (DWH.DW_MES_RESOURCESTATUS_SHIFT)',
            'row_count': 74820134,
            'time_field': 'DATADATE',
            'description': '設備狀態班次彙總表 - 班次級狀態/工時'
        },
        {
            'name': 'DWH.DW_MES_LOTWIPHISTORY',
            'display_name': 'LOTWIPHISTORY (DWH.DW_MES_LOTWIPHISTORY)',
            'row_count': 53454213,
            'time_field': 'TRACKINTIMESTAMP',
            'description': '在製流轉歷史表 - 批次進出站與流程軌跡'
        },
        {
            'name': 'DWH.DW_MES_LOTWIPDATAHISTORY',
            'display_name': 'LOTWIPDATAHISTORY (DWH.DW_MES_LOTWIPDATAHISTORY)',
            'row_count': 77960216,
            'time_field': 'TXNTIMESTAMP',
            'description': '在製數據採集歷史表 - 製程量測/參數紀錄'
        },
        {
            'name': 'DWH.DW_MES_HM_LOTMOVEOUT',
            'display_name': 'HM_LOTMOVEOUT (DWH.DW_MES_HM_LOTMOVEOUT)',
            'row_count': 48645692,
            'time_field': 'TXNDATE',
            'description': '批次出站事件歷史表 - 出站/移出交易'
        },
        {
            'name': 'DWH.DW_MES_JOBTXNHISTORY',
            'display_name': 'JOBTXNHISTORY (DWH.DW_MES_JOBTXNHISTORY)',
            'row_count': 9554723,
            'time_field': 'TXNDATE',
            'description': '維修工單交易歷史表 - 工單狀態變更紀錄'
        },
        {
            'name': 'DWH.DW_MES_LOTREJECTHISTORY',
            'display_name': 'LOTREJECTHISTORY (DWH.DW_MES_LOTREJECTHISTORY)',
            'row_count': 15786025,
            'time_field': 'TXNDATE',
            'description': '批次不良/報廢歷史表 - 不良原因與數量'
        },
        {
            'name': 'DWH.DW_MES_LOTMATERIALSHISTORY',
            'display_name': 'LOTMATERIALSHISTORY (DWH.DW_MES_LOTMATERIALSHISTORY)',
            'row_count': 17829931,
            'time_field': 'TXNDATE',
            'description': '批次物料消耗歷史表 - 用料與批次關聯'
        },
        {
            'name': 'DWH.DW_MES_HOLDRELEASEHISTORY',
            'display_name': 'HOLDRELEASEHISTORY (DWH.DW_MES_HOLDRELEASEHISTORY)',
            'row_count': 310737,
            'time_field': 'HOLDTXNDATE',
            'description': 'Hold/Release 歷史表 - 批次停工與解除紀錄'
        },
        {
            'name': 'DWH.DW_MES_MAINTENANCE',
            'display_name': 'MAINTENANCE (DWH.DW_MES_MAINTENANCE)',
            'row_count': 52060026,
            'time_field': 'TXNDATE',
            'description': '設備保養/維護紀錄表 - 保養計畫與點檢數據'
        }
    ],
    '輔助表': [
        {
            'name': 'DWH.DW_MES_PARTREQUESTORDER',
            'display_name': 'PARTREQUESTORDER (DWH.DW_MES_PARTREQUESTORDER)',
            'row_count': 61396,
            'time_field': None,
            'description': '維修用料請求表 - 維修/設備零件請領'
        },
        {
            'name': 'DWH.DW_MES_PJ_COMBINEDASSYLOTS',
            'display_name': 'PJ_COMBINEDASSYLOTS (DWH.DW_MES_PJ_COMBINEDASSYLOTS)',
            'row_count': 1965425,
            'time_field': None,
            'description': '併批紀錄表 - 合批/合併批次關聯與數量資訊'
        }
    ]
}
