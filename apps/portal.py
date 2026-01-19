"""
Unified MES portal with tabs for WIP report and table viewer.
"""

from datetime import datetime
import json
import time

import oracledb
import pandas as pd
from flask import Flask, jsonify, render_template, request
from sqlalchemy import create_engine, text

# Database connection config
DB_CONFIG = {
    'user': 'MBU1_R',
    'password': 'Pj2481mbu1',
    'dsn': '10.1.1.58:1521/DWDB'
}

# 16 core tables config (with categories)
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
            'time_field': 'DATADATE',
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

app = Flask(__name__, template_folder="templates")
ENGINE = create_engine(
    "oracle+oracledb://MBU1_R:Pj2481mbu1@10.1.1.58:1521/?service_name=DWDB",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)
CACHE_TTL_SECONDS = 60
CACHE = {}
EXCLUDED_LOCATIONS = [
    'ATEC',
    'F區',
    'F區焊接站',
    '報廢',
    '實驗室',
    '山東',
    '成型站_F區',
    '焊接F區',
    '無錫',
    '熒茂',
]
EXCLUDED_ASSET_STATUSES = ['Disapproved']


def get_db_connection():
    """Create a database connection."""
    try:
        return oracledb.connect(**DB_CONFIG)
    except Exception as exc:
        print(f"數據庫連接失敗: {exc}")
        return None


def read_sql_df(sql, params=None):
    """Run SQL with SQLAlchemy engine to avoid pandas DBAPI warnings."""
    with ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
        df.columns = [str(c).upper() for c in df.columns]
        return df


def cache_get(key):
    entry = CACHE.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if time.time() > expires_at:
        CACHE.pop(key, None)
        return None
    return value


def cache_set(key, value, ttl=CACHE_TTL_SECONDS):
    CACHE[key] = (time.time() + ttl, value)


def make_cache_key(prefix, days_back=None, filters=None):
    filters_key = json.dumps(filters, sort_keys=True, ensure_ascii=False) if filters else ""
    return f"{prefix}:{days_back}:{filters_key}"


def get_days_back(filters=None, default=365):
    if filters:
        return int(filters.get('days_back', default))
    return default


def get_table_columns(table_name):
    """Get column names for a table."""
    connection = get_db_connection()
    if not connection:
        return []

    try:
        cursor = connection.cursor()
        cursor.execute(f"SELECT * FROM {table_name} WHERE ROWNUM <= 1")
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        connection.close()
        return columns
    except Exception:
        if connection:
            connection.close()
        return []


