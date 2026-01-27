# -*- coding: utf-8 -*-
"""Table configuration metadata for MES Dashboard."""

# 17 core tables config (with categories)
TABLES_CONFIG = {
    '即時數據表 (DWH)': [
        {
            'name': 'DWH.DW_PJ_LOT_V',
            'display_name': 'WIP 即時批次 (DW_PJ_LOT_V)',
            'row_count': 10000,  # 動態變化，約 9000-12000
            'time_field': 'SYS_DATE',
            'description': 'DWH 即時 WIP View - 每 5 分鐘更新，包含完整批次狀態、工站、設備、Hold 原因等 70 欄位'
        }
    ],
    '現況快照表': [
        {
            'name': 'DW_MES_WIP',
            'display_name': 'WIP (在制品表)',
            'row_count': 77470834,
            'time_field': 'TXNDATE',
            'description': '在製品現況表（含歷史累積）- 當前 WIP 狀態/數量'
        },
        {
            'name': 'DW_MES_RESOURCE',
            'display_name': 'RESOURCE (資源主檔)',
            'row_count': 90620,
            'time_field': None,
            'description': '資源表 - 設備/載具等資源基本資料（OBJECTCATEGORY=ASSEMBLY 時，RESOURCENAME 為設備編號）'
        },
        {
            'name': 'DW_MES_CONTAINER',
            'display_name': 'CONTAINER (容器信息表)',
            'row_count': 5185532,
            'time_field': 'LASTMOVEOUTTIMESTAMP',
            'description': '容器/批次主檔 - 目前在製容器狀態、數量與流程資訊'
        },
        {
            'name': 'DW_MES_JOB',
            'display_name': 'JOB (設備維修工單)',
            'row_count': 1239659,
            'time_field': 'CREATEDATE',
            'description': '設備維修工單表 - 維修工單的當前狀態與流程'
        }
    ],
    '歷史累積表': [
        {
            'name': 'DW_MES_RESOURCESTATUS',
            'display_name': 'RESOURCESTATUS (資源狀態歷史)',
            'row_count': 65139825,
            'time_field': 'OLDLASTSTATUSCHANGEDATE',
            'description': '設備狀態變更歷史表 - 狀態切換與原因'
        },
        {
            'name': 'DW_MES_RESOURCESTATUS_SHIFT',
            'display_name': 'RESOURCESTATUS_SHIFT (資源班次狀態)',
            'row_count': 74155046,
            'time_field': 'DATADATE',
            'description': '設備狀態班次彙總表 - 班次級狀態/工時'
        },
        {
            'name': 'DW_MES_LOTWIPHISTORY',
            'display_name': 'LOTWIPHISTORY (批次流轉歷史)',
            'row_count': 53085425,
            'time_field': 'TRACKINTIMESTAMP',
            'description': '在製流轉歷史表 - 批次進出站與流程軌跡'
        },
        {
            'name': 'DW_MES_LOTWIPDATAHISTORY',
            'display_name': 'LOTWIPDATAHISTORY (批次數據歷史)',
            'row_count': 77168503,
            'time_field': 'TXNTIMESTAMP',
            'description': '在製數據採集歷史表 - 製程量測/參數紀錄'
        },
        {
            'name': 'DW_MES_HM_LOTMOVEOUT',
            'display_name': 'HM_LOTMOVEOUT (批次移出表)',
            'row_count': 48374309,
            'time_field': 'TXNDATE',
            'description': '批次出站事件歷史表 - 出站/移出交易'
        },
        {
            'name': 'DW_MES_JOBTXNHISTORY',
            'display_name': 'JOBTXNHISTORY (維修工單交易歷史)',
            'row_count': 9488096,
            'time_field': 'TXNDATE',
            'description': '維修工單交易歷史表 - 工單狀態變更紀錄'
        },
        {
            'name': 'DW_MES_LOTREJECTHISTORY',
            'display_name': 'LOTREJECTHISTORY (批次拒絕歷史)',
            'row_count': 15678513,
            'time_field': 'CREATEDATE',
            'description': '批次不良/報廢歷史表 - 不良原因與數量'
        },
        {
            'name': 'DW_MES_LOTMATERIALSHISTORY',
            'display_name': 'LOTMATERIALSHISTORY (物料消耗歷史)',
            'row_count': 17702828,
            'time_field': 'CREATEDATE',
            'description': '批次物料消耗歷史表 - 用料與批次關聯'
        },
        {
            'name': 'DW_MES_HOLDRELEASEHISTORY',
            'display_name': 'HOLDRELEASEHISTORY (Hold/Release歷史)',
            'row_count': 310033,
            'time_field': 'HOLDTXNDATE',
            'description': 'Hold/Release 歷史表 - 批次停工與解除紀錄'
        },
        {
            'name': 'DW_MES_MAINTENANCE',
            'display_name': 'MAINTENANCE (設備維護歷史)',
            'row_count': 50954850,
            'time_field': 'TXNDATE',
            'description': '設備保養/維護紀錄表 - 保養計畫與點檢數據'
        }
    ],
    '輔助表': [
        {
            'name': 'DW_MES_PARTREQUESTORDER',
            'display_name': 'PARTREQUESTORDER (物料請求訂單)',
            'row_count': 61396,
            'time_field': None,
            'description': '維修用料請求表 - 維修/設備零件請領'
        },
        {
            'name': 'DW_MES_PJ_COMBINEDASSYLOTS',
            'display_name': 'PJ_COMBINEDASSYLOTS (組合裝配批次)',
            'row_count': 1955691,
            'time_field': None,
            'description': '併批紀錄表 - 合批/合併批次關聯與數量資訊'
        }
    ]
}
