"""
查询 MES 表结构信息脚本
用于生成报表开发参考文档
"""

import sys
import io
import oracledb
import json
from pathlib import Path

# 设置 UTF-8 编码输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 数据库连接信息
DB_CONFIG = {
    'user': 'MBU1_R',
    'password': 'Pj2481mbu1',
    'dsn': '(DESCRIPTION=(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)(HOST=10.1.1.58)(PORT=1521)))(CONNECT_DATA=(SERVICE_NAME=DWDB)))'
}

# MES 表列表
MES_TABLES = [
    'DW_MES_CONTAINER',
    'DW_MES_HOLDRELEASEHISTORY',
    'DW_MES_JOB',
    'DW_MES_LOTREJECTHISTORY',
    'DW_MES_LOTWIPDATAHISTORY',
    'DW_MES_LOTWIPHISTORY',
    'DW_MES_MAINTENANCE',
    'DW_MES_PARTREQUESTORDER',
    'DW_MES_PJ_COMBINEDASSYLOTS',
    'DW_MES_RESOURCESTATUS',
    'DW_MES_RESOURCESTATUS_SHIFT',
    'DW_MES_WIP',
    'DW_MES_HM_LOTMOVEOUT',
    'DW_MES_JOBTXNHISTORY',
    'DW_MES_LOTMATERIALSHISTORY',
    'DW_MES_RESOURCE'
]


def get_table_schema(cursor, table_name):
    """获取表的结构信息"""
    query = """
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            DATA_LENGTH,
            DATA_PRECISION,
            DATA_SCALE,
            NULLABLE,
            DATA_DEFAULT,
            COLUMN_ID
        FROM ALL_TAB_COLUMNS
        WHERE TABLE_NAME = :table_name
        ORDER BY COLUMN_ID
    """
    cursor.execute(query, table_name=table_name)
    columns = cursor.fetchall()

    schema = []
    for col in columns:
        col_info = {
            'column_name': col[0],
            'data_type': col[1],
            'data_length': col[2],
            'data_precision': col[3],
            'data_scale': col[4],
            'nullable': col[5],
            'default_value': col[6],
            'column_id': col[7]
        }
        schema.append(col_info)

    return schema


def get_table_comments(cursor, table_name):
    """获取表和列的注释"""
    # 获取表注释
    cursor.execute("""
        SELECT COMMENTS
        FROM ALL_TAB_COMMENTS
        WHERE TABLE_NAME = :table_name
    """, table_name=table_name)
    table_comment = cursor.fetchone()

    # 获取列注释
    cursor.execute("""
        SELECT COLUMN_NAME, COMMENTS
        FROM ALL_COL_COMMENTS
        WHERE TABLE_NAME = :table_name
        ORDER BY COLUMN_NAME
    """, table_name=table_name)
    column_comments = {row[0]: row[1] for row in cursor.fetchall()}

    return table_comment[0] if table_comment else None, column_comments


def get_table_indexes(cursor, table_name):
    """获取表的索引信息"""
    query = """
        SELECT
            i.INDEX_NAME,
            i.UNIQUENESS,
            LISTAGG(ic.COLUMN_NAME, ', ') WITHIN GROUP (ORDER BY ic.COLUMN_POSITION) as COLUMNS
        FROM ALL_INDEXES i
        JOIN ALL_IND_COLUMNS ic ON i.INDEX_NAME = ic.INDEX_NAME AND i.TABLE_NAME = ic.TABLE_NAME
        WHERE i.TABLE_NAME = :table_name
        GROUP BY i.INDEX_NAME, i.UNIQUENESS
        ORDER BY i.INDEX_NAME
    """
    cursor.execute(query, table_name=table_name)
    return cursor.fetchall()


def get_sample_data(cursor, table_name, limit=5):
    """获取表的示例数据"""
    try:
        cursor.execute(f"SELECT * FROM {table_name} WHERE ROWNUM <= {limit}")
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        return columns, rows
    except Exception as e:
        return None, str(e)


def main():
    """主函数"""
    print("Connecting to database...")
    connection = oracledb.connect(**DB_CONFIG)
    cursor = connection.cursor()

    all_table_info = {}

    print(f"\nQuerying schema information for {len(MES_TABLES)} tables...\n")

    for idx, table_name in enumerate(MES_TABLES, 1):
        print(f"[{idx}/{len(MES_TABLES)}] Processing {table_name}...")

        try:
            # 获取表结构
            schema = get_table_schema(cursor, table_name)

            # 获取注释
            table_comment, column_comments = get_table_comments(cursor, table_name)

            # 获取索引
            indexes = get_table_indexes(cursor, table_name)

            # 获取行数
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]

            # 获取示例数据
            sample_columns, sample_data = get_sample_data(cursor, table_name, limit=3)

            all_table_info[table_name] = {
                'table_comment': table_comment,
                'row_count': row_count,
                'schema': schema,
                'column_comments': column_comments,
                'indexes': indexes,
                'sample_columns': sample_columns,
                'sample_data': sample_data
            }

        except Exception as e:
            print(f"   Error: {str(e)}")
            all_table_info[table_name] = {'error': str(e)}

    # 保存到 JSON 文件
    output_file = Path(__file__).resolve().parent.parent / 'data' / 'table_schema_info.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_table_info, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n[OK] Schema information saved to {output_file}")

    cursor.close()
    connection.close()
    print("[OK] Connection closed")


if __name__ == "__main__":
    main()