def get_table_data(table_name, limit=1000, time_field=None, filters=None):
    """Fetch last N rows from a table with optional column filters.

    Args:
        table_name: Name of the table to query
        limit: Max rows to return (applied after filters)
        time_field: Column to sort by (DESC)
        filters: Dict of {column_name: filter_value} for LIKE filtering
    """
    connection = get_db_connection()
    if not connection:
        return {'error': '數據庫連接失敗'}

    try:
        cursor = connection.cursor()

        # Build WHERE conditions for filters
        where_conditions = []
        bind_params = {}

        if filters:
            for col, val in filters.items():
                if val and val.strip():
                    # Sanitize column name (only allow alphanumeric and underscore)
                    safe_col = ''.join(c for c in col if c.isalnum() or c == '_')
                    param_name = f"p_{safe_col}"
                    where_conditions.append(
                        f"UPPER(TO_CHAR({safe_col})) LIKE UPPER(:{param_name})"
                    )
                    bind_params[param_name] = f"%{val.strip()}%"

        # Build the query
        if time_field:
            time_condition = f"{time_field} IS NOT NULL"
            if where_conditions:
                all_conditions = " AND ".join([time_condition] + where_conditions)
            else:
                all_conditions = time_condition

            sql = f"""
                SELECT * FROM (
                    SELECT * FROM {table_name}
                    WHERE {all_conditions}
                    ORDER BY {time_field} DESC
                ) WHERE ROWNUM <= :row_limit
            """
        else:
            if where_conditions:
                all_conditions = " AND ".join(where_conditions)
                sql = f"""
                    SELECT * FROM (
                        SELECT * FROM {table_name}
                        WHERE {all_conditions}
                    ) WHERE ROWNUM <= :row_limit
                """
            else:
                sql = f"""
                    SELECT * FROM {table_name}
                    WHERE ROWNUM <= :row_limit
                """

        bind_params['row_limit'] = limit
        cursor.execute(sql, bind_params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        data = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                if isinstance(value, datetime):
                    row_dict[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                elif value is None:
                    row_dict[col] = None
                elif isinstance(value, (int, float)):
                    row_dict[col] = value
                else:
                    row_dict[col] = str(value)
            data.append(row_dict)

        cursor.close()
        connection.close()
        return {'columns': columns, 'data': data, 'row_count': len(data)}
    except Exception as exc:
        if connection:
            connection.close()
        return {'error': f'查詢失敗: {str(exc)}'}


def get_current_wip_subquery(days_back=90):
    """Returns subquery to get latest record per CONTAINER (current WIP snapshot).

    Uses ROW_NUMBER() analytic function for better performance.
    Only scans recent data (default 90 days) to reduce scan size.
    Filters out completed (8) and scrapped (128) status.
    Excludes DUMMY orders (MFGORDERNAME = 'DUMMY').

    Logic explanation:
    - PARTITION BY CONTAINERNAME: Groups records by each LOT
    - ORDER BY TXNDATE DESC: Orders by transaction time (newest first)
    - rn = 1: Takes only the latest record for each LOT
    - This gives us the current/latest status of each LOT
    """
    return f"""
        SELECT *
        FROM (
            SELECT w.*,
                   ROW_NUMBER() OVER (PARTITION BY w.CONTAINERNAME ORDER BY w.TXNDATE DESC) as rn
            FROM DW_MES_WIP w
            WHERE w.TXNDATE >= SYSDATE - {days_back}
              AND w.STATUS NOT IN (8, 128)
              AND (w.MFGORDERNAME IS NULL OR w.MFGORDERNAME <> 'DUMMY')
        )
        WHERE rn = 1
    """


def query_wip_by_spec_workcenter():
    """Query current WIP by spec/workcenter."""
    connection = get_db_connection()
    if not connection:
        return None

    try:
        sql = f"""
            SELECT
                SPECNAME,
                WORKCENTERNAME,
                COUNT(CONTAINERNAME) as LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2
            FROM ({get_current_wip_subquery()}) wip
            WHERE SPECNAME IS NOT NULL
              AND WORKCENTERNAME IS NOT NULL
            GROUP BY SPECNAME, WORKCENTERNAME
            ORDER BY TOTAL_QTY DESC
        """
        df = read_sql_df(sql)
        connection.close()
        return df
    except Exception as exc:
        connection.close()
        print(f"查詢失敗: {exc}")
        return None


def query_wip_by_product_line():
    """Query current WIP by product line."""
    connection = get_db_connection()
    if not connection:
        return None

    try:
        sql = f"""
            SELECT
                PRODUCTLINENAME_LEF,
                SPECNAME,
                WORKCENTERNAME,
                COUNT(CONTAINERNAME) as LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2
            FROM ({get_current_wip_subquery()}) wip
            WHERE PRODUCTLINENAME_LEF IS NOT NULL
            GROUP BY PRODUCTLINENAME_LEF, SPECNAME, WORKCENTERNAME
            ORDER BY TOTAL_QTY DESC
        """
        df = read_sql_df(sql)
        connection.close()
        return df
    except Exception as exc:
        connection.close()
        print(f"查詢失敗: {exc}")
        return None


def query_wip_summary():
    """Query current WIP summary."""
    connection = get_db_connection()
    if not connection:
        return None

    try:
        sql = f"""
            SELECT
                COUNT(CONTAINERNAME) as TOTAL_LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2,
                COUNT(DISTINCT SPECNAME) as SPEC_COUNT,
                COUNT(DISTINCT WORKCENTERNAME) as WORKCENTER_COUNT,
                COUNT(DISTINCT PRODUCTLINENAME_LEF) as PRODUCT_LINE_COUNT
            FROM ({get_current_wip_subquery()}) wip
        """
        cursor = connection.cursor()
        cursor.execute(sql)
        result = cursor.fetchone()
        cursor.close()
        connection.close()

        if not result:
            return None
        return {
            'total_lot_count': result[0] or 0,
            'total_qty': result[1] or 0,
            'total_qty2': result[2] or 0,
            'spec_count': result[3] or 0,
            'workcenter_count': result[4] or 0,
            'product_line_count': result[5] or 0
        }
    except Exception as exc:
        connection.close()
        print(f"查詢失敗: {exc}")
        return None


@app.route('/')
def portal_index():
    """Portal home with tabs."""
    return render_template('portal.html')


@app.route('/tables')
def tables_page():
    """Table viewer page."""
    return render_template('index.html', tables_config=TABLES_CONFIG)


@app.route('/wip')
def wip_page():
    """WIP report page."""
    return render_template('wip_report.html')


@app.route('/api/query_table', methods=['POST'])
def query_table():
    """API: query table data with optional column filters."""
    data = request.get_json()
    table_name = data.get('table_name')
    limit = data.get('limit', 1000)
    time_field = data.get('time_field')
    filters = data.get('filters')  # Dict of {column: value}

    if not table_name:
        return jsonify({'error': '請指定表名'}), 400

    result = get_table_data(table_name, limit, time_field, filters)
    return jsonify(result)


@app.route('/api/get_table_columns', methods=['POST'])
def api_get_table_columns():
    """API: get column names for a table."""
    data = request.get_json()
    table_name = data.get('table_name')

    if not table_name:
        return jsonify({'error': '請指定表名'}), 400

    columns = get_table_columns(table_name)
    return jsonify({'columns': columns})


@app.route('/api/get_table_info', methods=['GET'])
def get_table_info():
    """API: get tables config."""
    return jsonify(TABLES_CONFIG)


@app.route('/api/wip/summary')
def api_wip_summary():
    """API: Current WIP summary."""
    summary = query_wip_summary()
    if summary:
        return jsonify({'success': True, 'data': summary})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/wip/by_spec_workcenter')
def api_wip_by_spec_workcenter():
    """API: Current WIP by spec/workcenter."""
    df = query_wip_by_spec_workcenter()
    if df is not None:
        data = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': data, 'count': len(data)})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/wip/by_product_line')
def api_wip_by_product_line():
    """API: Current WIP by product line."""
    df = query_wip_by_product_line()
    if df is not None:
        data = df.to_dict(orient='records')
        if not df.empty:
            product_line_summary = df.groupby('PRODUCTLINENAME_LEF').agg({
                'LOT_COUNT': 'sum',
                'TOTAL_QTY': 'sum',
                'TOTAL_QTY2': 'sum'
            }).reset_index()
            summary = product_line_summary.to_dict(orient='records')
        else:
            summary = []
        return jsonify({'success': True, 'data': data, 'summary': summary, 'count': len(data)})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


def query_wip_by_status():
    """Query current WIP by status."""
    connection = get_db_connection()
    if not connection:
        return None

    try:
        sql = f"""
            SELECT
                CASE STATUS
                    WHEN 1 THEN 'Queue'
                    WHEN 2 THEN 'Run'
                    WHEN 4 THEN 'Hold'
                    ELSE 'Other(' || STATUS || ')'
                END as STATUS_NAME,
                STATUS,
                COUNT(CONTAINERNAME) as LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2
            FROM ({get_current_wip_subquery()}) wip
            GROUP BY STATUS
            ORDER BY LOT_COUNT DESC
        """
        df = read_sql_df(sql)
        connection.close()
        return df
    except Exception as exc:
        connection.close()
        print(f"查詢失敗: {exc}")
        return None


def query_wip_by_mfgorder(limit=100):
    """Query current WIP by mfg order (GA)."""
    connection = get_db_connection()
    if not connection:
        return None

    try:
        sql = f"""
            SELECT * FROM (
                SELECT
                    MFGORDERNAME,
                    COUNT(CONTAINERNAME) as LOT_COUNT,
                    SUM(QTY) as TOTAL_QTY,
                    SUM(QTY2) as TOTAL_QTY2
                FROM ({get_current_wip_subquery()}) wip
                WHERE MFGORDERNAME IS NOT NULL
                GROUP BY MFGORDERNAME
                ORDER BY TOTAL_QTY DESC
            ) WHERE ROWNUM <= :limit
        """
        df = read_sql_df(sql, params={'limit': limit})
        connection.close()
        return df
    except Exception as exc:
        connection.close()
        print(f"查詢失敗: {exc}")
        return None


@app.route('/api/wip/by_status')
def api_wip_by_status():
    """API: Current WIP by status."""
    df = query_wip_by_status()
    if df is not None:
        data = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/wip/by_mfgorder')
def api_wip_by_mfgorder():
    """API: Current WIP by mfg order (Top N)."""
    limit = request.args.get('limit', 100, type=int)
    df = query_wip_by_mfgorder(limit)
    if df is not None:
        data = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


# ============================================================
# Resource Status Report APIs
# ============================================================

def get_resource_latest_status_subquery(days_back=30):
    """Returns subquery to get latest status per resource.

    篩選條件:
    - (OBJECTCATEGORY = 'ASSEMBLY' AND OBJECTTYPE = 'ASSEMBLY') OR
      (OBJECTCATEGORY = 'WAFERSORT' AND OBJECTTYPE = 'WAFERSORT')

    Uses ROW_NUMBER() for performance.
    Only scans recent status changes (default 30 days).
    Includes JOBID for SDT/UDT drill-down.
    Includes PJ_LOTID from RESOURCE table.
    """
    location_filter = ""
    if EXCLUDED_LOCATIONS:
        excluded_locations = "', '".join(EXCLUDED_LOCATIONS)
        location_filter = f"AND (r.LOCATIONNAME IS NULL OR r.LOCATIONNAME NOT IN ('{excluded_locations}'))"

    asset_status_filter = ""
    if EXCLUDED_ASSET_STATUSES:
        excluded_assets = "', '".join(EXCLUDED_ASSET_STATUSES)
        asset_status_filter = f"AND (r.PJ_ASSETSSTATUS IS NULL OR r.PJ_ASSETSSTATUS NOT IN ('{excluded_assets}'))"

    return f"""
          WITH latest_txn AS (
              SELECT MAX(COALESCE(TXNDATE, LASTSTATUSCHANGEDATE)) AS MAX_TXNDATE
              FROM DW_MES_RESOURCESTATUS
          )
          SELECT *
          FROM (
              SELECT
                r.RESOURCEID,
                r.RESOURCENAME,
                r.OBJECTCATEGORY,
                r.OBJECTTYPE,
                r.RESOURCEFAMILYNAME,
                r.WORKCENTERNAME,
                r.LOCATIONNAME,
                r.VENDORNAME,
                r.VENDORMODEL,
                r.PJ_DEPARTMENT,
                r.PJ_ASSETSSTATUS,
                r.PJ_ISPRODUCTION,
                r.PJ_ISKEY,
                r.PJ_ISMONITOR,
                r.PJ_LOTID,
                r.DESCRIPTION,
                  s.NEWSTATUSNAME,
                  s.NEWREASONNAME,
                  s.LASTSTATUSCHANGEDATE,
                  s.OLDSTATUSNAME,
                s.OLDREASONNAME,
                  s.AVAILABILITY,
                  s.JOBID,
                  s.TXNDATE,
                  ROW_NUMBER() OVER (
                      PARTITION BY r.RESOURCEID
                      ORDER BY s.LASTSTATUSCHANGEDATE DESC NULLS LAST,
                               COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) DESC
                  ) AS rn
              FROM DW_MES_RESOURCE r
              JOIN DW_MES_RESOURCESTATUS s ON r.RESOURCEID = s.HISTORYID
              CROSS JOIN latest_txn lt
              WHERE ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
                  OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
                AND COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) >= lt.MAX_TXNDATE - {days_back}
                {location_filter}
                {asset_status_filter}
          )
          WHERE rn = 1
      """


def query_resource_status_summary(days_back=30):
    """Query resource status summary."""
    connection = get_db_connection()
    if not connection:
        return None

    try:
        sql = f"""
            SELECT
                COUNT(*) as TOTAL_COUNT,
                COUNT(DISTINCT WORKCENTERNAME) as WORKCENTER_COUNT,
                COUNT(DISTINCT RESOURCEFAMILYNAME) as FAMILY_COUNT,
                COUNT(DISTINCT PJ_DEPARTMENT) as DEPT_COUNT
            FROM ({get_resource_latest_status_subquery(days_back)}) rs
        """
        cursor = connection.cursor()
        cursor.execute(sql)
        result = cursor.fetchone()
        cursor.close()
        connection.close()

        if not result:
            return None
        return {
            'total_count': result[0] or 0,
            'workcenter_count': result[1] or 0,
            'family_count': result[2] or 0,
            'dept_count': result[3] or 0
        }
    except Exception as exc:
        if connection:
            connection.close()
        print(f"查詢失敗: {exc}")
        return None


def query_resource_by_status(days_back=30):
    """Query resource count by status."""
    try:
        sql = f"""
            SELECT
                NEWSTATUSNAME,
                COUNT(*) as COUNT
            FROM ({get_resource_latest_status_subquery(days_back)}) rs
            WHERE NEWSTATUSNAME IS NOT NULL
            GROUP BY NEWSTATUSNAME
            ORDER BY COUNT DESC
        """
        df = read_sql_df(sql)
        return df
    except Exception as exc:
        print(f"查詢失敗: {exc}")
        return None


def query_resource_by_workcenter(days_back=30):
    """Query resource count by workcenter and status."""
    try:
        sql = f"""
            SELECT
                WORKCENTERNAME,
                NEWSTATUSNAME,
                COUNT(*) as COUNT
            FROM ({get_resource_latest_status_subquery(days_back)}) rs
            WHERE WORKCENTERNAME IS NOT NULL
            GROUP BY WORKCENTERNAME, NEWSTATUSNAME
            ORDER BY WORKCENTERNAME, COUNT DESC
        """
        df = read_sql_df(sql)
        return df
    except Exception as exc:
        print(f"查詢失敗: {exc}")
        return None


def query_resource_detail(filters=None, limit=500, offset=0, days_back=30):
    """Query resource detail with optional filters."""
    try:
        base_sql = get_resource_latest_status_subquery(days_back)

        where_conditions = []
        if filters:
            if filters.get('workcenter'):
                where_conditions.append(
                    f"WORKCENTERNAME = '{filters['workcenter']}'"
                )
            if filters.get('status'):
                where_conditions.append(
                    f"NEWSTATUSNAME = '{filters['status']}'"
                )
            if filters.get('family'):
                where_conditions.append(
                    f"RESOURCEFAMILYNAME = '{filters['family']}'"
                )
            if filters.get('department'):
                where_conditions.append(
                    f"PJ_DEPARTMENT = '{filters['department']}'"
                )
            # New filters for production/key/monitor flags
            if filters.get('isProduction') is not None:
                where_conditions.append(
                    f"NVL(PJ_ISPRODUCTION, 0) = {1 if filters['isProduction'] else 0}"
                )
            if filters.get('isKey') is not None:
                where_conditions.append(
                    f"NVL(PJ_ISKEY, 0) = {1 if filters['isKey'] else 0}"
                )
            if filters.get('isMonitor') is not None:
                where_conditions.append(
                    f"NVL(PJ_ISMONITOR, 0) = {1 if filters['isMonitor'] else 0}"
                )

        if where_conditions:
            where_clause = " AND " + " AND ".join(where_conditions)
        else:
            where_clause = ""

        start_row = offset + 1
        end_row = offset + limit
        sql = f"""
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
                FROM ({base_sql}) rs
                WHERE 1=1 {where_clause}
            ) WHERE rn BETWEEN {start_row} AND {end_row}
        """
        df = read_sql_df(sql)

        # Convert datetime to string
        if 'LASTSTATUSCHANGEDATE' in df.columns:
            df['LASTSTATUSCHANGEDATE'] = df['LASTSTATUSCHANGEDATE'].apply(
                lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else None
            )

        return df
    except Exception as exc:
        print(f"查詢失敗: {exc}")
        return None


def query_resource_workcenter_status_matrix(days_back=30):
    """Query resource count matrix by workcenter and status category.

    Actual status values in database (verified):
    - PRD: Productive (生產中)
    - SBY: Standby (待機)
    - UDT: Unscheduled Down Time (非計畫停機)
    - SDT: Scheduled Down Time (計畫停機)
    - EGT: Engineering Time (工程時間)
    - NST: (待確認，暫歸類為 OTHER)
    - SCRAP: 報廢
    """
    try:
        # Use exact status values based on database verification
        sql = f"""
            SELECT
                WORKCENTERNAME,
                CASE NEWSTATUSNAME
                    WHEN 'PRD' THEN 'PRD'
                    WHEN 'SBY' THEN 'SBY'
                    WHEN 'UDT' THEN 'UDT'
                    WHEN 'SDT' THEN 'SDT'
                    WHEN 'EGT' THEN 'EGT'
                    WHEN 'NST' THEN 'NST'
                    WHEN 'SCRAP' THEN 'SCRAP'
                    ELSE 'OTHER'
                END as STATUS_CATEGORY,
                NEWSTATUSNAME,
                COUNT(*) as COUNT
            FROM ({get_resource_latest_status_subquery(days_back)}) rs
            WHERE WORKCENTERNAME IS NOT NULL
            GROUP BY WORKCENTERNAME,
                CASE NEWSTATUSNAME
                    WHEN 'PRD' THEN 'PRD'
                    WHEN 'SBY' THEN 'SBY'
                    WHEN 'UDT' THEN 'UDT'
                    WHEN 'SDT' THEN 'SDT'
                    WHEN 'EGT' THEN 'EGT'
                    WHEN 'NST' THEN 'NST'
                    WHEN 'SCRAP' THEN 'SCRAP'
                    ELSE 'OTHER'
                END,
                NEWSTATUSNAME
            ORDER BY WORKCENTERNAME, STATUS_CATEGORY
        """
        df = read_sql_df(sql)
        return df
    except Exception as exc:
        print(f"查詢失敗: {exc}")
        return None


def query_resource_filter_options(days_back=30):
    """Get available filter options.

    優化：合併成一個查詢，只掃描一次子查詢，大幅提升效能。
    """
    try:
        sql_latest = f"""
            SELECT
                WORKCENTERNAME,
                NEWSTATUSNAME,
                RESOURCEFAMILYNAME,
                PJ_DEPARTMENT
            FROM ({get_resource_latest_status_subquery(days_back)}) rs
        """
        latest_df = read_sql_df(sql_latest)

        sql_resource = """
            SELECT
                LOCATIONNAME,
                PJ_ASSETSSTATUS
            FROM DW_MES_RESOURCE r
            WHERE ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
               OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
        """
        resource_df = read_sql_df(sql_resource)

        # 從結果中提取各欄位的不重複值
        workcenters = sorted(latest_df['WORKCENTERNAME'].dropna().unique().tolist())
        statuses = sorted(latest_df['NEWSTATUSNAME'].dropna().unique().tolist())
        families = sorted(latest_df['RESOURCEFAMILYNAME'].dropna().unique().tolist())
        departments = sorted(latest_df['PJ_DEPARTMENT'].dropna().unique().tolist())
        locations = sorted(resource_df['LOCATIONNAME'].dropna().unique().tolist())
        assets_statuses = sorted(resource_df['PJ_ASSETSSTATUS'].dropna().unique().tolist())

        print(f"篩選選項: locations={len(locations)}, assets_statuses={len(assets_statuses)}")

        return {
            'workcenters': workcenters,
            'statuses': statuses,
            'families': families,
            'departments': departments,
            'locations': locations,
            'assets_statuses': assets_statuses
        }
    except Exception as exc:
        print(f"查詢失敗: {exc}")
        import traceback
        traceback.print_exc()
        return None


@app.route('/resource')
def resource_page():
    """Resource status report page."""
    return render_template('resource_status.html')


@app.route('/api/resource/summary')
def api_resource_summary():
    """API: Resource status summary."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_summary", days_back)
    summary = cache_get(cache_key)
    if summary is None:
        summary = query_resource_status_summary(days_back)
        if summary:
            cache_set(cache_key, summary)
    if summary:
        return jsonify({'success': True, 'data': summary})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/resource/by_status')
def api_resource_by_status():
    """API: Resource count by status."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_by_status", days_back)
    data = cache_get(cache_key)
    if data is None:
        df = query_resource_by_status(days_back)
        if df is not None:
            data = df.to_dict(orient='records')
            cache_set(cache_key, data)
        else:
            data = None
    if data is not None:
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/resource/by_workcenter')
def api_resource_by_workcenter():
    """API: Resource count by workcenter."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_by_workcenter", days_back)
    data = cache_get(cache_key)
    if data is None:
        df = query_resource_by_workcenter(days_back)
        if df is not None:
            data = df.to_dict(orient='records')
            cache_set(cache_key, data)
        else:
            data = None
    if data is not None:
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/resource/workcenter_status_matrix')
def api_resource_workcenter_status_matrix():
    """API: Resource count matrix by workcenter and status category."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_workcenter_matrix", days_back)
    data = cache_get(cache_key)
    if data is None:
        df = query_resource_workcenter_status_matrix(days_back)
        if df is not None:
            data = df.to_dict(orient='records')
            cache_set(cache_key, data)
        else:
            data = None
    if data is not None:
        return jsonify({'success': True, 'data': data})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/resource/detail', methods=['POST'])
