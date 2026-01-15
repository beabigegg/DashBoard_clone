"""
WIP 報表查詢工具
查詢當前在制品 (Work In Process) 的數量統計
"""

import oracledb
import pandas as pd
from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta

# 數據庫連接配置
DB_CONFIG = {
    'user': 'MBU1_R',
    'password': 'Pj2481mbu1',
    'dsn': '10.1.1.58:1521/DWDB'
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

def query_wip_by_spec_workcenter(days=7):
    """
    查詢各 SPECNAME 及 WORKCENTERNAME 對應的當下 WIP 數量

    Args:
        days: 查詢最近幾天的數據（默認 7 天）

    Returns:
        DataFrame: 包含統計數據
    """
    connection = get_db_connection()
    if not connection:
        return None

    try:
        # SQL 查詢：按 SPECNAME 和 WORKCENTERNAME 統計
        sql = """
            SELECT
                SPECNAME,
                WORKCENTERNAME,
                COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2
            FROM DW_MES_WIP
            WHERE TXNDATE >= TRUNC(SYSDATE) - :days
              AND STATUS NOT IN (8, 128)  -- 排除已完成/取消
              AND SPECNAME IS NOT NULL
              AND WORKCENTERNAME IS NOT NULL
            GROUP BY SPECNAME, WORKCENTERNAME
            ORDER BY SPECNAME, WORKCENTERNAME
        """

        df = pd.read_sql(sql, connection, params={'days': days})
        connection.close()
        return df

    except Exception as e:
        if connection:
            connection.close()
        print(f"查詢失敗: {e}")
        return None

def query_wip_by_product_line(days=7):
    """
    查詢不同產品線的 WIP 數量分布

    Args:
        days: 查詢最近幾天的數據（默認 7 天）

    Returns:
        DataFrame: 包含產品線統計數據
    """
    connection = get_db_connection()
    if not connection:
        return None

    try:
        # SQL 查詢：按產品線統計
        sql = """
            SELECT
                PRODUCTLINENAME_LEF,
                SPECNAME,
                WORKCENTERNAME,
                COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2
            FROM DW_MES_WIP
            WHERE TXNDATE >= TRUNC(SYSDATE) - :days
              AND STATUS NOT IN (8, 128)  -- 排除已完成/取消
              AND PRODUCTLINENAME_LEF IS NOT NULL
            GROUP BY PRODUCTLINENAME_LEF, SPECNAME, WORKCENTERNAME
            ORDER BY PRODUCTLINENAME_LEF, SPECNAME, WORKCENTERNAME
        """

        df = pd.read_sql(sql, connection, params={'days': days})
        connection.close()
        return df

    except Exception as e:
        if connection:
            connection.close()
        print(f"查詢失敗: {e}")
        return None

def query_wip_summary(days=7):
    """
    查詢 WIP 總覽統計

    Returns:
        dict: 包含總體統計數據
    """
    connection = get_db_connection()
    if not connection:
        return None

    try:
        # SQL 查詢：總覽統計
        sql = """
            SELECT
                COUNT(DISTINCT CONTAINERNAME) as TOTAL_LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2,
                COUNT(DISTINCT SPECNAME) as SPEC_COUNT,
                COUNT(DISTINCT WORKCENTERNAME) as WORKCENTER_COUNT,
                COUNT(DISTINCT PRODUCTLINENAME_LEF) as PRODUCT_LINE_COUNT
            FROM DW_MES_WIP
            WHERE TXNDATE >= TRUNC(SYSDATE) - :days
              AND STATUS NOT IN (8, 128)
        """

        cursor = connection.cursor()
        cursor.execute(sql, {'days': days})
        result = cursor.fetchone()

        cursor.close()
        connection.close()

        if result:
            return {
                'total_lot_count': result[0] or 0,
                'total_qty': result[1] or 0,
                'total_qty2': result[2] or 0,
                'spec_count': result[3] or 0,
                'workcenter_count': result[4] or 0,
                'product_line_count': result[5] or 0
            }
        return None

    except Exception as e:
        if connection:
            connection.close()
        print(f"查詢失敗: {e}")
        return None

@app.route('/')
def index():
    """首頁"""
    return render_template('wip_report.html')

@app.route('/api/wip/summary')
def api_wip_summary():
    """API: WIP 總覽統計"""
    days = request.args.get('days', 7, type=int)

    summary = query_wip_summary(days)
    if summary:
        return jsonify({'success': True, 'data': summary})
    else:
        return jsonify({'success': False, 'error': '查詢失敗'}), 500

@app.route('/api/wip/by_spec_workcenter')
def api_wip_by_spec_workcenter():
    """API: 按 SPEC 和 WORKCENTER 統計"""
    days = request.args.get('days', 7, type=int)

    df = query_wip_by_spec_workcenter(days)
    if df is not None:
        # 轉換為 JSON
        data = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': data, 'count': len(data)})
    else:
        return jsonify({'success': False, 'error': '查詢失敗'}), 500

@app.route('/api/wip/by_product_line')
def api_wip_by_product_line():
    """API: 按產品線統計"""
    days = request.args.get('days', 7, type=int)

    df = query_wip_by_product_line(days)
    if df is not None:
        # 轉換為 JSON
        data = df.to_dict(orient='records')

        # 計算產品線匯總
        if not df.empty:
            product_line_summary = df.groupby('PRODUCTLINENAME_LEF').agg({
                'LOT_COUNT': 'sum',
                'TOTAL_QTY': 'sum',
                'TOTAL_QTY2': 'sum'
            }).reset_index()

            summary = product_line_summary.to_dict(orient='records')
        else:
            summary = []

        return jsonify({
            'success': True,
            'data': data,
            'summary': summary,
            'count': len(data)
        })
    else:
        return jsonify({'success': False, 'error': '查詢失敗'}), 500


def query_wip_by_status(days=7):
    """查詢各狀態的 WIP 分布"""
    connection = get_db_connection()
    if not connection:
        return None

    try:
        sql = """
            SELECT
                CASE STATUS
                    WHEN 1 THEN 'Queue'
                    WHEN 2 THEN 'Run'
                    WHEN 4 THEN 'Hold'
                    WHEN 8 THEN 'Complete'
                    WHEN 128 THEN 'Scrapped'
                    ELSE 'Other(' || STATUS || ')'
                END as STATUS_NAME,
                STATUS,
                COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT,
                SUM(QTY) as TOTAL_QTY,
                SUM(QTY2) as TOTAL_QTY2
            FROM DW_MES_WIP
            WHERE TXNDATE >= TRUNC(SYSDATE) - :days
            GROUP BY STATUS
            ORDER BY LOT_COUNT DESC
        """
        df = pd.read_sql(sql, connection, params={'days': days})
        connection.close()
        return df
    except Exception as e:
        if connection:
            connection.close()
        print(f"查詢失敗: {e}")
        return None


def query_wip_by_mfgorder(days=7, limit=20):
    """查詢各工單 (GA) 的 WIP 分布"""
    connection = get_db_connection()
    if not connection:
        return None

    try:
        sql = """
            SELECT * FROM (
                SELECT
                    MFGORDERNAME,
                    COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT,
                    SUM(QTY) as TOTAL_QTY,
                    SUM(QTY2) as TOTAL_QTY2
                FROM DW_MES_WIP
                WHERE TXNDATE >= TRUNC(SYSDATE) - :days
                  AND STATUS NOT IN (8, 128)
                  AND MFGORDERNAME IS NOT NULL
                GROUP BY MFGORDERNAME
                ORDER BY LOT_COUNT DESC
            ) WHERE ROWNUM <= :limit
        """
        df = pd.read_sql(sql, connection, params={'days': days, 'limit': limit})
        connection.close()
        return df
    except Exception as e:
        if connection:
            connection.close()
        print(f"查詢失敗: {e}")
        return None


def query_wip_heatmap(days=7):
    """查詢 SPEC × WORKCENTER 熱力圖數據"""
    connection = get_db_connection()
    if not connection:
        return None

    try:
        sql = """
            SELECT
                SPECNAME,
                WORKCENTERNAME,
                SUM(QTY) as TOTAL_QTY
            FROM DW_MES_WIP
            WHERE TXNDATE >= TRUNC(SYSDATE) - :days
              AND STATUS NOT IN (8, 128)
              AND SPECNAME IS NOT NULL
              AND WORKCENTERNAME IS NOT NULL
            GROUP BY SPECNAME, WORKCENTERNAME
            ORDER BY SPECNAME, WORKCENTERNAME
        """
        df = pd.read_sql(sql, connection, params={'days': days})
        connection.close()
        return df
    except Exception as e:
        if connection:
            connection.close()
        print(f"查詢失敗: {e}")
        return None


@app.route('/api/wip/by_status')
def api_wip_by_status():
    """API: 按狀態統計"""
    days = request.args.get('days', 7, type=int)

    df = query_wip_by_status(days)
    if df is not None:
        data = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': data})
    else:
        return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/wip/by_mfgorder')
def api_wip_by_mfgorder():
    """API: 按工單統計 (Top 20)"""
    days = request.args.get('days', 7, type=int)
    limit = request.args.get('limit', 20, type=int)

    df = query_wip_by_mfgorder(days, limit)
    if df is not None:
        data = df.to_dict(orient='records')
        return jsonify({'success': True, 'data': data})
    else:
        return jsonify({'success': False, 'error': '查詢失敗'}), 500


@app.route('/api/wip/heatmap')
def api_wip_heatmap():
    """API: SPEC × WORKCENTER 熱力圖數據"""
    days = request.args.get('days', 7, type=int)

    df = query_wip_heatmap(days)
    if df is not None:
        if df.empty:
            return jsonify({'success': True, 'specs': [], 'workcenters': [], 'data': []})

        specs = sorted(df['SPECNAME'].unique().tolist())
        workcenters = sorted(df['WORKCENTERNAME'].unique().tolist())

        # 轉換為熱力圖格式 [workcenter_index, spec_index, value]
        heatmap_data = []
        for _, row in df.iterrows():
            spec_idx = specs.index(row['SPECNAME'])
            wc_idx = workcenters.index(row['WORKCENTERNAME'])
            heatmap_data.append([wc_idx, spec_idx, int(row['TOTAL_QTY'] or 0)])

        return jsonify({
            'success': True,
            'specs': specs,
            'workcenters': workcenters,
            'data': heatmap_data
        })
    else:
        return jsonify({'success': False, 'error': '查詢失敗'}), 500

if __name__ == '__main__':
    # 測試數據庫連接
    print("正在測試數據庫連接...")
    conn = get_db_connection()
    if conn:
        print("✓ 數據庫連接成功！")
        conn.close()

        # 測試查詢
        print("\n正在測試查詢...")
        summary = query_wip_summary()
        if summary:
            print(f"✓ WIP 總覽查詢成功！")
            print(f"  - 總 LOT 數: {summary['total_lot_count']}")
            print(f"  - 總數量: {summary['total_qty']}")
            print(f"  - 總片數: {summary['total_qty2']}")

        print("\n啟動 Web 服務器...")
        print("請訪問: http://localhost:5001")
        print("按 Ctrl+C 停止服務器\n")

        app.run(debug=True, host='0.0.0.0', port=5001)
    else:
        print("✗ 數據庫連接失敗，請檢查配置")
