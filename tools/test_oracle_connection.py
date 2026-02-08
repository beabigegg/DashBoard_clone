"""
Oracle Database Connection Test Script
测试连接到 DWDB 数据库并验证 MES 表访问权限
"""

import sys
import io
import os
import oracledb
from datetime import datetime
from pathlib import Path

# 设置 UTF-8 编码输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / '.env'
    load_dotenv(env_path)
except ImportError:
    pass

# 数据库连接信息 (从环境变量读取，必须在 .env 中设置)
DB_HOST = os.getenv('DB_HOST', '')
DB_PORT = os.getenv('DB_PORT', '1521')
DB_SERVICE = os.getenv('DB_SERVICE', '')
DB_USER = os.getenv('DB_USER', '')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')

DB_CONFIG = {
    'user': DB_USER,
    'password': DB_PASSWORD,
    'dsn': f'(DESCRIPTION=(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)(HOST={DB_HOST})(PORT={DB_PORT})))(CONNECT_DATA=(SERVICE_NAME={DB_SERVICE})))'
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


def test_connection():
    """测试数据库连接"""
    print("=" * 60)
    print("Oracle Database Connection Test")
    print("=" * 60)
    print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Host: {DB_HOST}:{DB_PORT}")
    print(f"Service Name: {DB_SERVICE}")
    print(f"User: {DB_USER}")
    print("=" * 60)

    try:
        # 尝试连接数据库
        print("\n[1/3] Attempting to connect to database...")
        connection = oracledb.connect(**DB_CONFIG)
        print("[OK] Connection successful!")

        # 获取数据库版本信息
        print("\n[2/3] Retrieving database version...")
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM v$version WHERE banner LIKE 'Oracle%'")
        version = cursor.fetchone()
        if version:
            print(f"[OK] Database Version: {version[0]}")

        # 测试每个表的访问权限
        print("\n[3/3] Testing access to MES tables...")
        print("-" * 60)

        accessible_tables = []
        inaccessible_tables = []

        for table_name in MES_TABLES:
            try:
                # 尝试查询表的行数
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"[OK] {table_name:<35} - {count:,} rows")
                accessible_tables.append(table_name)
            except oracledb.DatabaseError as e:
                error_obj, = e.args
                print(f"[FAIL] {table_name:<35} - Error: {error_obj.message}")
                inaccessible_tables.append((table_name, error_obj.message))

        # 汇总结果
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        print(f"Total tables tested: {len(MES_TABLES)}")
        print(f"Accessible tables: {len(accessible_tables)}")
        print(f"Inaccessible tables: {len(inaccessible_tables)}")

        if inaccessible_tables:
            print("\nInaccessible Tables:")
            for table, error in inaccessible_tables:
                print(f"  - {table}: {error}")

        # 关闭连接
        cursor.close()
        connection.close()
        print("\n[OK] Connection closed successfully")

        return len(inaccessible_tables) == 0

    except oracledb.DatabaseError as e:
        error_obj, = e.args
        print(f"\n[FAIL] Database Error: {error_obj.message}")
        print(f"   Error Code: {error_obj.code}")
        return False

    except Exception as e:
        print(f"\n[FAIL] Unexpected Error: {str(e)}")
        return False


def main():
    """主函数"""
    try:
        success = test_connection()

        print("\n" + "=" * 60)
        if success:
            print("[SUCCESS] All tests passed successfully!")
        else:
            print("[WARNING] Some tests failed. Please check the output above.")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n\nFatal error: {str(e)}")


if __name__ == "__main__":
    main()