def api_resource_detail():
    """API: Resource detail with filters."""
    data = request.get_json() or {}
    filters = data.get('filters')
    limit = data.get('limit', 500)
    offset = data.get('offset', 0)
    days_back = get_days_back(filters)

    df = query_resource_detail(filters, limit, offset, days_back)
    if df is not None:
        records = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': records, 'count': len(records), 'offset': offset})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/resource/filter_options')
def api_resource_filter_options():
    """API: Get filter options."""
    days_back = request.args.get('days_back', 30, type=int)
    cache_key = make_cache_key("resource_filter_options", days_back)
    options = cache_get(cache_key)
    if options is None:
        options = query_resource_filter_options(days_back)
        if options:
            cache_set(cache_key, options)
    if options:
        return jsonify({'success': True, 'data': options})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/resource/status_values')
def api_resource_status_values():
    """API: Get all distinct status values with counts (for verification)."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': '數據庫連接失敗'}), 500

    try:
        sql = """
            SELECT DISTINCT NEWSTATUSNAME, COUNT(*) as CNT
            FROM DW_MES_RESOURCESTATUS
            WHERE NEWSTATUSNAME IS NOT NULL
              AND LASTSTATUSCHANGEDATE >= SYSDATE - 30
            GROUP BY NEWSTATUSNAME
            ORDER BY CNT DESC
        """
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        connection.close()

        data = [{'status': row[0], 'count': row[1]} for row in rows]
        return jsonify({'success': True, 'data': data})
    except Exception as exc:
        if connection:
            connection.close()
        return jsonify({'success': False, 'error': str(exc)}), 500


# ============================================================
# Dashboard v2 APIs - 全廠機況 Dashboard
# ============================================================

def query_dashboard_kpi(filters=None):
    """Query overall KPI for dashboard header.

    指標分類:
    - RUN: PRD (生產中)
    - DOWN: UDT + SDT (停機)
    - IDLE: SBY + NST (閒置)
    - ENG: EGT (工程時間)

    OU% = PRD / (PRD + SBY + EGT + SDT + UDT) * 100
    """
    connection = get_db_connection()
    if not connection:
        return None

    try:
        days_back = get_days_back(filters)
        base_sql = get_resource_latest_status_subquery(days_back)

        # Build filter conditions
        where_conditions = []
        if filters:
            if filters.get('isProduction'):
                where_conditions.append("NVL(PJ_ISPRODUCTION, 0) = 1")
            if filters.get('isKey'):
                where_conditions.append("NVL(PJ_ISKEY, 0) = 1")
            if filters.get('isMonitor'):
                where_conditions.append("NVL(PJ_ISMONITOR, 0) = 1")
            # 支援多選廠區
            if filters.get('locations') and len(filters['locations']) > 0:
                loc_list = "', '".join(filters['locations'])
                where_conditions.append(f"LOCATIONNAME IN ('{loc_list}')")
            # 支援多選資產狀態
            if filters.get('assetsStatuses') and len(filters['assetsStatuses']) > 0:
                status_list = "', '".join(filters['assetsStatuses'])
                where_conditions.append(f"PJ_ASSETSSTATUS IN ('{status_list}')")

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        sql = f"""
            SELECT
                COUNT(*) as TOTAL,
                SUM(CASE WHEN NEWSTATUSNAME = 'PRD' THEN 1 ELSE 0 END) as PRD_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME = 'SBY' THEN 1 ELSE 0 END) as SBY_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME = 'UDT' THEN 1 ELSE 0 END) as UDT_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME = 'SDT' THEN 1 ELSE 0 END) as SDT_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME = 'EGT' THEN 1 ELSE 0 END) as EGT_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME = 'NST' THEN 1 ELSE 0 END) as NST_COUNT,
                SUM(CASE WHEN NEWSTATUSNAME NOT IN ('PRD','SBY','UDT','SDT','EGT','NST') THEN 1 ELSE 0 END) as OTHER_COUNT
            FROM ({base_sql}) rs
            WHERE {where_clause}
        """
        cursor = connection.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        cursor.close()
        connection.close()

        if not row:
            return None

        total = row[0] or 0
        prd = row[1] or 0
        sby = row[2] or 0
        udt = row[3] or 0
        sdt = row[4] or 0
        egt = row[5] or 0
        nst = row[6] or 0
        other = row[7] or 0

        # 指標分類
        run_count = prd                    # RUN = PRD
        down_count = udt + sdt             # DOWN = UDT + SDT
        idle_count = sby + nst             # IDLE = SBY + NST
        eng_count = egt                    # ENG = EGT

        # OU% = PRD / (PRD + SBY + EGT + SDT + UDT) * 100 (稼動率)
        # 分母不含 NST 和 OTHER
        operational = prd + sby + egt + sdt + udt
        ou_pct = round(prd / operational * 100, 1) if operational > 0 else 0

        # Run% = PRD / Total * 100
        run_pct = round(prd / total * 100, 1) if total > 0 else 0

        return {
            'total': total,
            'prd': prd,
            'sby': sby,
            'udt': udt,
            'sdt': sdt,
            'egt': egt,
            'nst': nst,
            'other': other,
            # 四大指標
            'run': run_count,
            'down': down_count,
            'idle': idle_count,
            'eng': eng_count,
            # 百分比
            'ou_pct': ou_pct,
            'run_pct': run_pct
        }
    except Exception as exc:
        if connection:
            connection.close()
        print(f"KPI 查詢失敗: {exc}")
        return None


# 工站合併與排序設定
# 順序: 0=切割, 1=焊接_DB, 2=焊接_WB, 3=焊接_DW, 4=成型, 5=去膠, 6=水吹砂, 7=電鍍, 8=移印, 9=切彎腳, 10=元件切割, 11=測試
WORKCENTER_GROUPS = {
    '切割': {
        'order': 0,
        'patterns': ['切割'],
        'exclude': ['元件切割', 'PKG_SAW']  # 元件切割是另一組
    },
    '焊接_DB': {
        'order': 1,
        'patterns': ['焊接_DB', '焊_DB_料', '焊_DB']
    },
    '焊接_WB': {
        'order': 2,
        'patterns': ['焊接_WB', '焊_WB_料', '焊_WB']
    },
    '焊接_DW': {
        'order': 3,
        'patterns': ['焊接_DW', '焊_DW', '焊_DW_料']
    },
    '成型': {
        'order': 4,
        'patterns': ['成型', '成型_料']
    },
    '去膠': {
        'order': 5,
        'patterns': ['去膠']
    },
    '水吹砂': {
        'order': 6,
        'patterns': ['水吹砂']
    },
    '電鍍': {
        'order': 7,
        'patterns': ['掛鍍', '滾鍍', '條鍍', '電鍍', '補鍍', 'TOTAI', 'BANDL']
    },
    '移印': {
        'order': 8,
        'patterns': ['移印']
    },
    '切彎腳': {
        'order': 9,
        'patterns': ['切彎腳']
    },
    '元件切割': {
        'order': 10,
        'patterns': ['元件切割', 'PKG_SAW']
    },
    '測試': {
        'order': 11,
        'patterns': ['TMTT', '測試']
    }
}


def get_workcenter_group(workcenter_name):
    """Map workcenter name to group name based on patterns."""
    if not workcenter_name:
        return None, 999

    wc_upper = workcenter_name.upper()

    for group_name, config in WORKCENTER_GROUPS.items():
        # Check exclusions first (for '切割' group)
        if 'exclude' in config:
            excluded = False
            for excl in config['exclude']:
                if excl.upper() in wc_upper:
                    excluded = True
                    break
            if excluded:
                continue

        # Check patterns
        for pattern in config['patterns']:
            if pattern.upper() in wc_upper:
                return group_name, config['order']

    return None, 999  # Unmatched workcenters


def query_workcenter_cards(filters=None):
    """Query workcenter status cards for dashboard with grouping.

    工站合併順序:
    0: 切割
    1: 焊接_DB (焊接_DB + 焊_DB_料)
    2: 焊接_WB (焊接_WB + 焊_WB_料)
    3: 焊接_DW
    4: 成型 (成型 + 成型_料)
    5: 去膠
    6: 水吹砂
    7: 電鍍 (掛鍍 + 滾鍍 + 條鍍)
    8: 移印
    9: 切彎腳
    10: 元件切割 (PKG_SAE)
    11: 測試 (TMTT)
    """
    try:
        days_back = get_days_back(filters)
        base_sql = get_resource_latest_status_subquery(days_back)

        # Build filter conditions
        where_conditions = []
        if filters:
            if filters.get('isProduction'):
                where_conditions.append("NVL(PJ_ISPRODUCTION, 0) = 1")
            if filters.get('isKey'):
                where_conditions.append("NVL(PJ_ISKEY, 0) = 1")
            if filters.get('isMonitor'):
                where_conditions.append("NVL(PJ_ISMONITOR, 0) = 1")
            # 支援多選廠區
            if filters.get('locations') and len(filters['locations']) > 0:
                loc_list = "', '".join(filters['locations'])
                where_conditions.append(f"LOCATIONNAME IN ('{loc_list}')")
            # 支援多選資產狀態
            if filters.get('assetsStatuses') and len(filters['assetsStatuses']) > 0:
                status_list = "', '".join(filters['assetsStatuses'])
                where_conditions.append(f"PJ_ASSETSSTATUS IN ('{status_list}')")

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        sql = f"""
            SELECT
                WORKCENTERNAME,
                COUNT(*) as TOTAL,
                SUM(CASE WHEN NEWSTATUSNAME = 'PRD' THEN 1 ELSE 0 END) as PRD,
                SUM(CASE WHEN NEWSTATUSNAME = 'SBY' THEN 1 ELSE 0 END) as SBY,
                SUM(CASE WHEN NEWSTATUSNAME = 'UDT' THEN 1 ELSE 0 END) as UDT,
                SUM(CASE WHEN NEWSTATUSNAME = 'SDT' THEN 1 ELSE 0 END) as SDT,
                SUM(CASE WHEN NEWSTATUSNAME = 'EGT' THEN 1 ELSE 0 END) as EGT,
                SUM(CASE WHEN NEWSTATUSNAME = 'NST' THEN 1 ELSE 0 END) as NST
            FROM ({base_sql}) rs
            WHERE WORKCENTERNAME IS NOT NULL AND {where_clause}
            GROUP BY WORKCENTERNAME
        """
        df = read_sql_df(sql)

        # Group workcenters
        grouped_data = {}
        ungrouped_data = []

        for _, row in df.iterrows():
            wc_name = row['WORKCENTERNAME']
            group_name, order = get_workcenter_group(wc_name)

            if group_name:
                if group_name not in grouped_data:
                    grouped_data[group_name] = {
                        'order': order,
                        'original_wcs': [],
                        'total': 0,
                        'prd': 0,
                        'sby': 0,
                        'udt': 0,
                        'sdt': 0,
                        'egt': 0,
                        'nst': 0
                    }
                grouped_data[group_name]['original_wcs'].append(wc_name)
                grouped_data[group_name]['total'] += int(row['TOTAL'])
                grouped_data[group_name]['prd'] += int(row['PRD'])
                grouped_data[group_name]['sby'] += int(row['SBY'])
                grouped_data[group_name]['udt'] += int(row['UDT'])
                grouped_data[group_name]['sdt'] += int(row['SDT'])
                grouped_data[group_name]['egt'] += int(row['EGT'])
                grouped_data[group_name]['nst'] += int(row['NST'])
            else:
                # Ungrouped workcenter
                ungrouped_data.append({
                    'workcenter': wc_name,
                    'original_wcs': [wc_name],
                    'order': 999,
                    'total': int(row['TOTAL']),
                    'prd': int(row['PRD']),
                    'sby': int(row['SBY']),
                    'udt': int(row['UDT']),
                    'sdt': int(row['SDT']),
                    'egt': int(row['EGT']),
                    'nst': int(row['NST'])
                })

        # Calculate OU% and build result
        result = []

        # Add grouped workcenters
        for group_name, data in grouped_data.items():
            prd = data['prd']
            sby = data['sby']
            egt = data['egt']
            sdt = data['sdt']
            udt = data['udt']
            total = data['total']

            # OU% = PRD / (PRD + SBY + EGT + SDT + UDT) * 100
            operational = prd + sby + egt + sdt + udt
            ou_pct = round(prd / operational * 100, 1) if operational > 0 else 0
            run_pct = round(prd / total * 100, 1) if total > 0 else 0

            result.append({
                'workcenter': group_name,
                'original_wcs': data['original_wcs'],
                'order': data['order'],
                'total': total,
                'prd': prd,
                'sby': sby,
                'udt': udt,
                'sdt': sdt,
                'egt': egt,
                'nst': data['nst'],
                'ou_pct': ou_pct,
                'run_pct': run_pct,
                'down': udt + sdt,
                'idle': sby + data['nst'],
                'eng': egt
            })

        # Add ungrouped workcenters
        for data in ungrouped_data:
            prd = data['prd']
            sby = data['sby']
            egt = data['egt']
            sdt = data['sdt']
            udt = data['udt']
            total = data['total']

            operational = prd + sby + egt + sdt + udt
            ou_pct = round(prd / operational * 100, 1) if operational > 0 else 0
            run_pct = round(prd / total * 100, 1) if total > 0 else 0

            result.append({
                'workcenter': data['workcenter'],
                'original_wcs': data['original_wcs'],
                'order': data['order'],
                'total': total,
                'prd': prd,
                'sby': sby,
                'udt': udt,
                'sdt': sdt,
                'egt': egt,
                'nst': data['nst'],
                'ou_pct': ou_pct,
                'run_pct': run_pct,
                'down': udt + sdt,
                'idle': sby + data['nst'],
                'eng': egt
            })

        # Sort by order
        result.sort(key=lambda x: (x['order'], -x['total']))

        return result
    except Exception as exc:
        print(f"工站卡片查詢失敗: {exc}")
        return None


def query_resource_detail_with_job(filters=None, limit=200, offset=0):
    """Query resource detail with JOB info for SDT/UDT drill-down.

    欄位來源說明:
    - 工單 (PJ_LOTID): 來自 DW_MES_RESOURCE.PJ_LOTID
    - 症狀 (SYMPTOMCODENAME): 來自 DW_MES_JOB.SYMPTOMCODENAME (透過 JOBID 關聯)
    - 原因碼 (CAUSECODENAME): 來自 DW_MES_JOB.CAUSECODENAME (透過 JOBID 關聯)
    - DownTime: 計算自最新的 LASTSTATUSCHANGEDATE - 每台機台自己的 LASTSTATUSCHANGEDATE (分鐘)

    Returns:
    - DataFrame with detail records
    - Also includes MAX_STATUS_TIME for Last Update display
    """
    try:
        days_back = get_days_back(filters)

        # 建立篩選條件
        location_filter = ""
        if EXCLUDED_LOCATIONS:
            excluded_locations = "', '".join(EXCLUDED_LOCATIONS)
            location_filter = f"AND (r.LOCATIONNAME IS NULL OR r.LOCATIONNAME NOT IN ('{excluded_locations}'))"

        asset_status_filter = ""
        if EXCLUDED_ASSET_STATUSES:
            excluded_assets = "', '".join(EXCLUDED_ASSET_STATUSES)
            asset_status_filter = f"AND (r.PJ_ASSETSSTATUS IS NULL OR r.PJ_ASSETSSTATUS NOT IN ('{excluded_assets}'))"

        where_conditions = []
        if filters:
            # 支援工站群組篩選 (合併後的工站)
            if filters.get('workcenter'):
                wc_filter = filters['workcenter']
                # 檢查是否為合併群組
                if wc_filter in WORKCENTER_GROUPS:
                    patterns = WORKCENTER_GROUPS[wc_filter]['patterns']
                    pattern_conditions = []
                    for p in patterns:
                        pattern_conditions.append(f"UPPER(rs.WORKCENTERNAME) LIKE '%{p.upper()}%'")
                    where_conditions.append(f"({' OR '.join(pattern_conditions)})")
                else:
                    where_conditions.append(f"rs.WORKCENTERNAME = '{wc_filter}'")

            if filters.get('original_wcs'):
                # 如果有原始工站列表，直接用 IN 查詢
                wcs = filters['original_wcs']
                wc_list = "', '".join(wcs)
                where_conditions.append(f"rs.WORKCENTERNAME IN ('{wc_list}')")

            if filters.get('status'):
                where_conditions.append(f"rs.NEWSTATUSNAME = '{filters['status']}'")
            if filters.get('isProduction'):
                where_conditions.append("NVL(rs.PJ_ISPRODUCTION, 0) = 1")
            if filters.get('isKey'):
                where_conditions.append("NVL(rs.PJ_ISKEY, 0) = 1")
            if filters.get('isMonitor'):
                where_conditions.append("NVL(rs.PJ_ISMONITOR, 0) = 1")
            # 支援多選廠區
            if filters.get('locations') and len(filters['locations']) > 0:
                loc_list = "', '".join(filters['locations'])
                where_conditions.append(f"rs.LOCATIONNAME IN ('{loc_list}')")
            # 支援多選資產狀態
            if filters.get('assetsStatuses') and len(filters['assetsStatuses']) > 0:
                status_list = "', '".join(filters['assetsStatuses'])
                where_conditions.append(f"rs.PJ_ASSETSSTATUS IN ('{status_list}')")

        # 預設只顯示 DOWN 狀態 (UDT, SDT)
        where_conditions.append("rs.NEWSTATUSNAME IN ('UDT', 'SDT')")

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # Left join with JOB table for SDT/UDT details
        # JOB 匹配邏輯: RESOURCEID + CREATEDATE = LASTSTATUSCHANGEDATE (等值匹配)
        # PJ_LOTID 來自 RESOURCE 表
        # SYMPTOMCODENAME, CAUSECODENAME, JOBID 等來自 JOB 表
        # DOWN_MINUTES: 使用全體最大 LASTSTATUSCHANGEDATE - 每台機台自己的時間
        # 注意: 將所有 CTE 放在同一層級，避免巢狀 WITH 子句 (Oracle 不支援)
        start_row = offset + 1
        end_row = offset + limit
        sql = f"""
            WITH latest_txn AS (
                SELECT MAX(COALESCE(TXNDATE, LASTSTATUSCHANGEDATE)) AS MAX_TXNDATE
                FROM DW_MES_RESOURCESTATUS
            ),
            base_data AS (
                SELECT *
                FROM (
                    SELECT
                        r.RESOURCEID,
                        r.RESOURCENAME,
                        r.OBJECTCATEGORY,
                        r.OBJECTTYPE,
                        r.RESOURCEFAMILYNAME,
                        r.WORKCENTERNAME,
                        r.LOCATIONNAME,
                        r.VENDORNAME,
                        r.VENDORMODEL,
                        r.PJ_DEPARTMENT,
                        r.PJ_ASSETSSTATUS,
                        r.PJ_ISPRODUCTION,
                        r.PJ_ISKEY,
                        r.PJ_ISMONITOR,
                        r.PJ_LOTID,
                        r.DESCRIPTION,
                        s.NEWSTATUSNAME,
                        s.NEWREASONNAME,
                        s.LASTSTATUSCHANGEDATE,
                        s.OLDSTATUSNAME,
                        s.OLDREASONNAME,
                        s.AVAILABILITY,
                        s.JOBID,
                        s.TXNDATE,
                        ROW_NUMBER() OVER (
                            PARTITION BY r.RESOURCEID
                            ORDER BY s.LASTSTATUSCHANGEDATE DESC NULLS LAST,
                                     COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) DESC
                        ) AS rn
                    FROM DW_MES_RESOURCE r
                    JOIN DW_MES_RESOURCESTATUS s ON r.RESOURCEID = s.HISTORYID
                    CROSS JOIN latest_txn lt
                    WHERE ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
                        OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
                      AND COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) >= lt.MAX_TXNDATE - {days_back}
                      {location_filter}
                      {asset_status_filter}
                )
                WHERE rn = 1
            ),
            max_time AS (
                SELECT MAX(LASTSTATUSCHANGEDATE) AS MAX_STATUS_TIME FROM base_data
            )
            SELECT * FROM (
                SELECT
                    rs.RESOURCENAME,
                    rs.WORKCENTERNAME,
                    rs.RESOURCEFAMILYNAME,
                    rs.NEWSTATUSNAME,
                    rs.NEWREASONNAME,
                    rs.LASTSTATUSCHANGEDATE,
                    rs.PJ_DEPARTMENT,
                    rs.VENDORNAME,
                    rs.VENDORMODEL,
                    rs.PJ_ISPRODUCTION,
                    rs.PJ_ISKEY,
                    rs.PJ_ISMONITOR,
                    j.JOBID,
                    rs.PJ_LOTID,
                    j.JOBORDERNAME,
                    j.JOBSTATUS,
                    j.SYMPTOMCODENAME,
                    j.CAUSECODENAME,
                    j.REPAIRCODENAME,
                    j.CREATEDATE as JOB_CREATEDATE,
                    j.FIRSTCLOCKONDATE,
                    mt.MAX_STATUS_TIME,
                    ROUND((mt.MAX_STATUS_TIME - rs.LASTSTATUSCHANGEDATE) * 24 * 60, 0) as DOWN_MINUTES,
                    ROW_NUMBER() OVER (
                        ORDER BY
                            CASE rs.NEWSTATUSNAME
                                WHEN 'UDT' THEN 1
                                WHEN 'SDT' THEN 2
                                ELSE 3
                            END,
                            rs.LASTSTATUSCHANGEDATE DESC NULLS LAST
                    ) AS rn
                FROM base_data rs
                CROSS JOIN max_time mt
                LEFT JOIN DW_MES_JOB j ON j.RESOURCEID = rs.RESOURCEID
                                       AND j.CREATEDATE = rs.LASTSTATUSCHANGEDATE
                WHERE {where_clause}
            ) WHERE rn BETWEEN {start_row} AND {end_row}
        """
        df = read_sql_df(sql)

        # Get max_status_time for Last Update display
        max_status_time = None
        if 'MAX_STATUS_TIME' in df.columns and len(df) > 0:
            max_status_time = df['MAX_STATUS_TIME'].iloc[0]
            if pd.notna(max_status_time):
                max_status_time = max_status_time.strftime('%Y-%m-%d %H:%M:%S')

        # Convert datetime columns
        datetime_cols = ['LASTSTATUSCHANGEDATE', 'JOB_CREATEDATE', 'FIRSTCLOCKONDATE', 'MAX_STATUS_TIME']
        for col in datetime_cols:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else None
                )

        return df, max_status_time
    except Exception as exc:
        print(f"明細查詢失敗: {exc}")
        return None, None


@app.route('/api/dashboard/kpi', methods=['POST'])
def api_dashboard_kpi():
    """API: Dashboard KPI data."""
    data = request.get_json() or {}
    filters = data.get('filters')

    days_back = get_days_back(filters)
    cache_key = make_cache_key("dashboard_kpi", days_back, filters)
    kpi = cache_get(cache_key)
    if kpi is None:
        kpi = query_dashboard_kpi(filters)
        if kpi:
            cache_set(cache_key, kpi)
    if kpi:
        return jsonify({'success': True, 'data': kpi})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/dashboard/workcenter_cards', methods=['POST'])
def api_dashboard_workcenter_cards():
    """API: Workcenter cards data."""
    data = request.get_json() or {}
    filters = data.get('filters')

    days_back = get_days_back(filters)
    cache_key = make_cache_key("dashboard_workcenter_cards", days_back, filters)
    cards = cache_get(cache_key)
    if cards is None:
        cards = query_workcenter_cards(filters)
        if cards is not None:
            cache_set(cache_key, cards)
    if cards is not None:
        return jsonify({'success': True, 'data': cards})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/dashboard/detail', methods=['POST'])
def api_dashboard_detail():
    """API: Resource detail with JOB info."""
    data = request.get_json() or {}
    filters = data.get('filters')
    limit = data.get('limit', 200)
    offset = data.get('offset', 0)

    df, max_status_time = query_resource_detail_with_job(filters, limit, offset)
    if df is not None:
        records = df.to_dict(orient='records')
        return jsonify({
            'success': True,
            'data': records,
            'count': len(records),
            'offset': offset,
            'max_status_time': max_status_time
        })
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


def query_ou_trend(days=7, filters=None):
    """Query OU% trend by date using RESOURCESTATUS_SHIFT table.

    Uses HOURS field to calculate actual time-based OU%.
    OU% = PRD_HOURS / (PRD + SBY + EGT + SDT + UDT) * 100

    Args:
        days: Number of days to query (default 7)
        filters: Optional filters (isProduction, isKey, isMonitor)

    Returns:
        List of {date, ou_pct, prd_hours, total_hours} records
    """
    try:
        # Build location and asset status filters
        location_filter = ""
        if EXCLUDED_LOCATIONS:
            excluded_locations = "', '".join(EXCLUDED_LOCATIONS)
            location_filter = f"AND (ss.LOCATIONNAME IS NULL OR ss.LOCATIONNAME NOT IN ('{excluded_locations}'))"

        asset_status_filter = ""
        if EXCLUDED_ASSET_STATUSES:
            excluded_assets = "', '".join(EXCLUDED_ASSET_STATUSES)
            asset_status_filter = f"AND (ss.PJ_ASSETSSTATUS IS NULL OR ss.PJ_ASSETSSTATUS NOT IN ('{excluded_assets}'))"

        # Build filter conditions for equipment flags
        flag_conditions = []
        if filters:
            if filters.get('isProduction'):
                flag_conditions.append("r.PJ_ISPRODUCTION = 1")
            if filters.get('isKey'):
                flag_conditions.append("r.PJ_ISKEY = 1")
            if filters.get('isMonitor'):
                flag_conditions.append("r.PJ_ISMONITOR = 1")

        flag_filter = ""
        if flag_conditions:
            flag_filter = "AND " + " AND ".join(flag_conditions)

        sql = f"""
            SELECT
                TRUNC(ss.TXNDATE) as DATA_DATE,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SBY' THEN ss.HOURS ELSE 0 END) as SBY_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'UDT' THEN ss.HOURS ELSE 0 END) as UDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'SDT' THEN ss.HOURS ELSE 0 END) as SDT_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'EGT' THEN ss.HOURS ELSE 0 END) as EGT_HOURS,
                SUM(ss.HOURS) as TOTAL_HOURS
            FROM DW_MES_RESOURCESTATUS_SHIFT ss
            JOIN DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
            WHERE ss.TXNDATE >= TRUNC(SYSDATE) - {days}
              AND ss.TXNDATE < TRUNC(SYSDATE)
              AND ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
                   OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
              {location_filter}
              {asset_status_filter}
              {flag_filter}
            GROUP BY TRUNC(ss.TXNDATE)
            ORDER BY DATA_DATE
        """
        df = read_sql_df(sql)

        result = []
        for _, row in df.iterrows():
            prd = float(row['PRD_HOURS'] or 0)
            sby = float(row['SBY_HOURS'] or 0)
            udt = float(row['UDT_HOURS'] or 0)
            sdt = float(row['SDT_HOURS'] or 0)
            egt = float(row['EGT_HOURS'] or 0)

            # OU% denominator: PRD + SBY + EGT + SDT + UDT (excludes NST)
            denominator = prd + sby + egt + sdt + udt
            ou_pct = round((prd / denominator * 100), 2) if denominator > 0 else 0

            result.append({
                'date': row['DATA_DATE'].strftime('%Y-%m-%d') if pd.notna(row['DATA_DATE']) else None,
                'ou_pct': ou_pct,
                'prd_hours': round(prd, 1),
                'sby_hours': round(sby, 1),
                'udt_hours': round(udt, 1),
                'sdt_hours': round(sdt, 1),
                'egt_hours': round(egt, 1),
                'total_hours': round(float(row['TOTAL_HOURS'] or 0), 1)
            })

        return result
    except Exception as exc:
        print(f"OU趨勢查詢失敗: {exc}")
        import traceback
        traceback.print_exc()
        return None


def query_utilization_heatmap(days=7, filters=None):
    """Query equipment utilization heatmap data by workcenter and date.

    Uses HOURS field to calculate PRD% per workcenter per day.

    Args:
        days: Number of days to query (default 7)
        filters: Optional filters (isProduction, isKey, isMonitor)

    Returns:
        List of {workcenter, date, prd_pct, prd_hours, total_hours} records
    """
    try:
        # Build location and asset status filters
        location_filter = ""
        if EXCLUDED_LOCATIONS:
            excluded_locations = "', '".join(EXCLUDED_LOCATIONS)
            location_filter = f"AND (ss.LOCATIONNAME IS NULL OR ss.LOCATIONNAME NOT IN ('{excluded_locations}'))"

        asset_status_filter = ""
        if EXCLUDED_ASSET_STATUSES:
            excluded_assets = "', '".join(EXCLUDED_ASSET_STATUSES)
            asset_status_filter = f"AND (ss.PJ_ASSETSSTATUS IS NULL OR ss.PJ_ASSETSSTATUS NOT IN ('{excluded_assets}'))"

        # Build filter conditions for equipment flags
        flag_conditions = []
        if filters:
            if filters.get('isProduction'):
                flag_conditions.append("r.PJ_ISPRODUCTION = 1")
            if filters.get('isKey'):
                flag_conditions.append("r.PJ_ISKEY = 1")
            if filters.get('isMonitor'):
                flag_conditions.append("r.PJ_ISMONITOR = 1")

        flag_filter = ""
        if flag_conditions:
            flag_filter = "AND " + " AND ".join(flag_conditions)

        sql = f"""
            SELECT
                ss.WORKCENTERNAME,
                TRUNC(ss.TXNDATE) as DATA_DATE,
                SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
                SUM(CASE WHEN ss.OLDSTATUSNAME IN ('PRD', 'SBY', 'UDT', 'SDT', 'EGT') THEN ss.HOURS ELSE 0 END) as AVAIL_HOURS
            FROM DW_MES_RESOURCESTATUS_SHIFT ss
            JOIN DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
            WHERE ss.TXNDATE >= TRUNC(SYSDATE) - {days}
              AND ss.TXNDATE < TRUNC(SYSDATE)
              AND ss.WORKCENTERNAME IS NOT NULL
              AND ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
                   OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
              {location_filter}
              {asset_status_filter}
              {flag_filter}
            GROUP BY ss.WORKCENTERNAME, TRUNC(ss.TXNDATE)
            ORDER BY ss.WORKCENTERNAME, DATA_DATE
        """
        df = read_sql_df(sql)

        # Group by workcenter for heatmap format
        result = []
        for _, row in df.iterrows():
            prd = float(row['PRD_HOURS'] or 0)
            avail = float(row['AVAIL_HOURS'] or 0)
            prd_pct = round((prd / avail * 100), 2) if avail > 0 else 0

            wc_name = row['WORKCENTERNAME']
            # Apply workcenter grouping
            group_name, _ = get_workcenter_group(wc_name)

            result.append({
                'workcenter': wc_name,
                'group': group_name,
                'date': row['DATA_DATE'].strftime('%Y-%m-%d') if pd.notna(row['DATA_DATE']) else None,
                'prd_pct': prd_pct,
                'prd_hours': round(prd, 1),
                'avail_hours': round(avail, 1)
            })

        return result
    except Exception as exc:
        print(f"利用率熱力圖查詢失敗: {exc}")
        import traceback
        traceback.print_exc()
        return None


@app.route('/api/dashboard/ou_trend', methods=['POST'])
def api_dashboard_ou_trend():
    """API: OU% trend data for line chart."""
    data = request.get_json() or {}
    filters = data.get('filters')
    days = data.get('days', 7)

    days_back = get_days_back(filters)
    cache_key = make_cache_key("dashboard_ou_trend", days, filters)
    trend = cache_get(cache_key)
    if trend is None:
        trend = query_ou_trend(days, filters)
        if trend is not None:
            cache_set(cache_key, trend, ttl=300)  # 5 min cache
    if trend is not None:
        return jsonify({'success': True, 'data': trend})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/dashboard/utilization_heatmap', methods=['POST'])
def api_dashboard_utilization_heatmap():
    """API: Utilization heatmap data."""
    data = request.get_json() or {}
    filters = data.get('filters')
    days = data.get('days', 7)

    cache_key = make_cache_key("dashboard_heatmap", days, filters)
    heatmap = cache_get(cache_key)
    if heatmap is None:
        heatmap = query_utilization_heatmap(days, filters)
        if heatmap is not None:
            cache_set(cache_key, heatmap, ttl=300)  # 5 min cache
    if heatmap is not None:
        return jsonify({'success': True, 'data': heatmap})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


# ============================================================
# WIP Distribution Table API (即時 WIP 分布表)
# ============================================================

def query_wip_distribution_filter_options(days_back=90):
    """取得 WIP 分布表的篩選選項: packages(PRODUCTLINENAME_LEF), types(PJ_TYPE), areas(PJ_PRODUCEREGION), lot_statuses"""
    try:
        base_sql = get_current_wip_subquery(days_back)
        sql = f"""
            SELECT
                PRODUCTLINENAME_LEF,
                PJ_TYPE,
                PJ_PRODUCEREGION,
                HOLDREASONNAME
            FROM ({base_sql}) wip
        """
        df = read_sql_df(sql)

        # 提取不重複值並排序
        packages = sorted([x for x in df['PRODUCTLINENAME_LEF'].dropna().unique().tolist() if x])
        types = sorted([x for x in df['PJ_TYPE'].dropna().unique().tolist() if x])
        areas = sorted([x for x in df['PJ_PRODUCEREGION'].dropna().unique().tolist() if x])

        # Lot 狀態: 根據 HOLDREASONNAME 判斷 - 有值=Hold, 無值=Active
        lot_statuses = ['Active', 'Hold']

        return {
            'packages': packages,
            'types': types,
            'areas': areas,
            'lot_statuses': lot_statuses
        }
    except Exception as exc:
        print(f"WIP 篩選選項查詢失敗: {exc}")
        import traceback
        traceback.print_exc()
        return None


def query_wip_distribution_pivot_columns(filters=None, days_back=90):
    """取得 WIP 分布表的 Pivot 欄位列表 (只回傳有資料的 Workcenter|Spec 組合)"""
    try:
        base_sql = get_current_wip_subquery(days_back)

        # 建立篩選條件
        where_conditions = []
        if filters:
            if filters.get('packages') and len(filters['packages']) > 0:
                pkg_list = "', '".join(filters['packages'])
                where_conditions.append(f"PRODUCTLINENAME_LEF IN ('{pkg_list}')")
            if filters.get('types') and len(filters['types']) > 0:
                type_list = "', '".join(filters['types'])
                where_conditions.append(f"PJ_TYPE IN ('{type_list}')")
            if filters.get('areas') and len(filters['areas']) > 0:
                area_list = "', '".join(filters['areas'])
                where_conditions.append(f"PJ_PRODUCEREGION IN ('{area_list}')")
            # Lot 狀態篩選: Active = HOLDREASONNAME IS NULL, Hold = HOLDREASONNAME IS NOT NULL
            if filters.get('lot_statuses') and len(filters['lot_statuses']) > 0:
                status_conds = []
                if 'Active' in filters['lot_statuses']:
                    status_conds.append("HOLDREASONNAME IS NULL")
                if 'Hold' in filters['lot_statuses']:
                    status_conds.append("HOLDREASONNAME IS NOT NULL")
                if status_conds:
                    where_conditions.append(f"({' OR '.join(status_conds)})")

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        sql = f"""
            SELECT
                WORKCENTERNAME,
                SPECNAME as WC_SPEC,
                COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT
            FROM ({base_sql}) wip
            WHERE WORKCENTERNAME IS NOT NULL
              AND {where_clause}
            GROUP BY WORKCENTERNAME, SPECNAME
            ORDER BY LOT_COUNT DESC
        """
        df = read_sql_df(sql)

        # 轉換為 pivot 欄位列表，並套用 WORKCENTER_GROUPS 分組邏輯
        pivot_columns = []
        for _, row in df.iterrows():
            wc = row['WORKCENTERNAME'] or ''
            spec = row['WC_SPEC'] or ''
            # 使用 get_workcenter_group 取得合併後的群組名稱和排序
            group_name, order = get_workcenter_group(wc)
            display_wc = group_name if group_name else wc  # 合併後的顯示名稱
            key = f"{wc}|{spec}"  # key 仍使用原始 workcenter 以便匹配
            pivot_columns.append({
                'key': key,
                'workcenter': wc,           # 原始 workcenter
                'workcenter_group': display_wc,  # 合併後的群組名稱
                'order': order,             # 排序順序
                'spec': spec,
                'count': int(row['LOT_COUNT'] or 0)
            })

        return pivot_columns
    except Exception as exc:
        print(f"WIP Pivot 欄位查詢失敗: {exc}")
        import traceback
        traceback.print_exc()
        return None


def query_wip_distribution(filters=None, limit=500, offset=0, days_back=90):
    """查詢 WIP 分布表主數據，回傳每個 Lot 的基本資訊及其所在的 Workcenter|Spec"""
    try:
        base_sql = get_current_wip_subquery(days_back)

        # 建立篩選條件
        where_conditions = []
        if filters:
            if filters.get('packages') and len(filters['packages']) > 0:
                pkg_list = "', '".join(filters['packages'])
                where_conditions.append(f"PRODUCTLINENAME_LEF IN ('{pkg_list}')")
            if filters.get('types') and len(filters['types']) > 0:
                type_list = "', '".join(filters['types'])
                where_conditions.append(f"PJ_TYPE IN ('{type_list}')")
            if filters.get('areas') and len(filters['areas']) > 0:
                area_list = "', '".join(filters['areas'])
                where_conditions.append(f"PJ_PRODUCEREGION IN ('{area_list}')")
            # Lot 狀態篩選: Active = HOLDREASONNAME IS NULL, Hold = HOLDREASONNAME IS NOT NULL
            if filters.get('lot_statuses') and len(filters['lot_statuses']) > 0:
                status_conds = []
                if 'Active' in filters['lot_statuses']:
                    status_conds.append("HOLDREASONNAME IS NULL")
                if 'Hold' in filters['lot_statuses']:
                    status_conds.append("HOLDREASONNAME IS NOT NULL")
                if status_conds:
                    where_conditions.append(f"({' OR '.join(status_conds)})")
            if filters.get('search'):
                search_term = filters['search'].replace("'", "''")
                where_conditions.append(
                    f"(UPPER(MFGORDERNAME) LIKE UPPER('%{search_term}%') "
                    f"OR UPPER(CONTAINERNAME) LIKE UPPER('%{search_term}%'))"
                )

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # 先查詢總筆數
        count_sql = f"""
            SELECT COUNT(DISTINCT CONTAINERNAME) as TOTAL_COUNT
            FROM ({base_sql}) wip
            WHERE {where_clause}
        """
        count_df = read_sql_df(count_sql)
        total_count = int(count_df['TOTAL_COUNT'].iloc[0]) if len(count_df) > 0 else 0

        # 分頁查詢主數據
        start_row = offset + 1
        end_row = offset + limit
        sql = f"""
            SELECT * FROM (
                SELECT
                    MFGORDERNAME,
                    CONTAINERNAME,
                    SPECNAME,
                    PRODUCTLINENAME_LEF,
                    WAFERLOT,
                    PJ_TYPE,
                    PJ_PRODUCEREGION,
                    EQUIPMENTS,
                    WORKCENTERNAME,
                    STATUS,
                    HOLDREASONNAME,
                    QTY,
                    QTY2,
                    TXNDATE,
                    ROW_NUMBER() OVER (ORDER BY TXNDATE DESC, MFGORDERNAME, CONTAINERNAME) as rn
                FROM ({base_sql}) wip
                WHERE {where_clause}
            ) WHERE rn BETWEEN {start_row} AND {end_row}
        """
        df = read_sql_df(sql)

        # 轉換為回傳格式
        rows = []
        for _, row in df.iterrows():
            wc = row['WORKCENTERNAME'] or ''
            spec = row['SPECNAME'] or ''
            pivot_key = f"{wc}|{spec}"
            # Lot 狀態判斷: HOLDREASONNAME 有值=Hold, 無值=Active
            hold_reason = row['HOLDREASONNAME']
            lot_status = 'Hold' if (pd.notna(hold_reason) and hold_reason) else 'Active'

            rows.append({
                'MFGORDERNAME': row['MFGORDERNAME'],
                'CONTAINERNAME': row['CONTAINERNAME'],
                'SPECNAME': row['SPECNAME'],
                'PRODUCTLINENAME_LEF': row['PRODUCTLINENAME_LEF'],
                'WAFERLOT': row['WAFERLOT'],
                'PJ_TYPE': row['PJ_TYPE'],
                'PJ_PRODUCEREGION': row['PJ_PRODUCEREGION'],
                'EQUIPMENTS': row['EQUIPMENTS'],
                'WORKCENTERNAME': row['WORKCENTERNAME'],
                'LOT_STATUS': lot_status,
                'HOLDREASONNAME': hold_reason if pd.notna(hold_reason) else None,
                'QTY': int(row['QTY']) if pd.notna(row['QTY']) else 0,
                'QTY2': int(row['QTY2']) if pd.notna(row['QTY2']) else 0,
                'pivot_key': pivot_key
            })

        return {
            'rows': rows,
            'total_count': total_count,
            'offset': offset,
            'limit': limit
        }
    except Exception as exc:
        print(f"WIP 分布表查詢失敗: {exc}")
        import traceback
        traceback.print_exc()
        return None


@app.route('/api/wip/distribution/filter_options')
def api_wip_distribution_filter_options():
    """API: 取得 WIP 分布表篩選選項"""
    days_back = request.args.get('days_back', 90, type=int)
    cache_key = make_cache_key("wip_dist_filter_options", days_back)
    options = cache_get(cache_key)
    if options is None:
        options = query_wip_distribution_filter_options(days_back)
        if options:
            cache_set(cache_key, options, ttl=600)  # 10 分鐘快取
    if options:
        return jsonify({'success': True, 'data': options})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/wip/distribution/pivot_columns', methods=['POST'])
def api_wip_distribution_pivot_columns():
    """API: 取得 WIP 分布表 Pivot 欄位列表"""
    data = request.get_json() or {}
    filters = data.get('filters')
    days_back = data.get('days_back', 90)

    cache_key = make_cache_key("wip_dist_pivot_cols", days_back, filters)
    columns = cache_get(cache_key)
    if columns is None:
        columns = query_wip_distribution_pivot_columns(filters, days_back)
        if columns is not None:
            cache_set(cache_key, columns, ttl=300)  # 5 分鐘快取
    if columns is not None:
        return jsonify({'success': True, 'data': columns})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/wip/distribution', methods=['POST'])
def api_wip_distribution():
    """API: 查詢 WIP 分布表主數據"""
    data = request.get_json() or {}
    filters = data.get('filters')
    limit = min(data.get('limit', 500), 1000)  # 最大 1000 筆
    offset = data.get('offset', 0)
    days_back = data.get('days_back', 90)

    result = query_wip_distribution(filters, limit, offset, days_back)
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500


if __name__ == '__main__':
    print("正在測試數據庫連接...")
    conn = get_db_connection()
    if conn:
        print("? 數據庫連接成功！")
        conn.close()
        print("\n啟動 Web 服務器...")
        print("請訪問: http://localhost:5000")
        print("按 Ctrl+C 停止服務器\n")
        app.run(debug=True, host='0.0.0.0', port=5000)
    else:
        print("? 數據庫連接失敗，請檢查配置")

