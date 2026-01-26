"""
生成 MES 数据库参考文档
用于报表开发参考
"""

import json
from pathlib import Path
from datetime import datetime

# 读取表结构信息
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT_DIR / 'data' / 'table_schema_info.json'
with open(DATA_FILE, 'r', encoding='utf-8') as f:
    table_info = json.load(f)

# 表用途描述（根据表名推断）
TABLE_DESCRIPTIONS = {
    'DW_MES_CONTAINER': '容器/批次主檔 - 目前在製容器狀態、數量與流程資訊',
    'DW_MES_HOLDRELEASEHISTORY': 'Hold/Release 歷史表 - 批次停工與解除紀錄',
    'DW_MES_JOB': '設備維修工單表 - 維修工單的當前狀態與流程',
    'DW_MES_LOTREJECTHISTORY': '批次不良/報廢歷史表 - 不良原因與數量',
    'DW_MES_LOTWIPDATAHISTORY': '在製數據採集歷史表 - 製程量測/參數紀錄',
    'DW_MES_LOTWIPHISTORY': '在製流轉歷史表 - 批次進出站與流程軌跡',
    'DW_MES_MAINTENANCE': '設備保養/維護紀錄表 - 保養計畫與點檢數據',
    'DW_MES_PARTREQUESTORDER': '維修用料請求表 - 維修/設備零件請領',
    'DW_MES_PJ_COMBINEDASSYLOTS': '併批紀錄表 - 合批/合併批次關聯與數量資訊',
    'DW_MES_RESOURCESTATUS': '設備狀態變更歷史表 - 狀態切換與原因',
    'DW_MES_RESOURCESTATUS_SHIFT': '設備狀態班次彙總表 - 班次級狀態/工時',
    'DW_MES_WIP': '在製品現況表（含歷史累積）- 當前 WIP 狀態/數量',
    'DW_MES_HM_LOTMOVEOUT': '批次出站事件歷史表 - 出站/移出交易',
    'DW_MES_JOBTXNHISTORY': '維修工單交易歷史表 - 工單狀態變更紀錄',
    'DW_MES_LOTMATERIALSHISTORY': '批次物料消耗歷史表 - 用料與批次關聯',
    'DW_MES_RESOURCE': '資源表 - 設備/載具等資源基本資料（OBJECTCATEGORY=ASSEMBLY 時，RESOURCENAME 為設備編號）'
}

# 常见字段说明
COMMON_FIELD_NOTES = {
    'ID': '唯一标识符',
    'NAME': '名称',
    'STATUS': '状态',
    'TIMESTAMP': '时间戳',
    'CREATEDATE': '创建日期',
    'UPDATEDATE': '更新日期',
    'LOTID': '批次ID',
    'CONTAINERID': '容器ID',
    'RESOURCEID': '资源ID',
    'EQUIPMENTID': '设备ID',
    'OPERATIONID': '工序ID',
    'JOBID': '工单ID',
    'PRODUCTID': '产品ID',
    'CUSTOMERID': '客户ID',
    'QTY': '数量',
    'QUANTITY': '数量'
}


