"""
MES 數據表查詢工具
用於查看各數據表的最後 1000 筆資料，確認表結構和內容
"""

import oracledb
import pandas as pd
from flask import Flask, render_template, request, jsonify
from datetime import datetime
import json

# 數據庫連接配置
DB_CONFIG = {
    'user': 'MBU1_R',
    'password': 'Pj2481mbu1',
    'dsn': '10.1.1.58:1521/DWDB'
}

# 16 張核心表配置（含表性質分類）
TABLES_CONFIG = {
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
            'display_name': 'RESOURCESTATUS (資源狀態歷史) ⭐',
            'row_count': 65139825,
            'time_field': 'OLDLASTSTATUSCHANGEDATE',
            'description': '設備狀態變更歷史表 - 狀態切換與原因'
        },
        {
            'name': 'DW_MES_RESOURCESTATUS_SHIFT',
            'display_name': 'RESOURCESTATUS_SHIFT (資源班次狀態)',
            'row_count': 74155046,
            'time_field': 'SHIFTDATE',
            'description': '設備狀態班次彙總表 - 班次級狀態/工時'
        },
        {
            'name': 'DW_MES_LOTWIPHISTORY',
            'display_name': 'LOTWIPHISTORY (批次流轉歷史) ⭐',
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
            'time_field': 'CREATEDATE',
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

app = Flask(__name__)

def get_db_connection():
    """建立數據庫連接"""
    try:
        connection = oracledb.connect(**DB_CONFIG)
        return connection
    except Exception as e:
        print(f"數據庫連接失敗: {e}")
        return None

def get_table_data(table_name, limit=1000, time_field=None):
    """
    查詢表的最後 N 筆資料

    Args:
        table_name: 表名
        limit: 返回行數
        time_field: 時間欄位（用於排序）

    Returns:
        dict: 包含 columns, data, row_count 的字典
    """
    connection = get_db_connection()
    if not connection:
        return {'error': '數據庫連接失敗'}

    try:
        cursor = connection.cursor()

        # 構建查詢 SQL
        if time_field:
            # 如果有時間欄位，按時間倒序
            sql = f"""
                SELECT * FROM (
                    SELECT * FROM {table_name}
                    WHERE {time_field} IS NOT NULL
                    ORDER BY {time_field} DESC
                ) WHERE ROWNUM <= {limit}
            """
        else:
            # 沒有時間欄位，直接取前 N 筆
            sql = f"""
                SELECT * FROM {table_name}
                WHERE ROWNUM <= {limit}
            """

        # 執行查詢
        cursor.execute(sql)

        # 獲取欄位名
        columns = [desc[0] for desc in cursor.description]

        # 獲取數據
        rows = cursor.fetchall()

        # 轉換為 JSON 可序列化格式
        data = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                # 處理日期類型
                if isinstance(value, datetime):
                    row_dict[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                # 處理 None
                elif value is None:
                    row_dict[col] = None
                # 處理數字
                elif isinstance(value, (int, float)):
                    row_dict[col] = value
                # 其他轉為字符串
                else:
                    row_dict[col] = str(value)
            data.append(row_dict)

        cursor.close()
        connection.close()

        return {
            'columns': columns,
            'data': data,
            'row_count': len(data)
        }

    except Exception as e:
        if connection:
            connection.close()
        return {'error': f'查詢失敗: {str(e)}'}

@app.route('/')
def index():
    """首頁 - 顯示所有表列表"""
    return render_template('index.html', tables_config=TABLES_CONFIG)

@app.route('/api/query_table', methods=['POST'])
def query_table():
    """API: 查詢指定表的資料"""
    data = request.get_json()
    table_name = data.get('table_name')
    limit = data.get('limit', 1000)
    time_field = data.get('time_field')

    if not table_name:
        return jsonify({'error': '請指定表名'}), 400

    result = get_table_data(table_name, limit, time_field)
    return jsonify(result)

@app.route('/api/get_table_info', methods=['GET'])
def get_table_info():
    """API: 獲取所有表的配置信息"""
    return jsonify(TABLES_CONFIG)

if __name__ == '__main__':
    # 檢查數據庫連接
    print("正在測試數據庫連接...")
    conn = get_db_connection()
    if conn:
        print("✓ 數據庫連接成功！")
        conn.close()
        print("\n啟動 Web 服務器...")
        print("請訪問: http://localhost:5000")
        print("\n提示:")
        print("- 點擊表名查看最後 1000 筆資料")
        print("- 大表會自動使用時間欄位排序")
        print("- 按 Ctrl+C 停止服務器")
        app.run(debug=True, host='0.0.0.0', port=5000)
    else:
        print("✗ 數據庫連接失敗，請檢查配置")