def generate_markdown():
    """生成 Markdown 文档"""

    md = []

    # 标题和简介
    md.append("# MES 数据库报表开发参考文档\n")
    md.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    md.append("---\n")

    # 目录
    md.append("## 目录\n")
    md.append("1. [数据库连接信息](#数据库连接信息)")
    md.append("2. [数据库概览](#数据库概览)")
    md.append("3. [表结构详细说明](#表结构详细说明)")
    md.append("4. [报表开发注意事项](#报表开发注意事项)")
    md.append("5. [常用查询示例](#常用查询示例)\n")
    md.append("---\n")

    # 1. 数据库连接信息
    md.append("## 数据库连接信息\n")
    md.append("### 连接参数\n")
    md.append("| 参数 | 值 |")
    md.append("|------|------|")
    md.append("| 数据库类型 | Oracle Database 19c Enterprise Edition |")
    md.append("| 主机地址 | 10.1.1.58 |")
    md.append("| 端口 | 1521 |")
    md.append("| 服务名 | DWDB |")
    md.append("| 用户名 | MBU1_R |")
    md.append("| 密码 | Pj2481mbu1 |\n")

    md.append("### Python 连接示例\n")
    md.append("```python")
    md.append("import oracledb")
    md.append("")
    md.append("# 连接配置")
    md.append("DB_CONFIG = {")
    md.append("    'user': 'MBU1_R',")
    md.append("    'password': 'Pj2481mbu1',")
    md.append("    'dsn': '(DESCRIPTION=(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)(HOST=10.1.1.58)(PORT=1521)))(CONNECT_DATA=(SERVICE_NAME=DWDB)))'")
    md.append("}")
    md.append("")
    md.append("# 建立连接")
    md.append("connection = oracledb.connect(**DB_CONFIG)")
    md.append("cursor = connection.cursor()")
    md.append("")
    md.append("# 执行查询")
    md.append("cursor.execute('SELECT * FROM DW_MES_WIP WHERE ROWNUM <= 10')")
    md.append("results = cursor.fetchall()")
    md.append("")
    md.append("# 关闭连接")
    md.append("cursor.close()")
    md.append("connection.close()")
    md.append("```\n")

    md.append("### JDBC 连接字符串\n")
    md.append("```")
    md.append("jdbc:oracle:thin:@10.1.1.58:1521:DWDB")
    md.append("```\n")

    # 2. 数据库概览
    md.append("---\n")
    md.append("## 数据库概览\n")
    md.append("### 表统计信息\n")
    md.append("| # | 表名 | 用途 | 数据量 |")
    md.append("|---|------|------|--------|")

    for idx, (table_name, info) in enumerate(sorted(table_info.items()), 1):
        if 'error' not in info:
            row_count = f"{info['row_count']:,}"
            description = TABLE_DESCRIPTIONS.get(table_name, '待补充')
            md.append(f"| {idx} | `{table_name}` | {description} | {row_count} |")

    md.append("")

    # 计算总数据量
    total_rows = sum(info['row_count'] for info in table_info.values() if 'error' not in info)
    md.append(f"**总数据量**: {total_rows:,} 行\n")

    # 3. 表结构详细说明
    md.append("---\n")
    md.append("## 表结构详细说明\n")

    for table_name in sorted(table_info.keys()):
        info = table_info[table_name]

        if 'error' in info:
            continue

        md.append(f"### {table_name}\n")

        # 表说明
        md.append(f"**用途**: {TABLE_DESCRIPTIONS.get(table_name, '待补充')}\n")
        md.append(f"**数据量**: {info['row_count']:,} 行\n")

        if info.get('table_comment'):
            md.append(f"**表注释**: {info['table_comment']}\n")

        # 字段列表
        md.append("#### 字段列表\n")
        md.append("| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |")
        md.append("|---|--------|----------|------|------|------|")

        schema = info.get('schema', [])
        for col in schema:
            col_num = col['column_id']
            col_name = col['column_name']

            # 构建数据类型显示
            if col['data_type'] in ['VARCHAR2', 'CHAR']:
                data_type = f"{col['data_type']}({col['data_length']})"
            elif col['data_type'] == 'NUMBER' and col['data_precision']:
                if col['data_scale']:
                    data_type = f"NUMBER({col['data_precision']},{col['data_scale']})"
                else:
                    data_type = f"NUMBER({col['data_precision']})"
            else:
                data_type = col['data_type']

            nullable = "是" if col['nullable'] == 'Y' else "否"

            # 获取字段说明
            column_comments = info.get('column_comments', {})
            comment = column_comments.get(col_name, '')

            # 如果没有注释，尝试从常见字段说明中获取
            if not comment:
                for key, value in COMMON_FIELD_NOTES.items():
                    if key in col_name:
                        comment = value
                        break

            md.append(f"| {col_num} | `{col_name}` | {data_type} | {col.get('data_length', '-')} | {nullable} | {comment} |")

        md.append("")

        # 索引信息
        indexes = info.get('indexes', [])
        if indexes:
            md.append("#### 索引\n")
            md.append("| 索引名 | 类型 | 字段 |")
            md.append("|--------|------|------|")
            for idx_info in indexes:
                idx_type = "唯一索引" if idx_info[1] == 'UNIQUE' else "普通索引"
                md.append(f"| `{idx_info[0]}` | {idx_type} | {idx_info[2]} |")
            md.append("")

        md.append("---\n")

    # 4. 报表开发注意事项
    md.append("## 报表开发注意事项\n")
    md.append("### 性能优化建议\n")
    md.append("1. **大数据量表查询优化**")
    md.append("   - 以下表数据量较大，查询时务必添加时间范围限制：")

    large_tables = [(name, info['row_count']) for name, info in table_info.items()
                    if 'error' not in info and info['row_count'] > 10000000]
    large_tables.sort(key=lambda x: x[1], reverse=True)

    for table_name, count in large_tables:
        md.append(f"     - `{table_name}`: {count:,} 行")

    md.append("")
    md.append("2. **索引使用**")
    md.append("   - 查询时尽量使用已建立索引的字段作为查询条件")
    md.append("   - 避免在索引字段上使用函数，会导致索引失效")
    md.append("")
    md.append("3. **连接池配置**")
    md.append("   - 建议使用连接池管理数据库连接")
    md.append("   - 推荐连接池大小：5-10 个连接")
    md.append("")
    md.append("4. **查询超时设置**")
    md.append("   - 建议设置查询超时时间为 30-60 秒")
    md.append("   - 避免长时间运行的查询影响系统性能")
    md.append("")

    md.append("### 数据时效性\n")
    md.append("- **实时数据表**: `DW_MES_WIP`（含歷史累積）, `DW_MES_RESOURCESTATUS`")
    md.append("- **历史数据表**: 带有 `HISTORY` 后缀的表")
    md.append("- **主数据表**: `DW_MES_RESOURCE`, `DW_MES_CONTAINER`")
    md.append("")

    md.append("### 常用时间字段\n")
    md.append("大多数历史表包含以下时间相关字段：")
    md.append("- `CREATEDATE` / `CREATETIMESTAMP`: 记录创建时间")
    md.append("- `UPDATEDATE` / `UPDATETIMESTAMP`: 记录更新时间")
    md.append("- `TRANSACTIONDATE`: 交易发生时间")
    md.append("")

    md.append("### 数据权限\n")
    md.append("- 当前账号 `MBU1_R` 为只读账号")
    md.append("- 仅可执行 SELECT 查询")
    md.append("- 无法进行 INSERT, UPDATE, DELETE 操作")
    md.append("")

    # 5. 常用查询示例
    md.append("---\n")
    md.append("## 常用查询示例\n")

    md.append("### 1. 查询当前在制品数量\n")
    md.append("```sql")
    md.append("SELECT COUNT(*) as WIP_COUNT")
    md.append("FROM DW_MES_WIP")
    md.append("WHERE CURRENTSTATUSID IS NOT NULL;")
    md.append("```\n")

    md.append("### 2. 查询设备状态统计\n")
    md.append("```sql")
    md.append("SELECT")
    md.append("    CURRENTSTATUSID,")
    md.append("    COUNT(*) as COUNT")
    md.append("FROM DW_MES_RESOURCESTATUS")
    md.append("GROUP BY CURRENTSTATUSID")
    md.append("ORDER BY COUNT DESC;")
    md.append("```\n")

    md.append("### 3. 查询最近 7 天的批次历史\n")
    md.append("```sql")
    md.append("SELECT *")
    md.append("FROM DW_MES_LOTWIPHISTORY")
    md.append("WHERE CREATEDATE >= SYSDATE - 7")
    md.append("ORDER BY CREATEDATE DESC;")
    md.append("```\n")

    md.append("### 4. 查询工单完成情况\n")
    md.append("```sql")
    md.append("SELECT")
    md.append("    JOBID,")
    md.append("    JOBSTATUS,")
    md.append("    COUNT(*) as COUNT")
    md.append("FROM DW_MES_JOB")
    md.append("GROUP BY JOBID, JOBSTATUS")
    md.append("ORDER BY JOBID;")
    md.append("```\n")

    md.append("### 5. 按日期统计生产数量\n")
    md.append("```sql")
    md.append("SELECT")
    md.append("    TRUNC(CREATEDATE) as PRODUCTION_DATE,")
    md.append("    COUNT(*) as LOT_COUNT")
    md.append("FROM DW_MES_HM_LOTMOVEOUT")
    md.append("WHERE CREATEDATE >= SYSDATE - 30")
    md.append("GROUP BY TRUNC(CREATEDATE)")
    md.append("ORDER BY PRODUCTION_DATE DESC;")
    md.append("```\n")

    md.append("### 6. 联表查询示例（批次与容器）\n")
    md.append("```sql")
    md.append("SELECT")
    md.append("    w.LOTID,")
    md.append("    w.CONTAINERNAME,")
    md.append("    c.CURRENTSTATUSID,")
    md.append("    c.CUSTOMERID")
    md.append("FROM DW_MES_WIP w")
    md.append("LEFT JOIN DW_MES_CONTAINER c ON w.CONTAINERID = c.CONTAINERID")
    md.append("WHERE w.CREATEDATE >= SYSDATE - 1")
    md.append("ORDER BY w.CREATEDATE DESC;")
    md.append("```\n")

    md.append("---\n")
    md.append("## 附录\n")
    md.append("### 文档更新记录\n")
    md.append(f"- {datetime.now().strftime('%Y-%m-%d')}: 初始版本创建")
    md.append("")
    md.append("### 联系方式\n")
    md.append("如有疑问或需要补充信息，请联系数据库管理员。\n")

    return '\n'.join(md)


if __name__ == "__main__":
    print("Generating documentation...")
    markdown_content = generate_markdown()

    output_file = ROOT_DIR / 'docs' / 'MES_Database_Reference.md'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

    print(f"[OK] Documentation generated: {output_file}")




