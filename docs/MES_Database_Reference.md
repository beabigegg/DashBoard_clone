# MES 数据库报表开发参考文档

**生成时间**: 2026-03-18 08:07:24

---

## 目录

1. [数据库连接信息](#数据库连接信息)
2. [数据库概览](#数据库概览)
3. [表结构详细说明](#表结构详细说明)
4. [报表开发注意事项](#报表开发注意事项)
5. [常用查询示例](#常用查询示例)

---

## 数据库连接信息

### 连接参数

| 参数 | 值 |
|------|------|
| 数据库类型 | Oracle Database 19c Enterprise Edition |
| 主机地址 | 請參考 .env 檔案 (DB_HOST) |
| 端口 | 請參考 .env 檔案 (DB_PORT) |
| 服务名 | 請參考 .env 檔案 (DB_SERVICE) |
| 用户名 | 請參考 .env 檔案 (DB_USER) |
| 密码 | 請參考 .env 檔案 (DB_PASSWORD) |

### Python 连接示例

```python
import os
import oracledb
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 连接配置 (從環境變數讀取)
DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'dsn': f"(DESCRIPTION=(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)(HOST={os.getenv('DB_HOST')})(PORT={os.getenv('DB_PORT')})))(CONNECT_DATA=(SERVICE_NAME={os.getenv('DB_SERVICE')})))"
}

# 建立连接
connection = oracledb.connect(**DB_CONFIG)
cursor = connection.cursor()

# 执行查询
cursor.execute('SELECT * FROM DW_MES_WIP WHERE ROWNUM <= 10')
results = cursor.fetchall()

# 关闭连接
cursor.close()
connection.close()
```

### JDBC 连接字符串

```
jdbc:oracle:thin:@${DB_HOST}:${DB_PORT}:${DB_SERVICE}
```

---

## 数据库概览

### 表统计信息

| # | 表名 | 用途 | 数据量 |
|---|------|------|--------|
| 1 | `DW_MES_CONTAINER` | 容器/批次主檔 - 目前在製容器狀態、數量與流程資訊 | 5,313,094 |
| 2 | `DW_MES_EQUIPMENTSTATUS_WIP_V` | 設備狀態與 WIP 關聯視圖 - 即時設備狀態與工單資訊 | 2,784 |
| 3 | `DW_MES_HM_LOTMOVEOUT` | 批次出站事件歷史表 - 出站/移出交易 | 49,429,401 |
| 4 | `DW_MES_HOLDRELEASEHISTORY` | Hold/Release 歷史表 - 批次停工與解除紀錄 | 312,949 |
| 5 | `DW_MES_JOB` | 設備維修工單表 - 維修工單的當前狀態與流程 | 1,273,902 |
| 6 | `DW_MES_JOBTXNHISTORY` | 維修工單交易歷史表 - 工單狀態變更紀錄 | 9,743,810 |
| 7 | `DW_MES_LOTMATERIALSHISTORY` | 批次物料消耗歷史表 - 用料與批次關聯 | 18,136,445 |
| 8 | `DW_MES_LOTREJECTHISTORY` | 批次不良/報廢歷史表 - 不良原因與數量 | 16,103,258 |
| 9 | `DW_MES_LOTWIPDATAHISTORY` | 在製數據採集歷史表 - 製程量測/參數紀錄 | 80,316,112 |
| 10 | `DW_MES_LOTWIPHISTORY` | 在製流轉歷史表 - 批次進出站與流程軌跡 | 54,519,619 |
| 11 | `DW_MES_LOT_V` | MES 即時 WIP 視圖 - 批次現況、工站、設備與 Hold 資訊 | 9,923 |
| 12 | `DW_MES_MAINTENANCE` | 設備保養/維護紀錄表 - 保養計畫與點檢數據 | 55,101,182 |
| 13 | `DW_MES_PARTREQUESTORDER` | 維修用料請求表 - 維修/設備零件請領 | 61,396 |
| 14 | `DW_MES_PJ_COMBINEDASSYLOTS` | 併批紀錄表 - 合批/合併批次關聯與數量資訊 | 1,994,711 |
| 15 | `DW_MES_RESOURCE` | 資源表 - 設備/載具等資源基本資料（OBJECTCATEGORY=ASSEMBLY 時，RESOURCENAME 為設備編號） | 91,673 |
| 16 | `DW_MES_RESOURCESTATUS` | 設備狀態變更歷史表 - 狀態切換與原因 | 67,681,971 |
| 17 | `DW_MES_RESOURCESTATUS_SHIFT` | 設備狀態班次彙總表 - 班次級狀態/工時 | 76,947,961 |
| 18 | `DW_MES_SPEC_WORKCENTER_V` | 工站/工序對照視圖 - 用於工站分組與排序映射 | 230 |
| 19 | `DW_MES_WIP` | 在製品現況表（含歷史累積）- 當前 WIP 狀態/數量 | 84,271,674 |
| 20 | `ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE` | ERP 報廢原因排除清單 - 控制需排除的報廢原因代碼 | 39 |
| 21 | `ERP_WIP_MOVETXN` | ERP 工單移轉與報廢明細 - 工單層級移轉/報廢數量事件 | 10,748,846 |
| 22 | `ERP_WIP_MOVETXN_DETAIL` | ERP 工單站點損耗明細 - 站點/產品維度移轉與報廢明細 | 37,543,032 |

**总数据量**: 569,604,012 行

---

## 表结构详细说明

### DW_MES_CONTAINER

**用途**: 容器/批次主檔 - 目前在製容器狀態、數量與流程資訊

**数据量**: 5,313,094 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `CONTAINERCOMMENTS` | VARCHAR2(2000) | 2000 | 是 | None |
| 2 | `CONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 3 | `CONTAINERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 4 | `CURRENTHOLDCOUNT` | NUMBER(10) | 22 | 是 | None |
| 5 | `CURRENTSTATUSID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 6 | `CURRENTREWORKCOUNT` | NUMBER(10) | 22 | 是 | None |
| 7 | `CURRENTWIPLOTID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 8 | `CUSTOMERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 9 | `DOCUMENTSETID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 10 | `EQUIPMENTCOUNT` | NUMBER(10) | 22 | 是 | None |
| 11 | `EQUIPMENTLOADINGCOUNT` | NUMBER(10) | 22 | 是 | None |
| 12 | `EXPIRATIONDATE` | DATE | 7 | 是 | None |
| 13 | `FACTORYSTARTDATE` | DATE | 7 | 是 | None |
| 14 | `FACTORYSTARTQTY` | NUMBER(10) | 22 | 是 | 数量 |
| 15 | `FIRSTNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 16 | `FUTURECOMBINECOUNT` | NUMBER(10) | 22 | 是 | None |
| 17 | `FUTURECOMBINEPARENTLOTID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 18 | `FUTURECOMBINESPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 19 | `FUTUREHOLDCOUNT` | NUMBER(10) | 22 | 是 | None |
| 20 | `HOLDLOCATIONDURATION` | NUMBER | 22 | 是 | None |
| 21 | `HOLDLOCATIONID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 22 | `HOLDLOCATIONSTARTTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 23 | `HOLDREASONID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 24 | `LASTACTIVITYDATE` | DATE | 7 | 是 | None |
| 25 | `LASTCOMPLETIONDATE` | DATE | 7 | 是 | None |
| 26 | `LASTMOVEOUTTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 27 | `LASTMOVEOUTUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 28 | `LOTATTRIBUTESID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 29 | `MFGORDERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 30 | `MOVEINQTY` | NUMBER | 22 | 是 | 数量 |
| 31 | `MOVEINQTY2` | NUMBER | 22 | 是 | 数量 |
| 32 | `MOVEINTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 33 | `MOVEINUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 34 | `OBJECTTYPE` | VARCHAR2(40) | 40 | 是 | None |
| 35 | `ONHOLDDATE` | DATE | 7 | 是 | None |
| 36 | `ORIGINALCONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 37 | `ORIGINALQTY` | NUMBER | 22 | 是 | 数量 |
| 38 | `ORIGINALQTY2` | NUMBER | 22 | 是 | 数量 |
| 39 | `ORIGINALSTARTDATE` | DATE | 7 | 是 | None |
| 40 | `OWNERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 41 | `PARENTCONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 42 | `PLANNEDSTARTDATE` | DATE | 7 | 是 | None |
| 43 | `PRIORITYCODEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 44 | `PROCESSSPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 45 | `PRODUCTID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 46 | `QTY` | NUMBER | 22 | 是 | 数量 |
| 47 | `QTY2` | NUMBER | 22 | 是 | 数量 |
| 48 | `QTYSCHEDULED` | NUMBER | 22 | 是 | 数量 |
| 49 | `SCHEDULECOUNT` | NUMBER(10) | 22 | 是 | None |
| 50 | `SCHEDULEDATAID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 51 | `SPLITCOUNT` | NUMBER(10) | 22 | 是 | None |
| 52 | `SPLITFROMID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 53 | `STARTREASONID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 54 | `STATUS` | NUMBER(10) | 22 | 是 | 状态 |
| 55 | `UNITCOUNT` | NUMBER(10) | 22 | 是 | None |
| 56 | `UOM2ID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 57 | `UOMID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 58 | `PJ_ERPPRODUCTID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 59 | `LASTMOVEDATE` | DATE | 7 | 是 | CURRENTSTATUSID |
| 60 | `LOCATIONNAME` | VARCHAR2(40) | 40 | 是 | CURRENTSTATUSID |
| 61 | `WORKFLOWSTEPNAME` | VARCHAR2(40) | 40 | 是 | CURRENTSTATUSID |
| 62 | `SPECNAME` | VARCHAR2(40) | 40 | 是 | CURRENTSTATUSID |
| 63 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | CURRENTSTATUSID |
| 64 | `HOLDLOCATIONNAME` | VARCHAR2(40) | 40 | 是 | HOLDLOCATIONID |
| 65 | `HOLDREASONNAME` | VARCHAR2(40) | 40 | 是 | HOLDREASONID |
| 66 | `MFGORDERNAME` | VARCHAR2(40) | 40 | 是 | MFGORDERID |
| 67 | `PJ_BOP` | VARCHAR2(40) | 40 | 是 | MFGORDERID |
| 68 | `PJ_PRODUCEREGION` | VARCHAR2(40) | 40 | 是 | MFGORDERID |
| 69 | `PRODUCTBOMBASEID` | CHAR(16) | 16 | 是 | MFGORDERID |
| 70 | `OWNERNAME` | VARCHAR2(40) | 40 | 是 | OWNERID |
| 71 | `PRIORITYCODENAME` | VARCHAR2(40) | 40 | 是 | PRIORITYCODEID |
| 72 | `PJ_TYPE` | VARCHAR2(40) | 40 | 是 | PRODUCTID |
| 73 | `PJ_FUNCTION` | VARCHAR2(40) | 40 | 是 | PRODUCTID |
| 74 | `PRODUCTNAME` | VARCHAR2(40) | 40 | 是 | PRODUCTID |
| 75 | `PRODUCTLINENAME` | VARCHAR2(40) | 40 | 是 | PRODUCTID |
| 76 | `STARTREASONNAME` | VARCHAR2(40) | 40 | 是 | STARTREASONID |
| 77 | `PRODUCTDESC` | VARCHAR2(255) | 255 | 是 | PRODUCTID |
| 78 | `UTS` | DATE | 7 | 是 | None |
| 79 | `LEADFRAMENAME` | VARCHAR2(100) | 100 | 是 | 名称 |
| 80 | `LEADFRAMEDESC` | VARCHAR2(200) | 200 | 是 | None |
| 81 | `LEADFRAMEOPTION` | VARCHAR2(100) | 100 | 是 | None |
| 82 | `LAST_SYNC_DATE` | DATE | 7 | 是 | None |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_C_CONTAINERID` | 唯一索引 | CONTAINERID |
| `DW_C_CONTAINERNAME` | 唯一索引 | CONTAINERNAME |
| `DW_C_MFGORDERNAME` | 普通索引 | MFGORDERNAME |
| `DW_C_PRODUCTBOMBASEID` | 普通索引 | PRODUCTBOMBASEID |
| `DW_C_SCHEDULEDATAID` | 普通索引 | SCHEDULEDATAID |
| `DW_MES_CONTAINER_PRODUCTLINENAME` | 普通索引 | PRODUCTLINENAME |

---

### DW_MES_EQUIPMENTSTATUS_WIP_V

**用途**: 設備狀態與 WIP 關聯視圖 - 即時設備狀態與工單資訊

**数据量**: 2,784 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `RESOURCEID` | CHAR(16) | 16 | 否 | 唯一标识符 |
| 2 | `EQUIPMENTID` | VARCHAR2(40) | 40 | 是 | 唯一标识符 |
| 3 | `OBJECTCATEGORY` | VARCHAR2(40) | 40 | 是 | None |
| 4 | `EQUIPMENTASSETSSTATUS` | VARCHAR2(40) | 40 | 是 | 状态 |
| 5 | `EQUIPMENTASSETSSTATUSREASON` | VARCHAR2(40) | 40 | 是 | 状态 |
| 6 | `JOBORDER` | VARCHAR2(40) | 40 | 是 | None |
| 7 | `JOBMODEL` | VARCHAR2(40) | 40 | 是 | None |
| 8 | `JOBSTAGE` | VARCHAR2(40) | 40 | 是 | None |
| 9 | `JOBID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 10 | `JOBSTATUS` | VARCHAR2(40) | 40 | 是 | 状态 |
| 11 | `CREATEDATE` | DATE | 7 | 是 | 创建日期 |
| 12 | `CREATEUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 13 | `CREATEUSER` | VARCHAR2(255) | 255 | 是 | None |
| 14 | `TECHNICIANUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 15 | `TECHNICIANUSER` | VARCHAR2(255) | 255 | 是 | None |
| 16 | `SYMPTOMCODE` | VARCHAR2(40) | 40 | 是 | None |
| 17 | `CAUSECODE` | VARCHAR2(40) | 40 | 是 | None |
| 18 | `REPAIRCODE` | VARCHAR2(40) | 40 | 是 | None |
| 19 | `RUNCARDLOTID` | VARCHAR2(40) | 40 | 是 | 唯一标识符 |
| 20 | `Package` | VARCHAR2(40) | 40 | 是 | None |
| 21 | `PACKAGE_LF` | VARCHAR2(4000) | 4000 | 是 | None |
| 22 | `Function` | VARCHAR2(40) | 40 | 是 | None |
| 23 | `TYPE` | VARCHAR2(40) | 40 | 是 | None |
| 24 | `BOP` | VARCHAR2(40) | 40 | 是 | None |
| 25 | `WAFERLOTID` | VARCHAR2(40) | 40 | 是 | 唯一标识符 |
| 26 | `WAFERPN` | VARCHAR2(40) | 40 | 是 | None |
| 27 | `WAFERLOTID_PREFIX` | VARCHAR2(160) | 160 | 是 | 唯一标识符 |
| 28 | `SPEC` | VARCHAR2(40) | 40 | 是 | None |
| 29 | `LFOPTIONID` | VARCHAR2(4000) | 4000 | 是 | 唯一标识符 |
| 30 | `WIREDESCRIPTION` | VARCHAR2(4000) | 4000 | 是 | None |
| 31 | `WAFERMIL` | VARCHAR2(3062) | 3062 | 是 | None |
| 32 | `LOTTRACKINQTY_PCS` | NUMBER | 22 | 是 | 数量 |
| 33 | `LOTTRACKINTIME` | DATE | 7 | 是 | None |
| 34 | `LOTTRACKINEMPLOYEE` | VARCHAR2(255) | 255 | 是 | None |

---

### DW_MES_HM_LOTMOVEOUT

**用途**: 批次出站事件歷史表 - 出站/移出交易

**数据量**: 49,429,401 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `CALLBYCDONAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 2 | `CARRIERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 3 | `CARRIERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 4 | `CDONAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 5 | `CDOTXNSEQUENCE` | NUMBER(10) | 22 | 是 | None |
| 6 | `COMMENTS` | VARCHAR2(255) | 255 | 是 | None |
| 7 | `COMPUTERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 8 | `CONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 9 | `CONTAINERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 10 | `EMPLOYEEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 11 | `EMPLOYEENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 12 | `FACTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 13 | `FROMCONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 14 | `FROMCONTAINERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 15 | `FROMQTY` | NUMBER | 22 | 是 | 数量 |
| 16 | `FROMQTY2` | NUMBER | 22 | 是 | 数量 |
| 17 | `FROMSPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 18 | `FROMSPECNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 19 | `FROMWORKCENTER` | VARCHAR2(40) | 40 | 是 | None |
| 20 | `FROMSTATUS` | NUMBER(10) | 22 | 是 | 状态 |
| 21 | `FROMUOM2NAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 22 | `FROMUOMNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 23 | `FROMWORKFLOWNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 24 | `HISTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 25 | `HISTORYMAINLINEID` | CHAR(16) | 16 | 否 | 唯一标识符 |
| 26 | `HISTORYSUMMARYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 27 | `LASTLOTCARRIERSSETUPHISTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 28 | `LASTMOVEOUTTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 29 | `LASTMOVEOUTUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 30 | `MFGDATE` | DATE | 7 | 是 | None |
| 31 | `MOVEINQTY` | NUMBER | 22 | 是 | 数量 |
| 32 | `MOVEINQTY2` | NUMBER | 22 | 是 | 数量 |
| 33 | `MOVEINTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 34 | `MOVEINUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 35 | `OPERATIONID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 36 | `OWNERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 37 | `OWNERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 38 | `PARAMETRICDETAILID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 39 | `PROCESSSPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 40 | `PRODUCTID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 41 | `PRODUCTNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 42 | `QTY` | NUMBER | 22 | 是 | 数量 |
| 43 | `QTY2` | NUMBER | 22 | 是 | 数量 |
| 44 | `RESOURCEAVAILABILITY` | NUMBER(10) | 22 | 是 | None |
| 45 | `RESOURCEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 46 | `RESOURCENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 47 | `RESOURCEOBJECTCATEGORY` | VARCHAR2(40) | 40 | 是 | None |
| 48 | `RESOURCEOBJECTTYPE` | VARCHAR2(40) | 40 | 是 | None |
| 49 | `RESOURCESTATUSCODEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 50 | `RESOURCESTATUSREASONID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 51 | `SERVERNAME` | VARCHAR2(100) | 100 | 是 | 名称 |
| 52 | `SHIFTNAME` | VARCHAR2(30) | 30 | 是 | 名称 |
| 53 | `SPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 54 | `SPECNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 55 | `WORKCENTER` | VARCHAR2(40) | 40 | 是 | None |
| 56 | `STATUS` | NUMBER(10) | 22 | 是 | 状态 |
| 57 | `SYSTEMDATE` | DATE | 7 | 是 | None |
| 58 | `TXNDATE` | DATE | 7 | 是 | None |
| 59 | `TXNID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 60 | `TXNTYPE` | NUMBER(10) | 22 | 是 | None |
| 61 | `UOM2NAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 62 | `UOMNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 63 | `USERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 64 | `USERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 65 | `WIPTRACKINGGROUPKEYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 66 | `WORKFLOWNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 67 | `WORKFLOWSTEPID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 68 | `UPDATETIME` | DATE | 7 | 是 | None |
| 69 | `USERFULLNAME` | VARCHAR2(100) | 100 | 是 | 名称 |
| 70 | `EMPZONE` | VARCHAR2(100) | 100 | 是 | None |
| 71 | `WAFERPRODUCT` | VARCHAR2(40) | 40 | 是 | None |
| 72 | `CONSUMEFACTOR` | NUMBER(10) | 22 | 是 | None |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_HM_LMO_CALLBYCDONAME` | 普通索引 | CALLBYCDONAME |
| `DW_MES_HM_LMO_CDONAME` | 普通索引 | CDONAME |
| `DW_MES_HM_LMO_HISTORYID` | 普通索引 | HISTORYID |
| `DW_MES_HM_LMO_HISTORYID_TID_TDATE` | 普通索引 | HISTORYID, TXNID, TXNDATE |
| `DW_MES_HM_LMO_TXNDATE` | 普通索引 | TXNDATE |
| `DW_MES_HM_LMO__HID_TID_DATE_ID` | 普通索引 | HISTORYID, TXNID, TXNDATE, HISTORYMAINLINEID |
| `DW_MES_HM_LMO__HISTORYMAINLINEID` | 唯一索引 | HISTORYMAINLINEID |

---

### DW_MES_HOLDRELEASEHISTORY

**用途**: Hold/Release 歷史表 - 批次停工與解除紀錄

**数据量**: 312,949 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `RN` | VARCHAR2(16) | 16 | 是 | None |
| 2 | `CONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 3 | `HISTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 4 | `HISTORYMAINLINEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 5 | `FINISHEDRUNCARD` | VARCHAR2(255) | 255 | 是 | None |
| 6 | `PJ_WORKORDER` | VARCHAR2(40) | 40 | 是 | None |
| 7 | `WORKCENTERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 8 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 9 | `FROMSPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 10 | `FROMSPECNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 11 | `QTY` | NUMBER | 22 | 是 | 数量 |
| 12 | `QTY2` | NUMBER | 22 | 是 | 数量 |
| 13 | `PJ_CHIPREMARK1` | VARCHAR2(255) | 255 | 是 | None |
| 14 | `PJ_CHIPREMARK2` | VARCHAR2(255) | 255 | 是 | None |
| 15 | `PJ_CHIPREMARK3` | VARCHAR2(255) | 255 | 是 | None |
| 16 | `HOLDTXNDATE` | DATE | 7 | 是 | None |
| 17 | `RELEASETXNDATE` | DATE | 7 | 是 | None |
| 18 | `HOLDEMP` | VARCHAR2(40) | 40 | 是 | None |
| 19 | `HOLDEMPDEPTNAME` | VARCHAR2(100) | 100 | 是 | 名称 |
| 20 | `RELEASEEMP` | VARCHAR2(40) | 40 | 是 | None |
| 21 | `RELEASEEMPDEPTNAME` | VARCHAR2(100) | 100 | 是 | 名称 |
| 22 | `HOLDCOMMENTS` | VARCHAR2(255) | 255 | 是 | None |
| 23 | `RELEASECOMMENTS` | VARCHAR2(255) | 255 | 是 | None |
| 24 | `HOLDREASONID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 25 | `HOLDREASONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 26 | `RELEASEREASONID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 27 | `RELEASEREASONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 28 | `NCRID` | VARCHAR2(255) | 255 | 是 | 唯一标识符 |
| 29 | `LAST_UPDATED_DATE` | DATE | 7 | 是 | None |
| 30 | `HOLDUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 31 | `FUTUREHOLDCOMMENTS` | VARCHAR2(1000) | 1000 | 是 | None |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_HOLDRELEASEHISTORY_IDX1` | 普通索引 | HISTORYMAINLINEID |
| `DW_MES_HOLDRELEASEHISTORY_IDX2` | 普通索引 | CONTAINERID |

---

### DW_MES_JOB

**用途**: 設備維修工單表 - 維修工單的當前狀態與流程

**数据量**: 1,273,902 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `ACKNOWLEDGECOUNT` | NUMBER(10) | 22 | 是 | None |
| 2 | `ACTIVECLOCKONCOUNT` | NUMBER(10) | 22 | 是 | None |
| 3 | `ASSIGNCOUNT` | NUMBER(10) | 22 | 是 | None |
| 4 | `CANCELDATE` | DATE | 7 | 是 | None |
| 5 | `CANCELUSERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 6 | `CAUSECODENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 7 | `CLOCKONCOUNT` | NUMBER(10) | 22 | 是 | None |
| 8 | `COMPLETEDATE` | DATE | 7 | 是 | None |
| 9 | `COMPLETEUSERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 10 | `CREATEDATE` | DATE | 7 | 是 | 创建日期 |
| 11 | `CREATEUSERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 12 | `ESTIMATEDDURATION` | NUMBER | 22 | 是 | None |
| 13 | `EXPECTEDSTARTDATE` | DATE | 7 | 是 | None |
| 14 | `FIRSTCLOCKONDATE` | DATE | 7 | 是 | None |
| 15 | `ISSIMPLEMODE` | NUMBER(10) | 22 | 是 | None |
| 16 | `JOBID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 17 | `JOBMODELNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 18 | `JOBORDERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 19 | `JOBORDERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 20 | `JOBSTATUS` | VARCHAR2(40) | 40 | 是 | 状态 |
| 21 | `LASTCLOCKOFFDATE` | DATE | 7 | 是 | None |
| 22 | `REPAIRCODENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 23 | `RESOURCEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 24 | `STAGENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 25 | `STAGESEQUENCE` | NUMBER(10) | 22 | 是 | None |
| 26 | `SYMPTOMCODENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 27 | `PJ_CAUSECODE2NAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 28 | `PJ_REPAIRCODE2NAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 29 | `PJ_SYMPTOMCODE2NAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 30 | `CANCEL_EMPNAME` | VARCHAR2(40) | 40 | 是 | CANCELUSERID |
| 31 | `CANCEL_FULLNAME` | VARCHAR2(255) | 255 | 是 | CANCELUSERID |
| 32 | `COMPLETE_EMPNAME` | VARCHAR2(40) | 40 | 是 | COMPLETEUSERID |
| 33 | `COMPLETE_FULLNAME` | VARCHAR2(255) | 255 | 是 | COMPLETEUSERID |
| 34 | `CREATE_EMPNAME` | VARCHAR2(40) | 40 | 是 | CREATEUSERID |
| 35 | `CREATE_FULLNAME` | VARCHAR2(255) | 255 | 是 | CREATEUSERID |
| 36 | `RESOURCENAME` | VARCHAR2(40) | 40 | 是 | RESOURCEID |
| 37 | `CONTAINERIDS` | VARCHAR2(2000) | 2000 | 是 | 唯一标识符 |
| 38 | `CONTAINERNAMES` | VARCHAR2(2000) | 2000 | 是 | 名称 |
| 39 | `PARTREQUESTORDERNAME` | VARCHAR2(2000) | 2000 | 是 | DW_MES_PARTREQUESTORDER |
| 40 | `RESOURCE_PKG_GROUP` | VARCHAR2(255) | 255 | 是 | None |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_JOB_COMPLETEDATE` | 普通索引 | COMPLETEDATE |
| `DW_MES_JOB_CREATEDATE` | 普通索引 | CREATEDATE |
| `DW_MES_JOB_RESOURCEID` | 普通索引 | RESOURCEID |
| `DW_MES_JOB_RESOURCENAME` | 普通索引 | RESOURCENAME |

---

### DW_MES_JOBTXNHISTORY

**用途**: 維修工單交易歷史表 - 工單狀態變更紀錄

**数据量**: 9,743,810 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `ACKNOWLEDGECOUNT` | NUMBER(10) | 22 | 是 | None |
| 2 | `ASSIGNCOUNT` | NUMBER(10) | 22 | 是 | None |
| 3 | `CAUSECODEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 4 | `CAUSECODENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 5 | `CHECKLISTONLY` | NUMBER(10) | 22 | 是 | None |
| 6 | `CLOCKONCOUNT` | NUMBER(10) | 22 | 是 | None |
| 7 | `ESTIMATEDDURATION` | NUMBER | 22 | 是 | None |
| 8 | `EXPECTEDSTARTDATE` | DATE | 7 | 是 | None |
| 9 | `FROMJOBSTATUS` | VARCHAR2(40) | 40 | 是 | 状态 |
| 10 | `HISTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 11 | `HISTORYMAINLINEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 12 | `JOBID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 13 | `JOBMODELID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 14 | `JOBMODELNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 15 | `JOBORDERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 16 | `JOBORDERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 17 | `JOBSTATUS` | VARCHAR2(40) | 40 | 是 | 状态 |
| 18 | `JOBTXNHISTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 19 | `REPAIRCODEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 20 | `REPAIRCODENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 21 | `STAGEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 22 | `STAGENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 23 | `STAGESEQUENCE` | NUMBER(10) | 22 | 是 | None |
| 24 | `SYMPTOMCODEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 25 | `SYMPTOMCODENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 26 | `TOSTAGEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 27 | `TOSTAGENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 28 | `TOSTAGESEQUENCE` | NUMBER(10) | 22 | 是 | None |
| 29 | `TXNID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 30 | `TXNDATE` | DATE | 7 | 是 | None |
| 31 | `USERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 32 | `EMPLOYEEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 33 | `USER_EMPNO` | VARCHAR2(40) | 40 | 是 | 工號 |
| 34 | `USER_NAME` | VARCHAR2(255) | 255 | 是 | 姓名 |
| 35 | `EMP_EMPNO` | VARCHAR2(40) | 40 | 是 | 工號 |
| 36 | `EMP_NAME` | VARCHAR2(255) | 255 | 是 | 姓名 |
| 37 | `COMMENTS` | VARCHAR2(255) | 255 | 是 | HistoryMainline |
| 38 | `CDONAME` | VARCHAR2(40) | 40 | 是 | HistoryMainline |
| 39 | `CALLBYCDONAME` | VARCHAR2(40) | 40 | 是 | HistoryMainline |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `JOBTXN0_HISTORYMAINLINEID` | 普通索引 | HISTORYMAINLINEID |
| `JOBTXN0_JOBID` | 普通索引 | JOBID |
| `JOBTXN0_JOBTXNHISTORYID` | 普通索引 | JOBTXNHISTORYID |
| `JOBTXN0_TXNDATE` | 普通索引 | TXNDATE |

---

### DW_MES_LOTMATERIALSHISTORY

**用途**: 批次物料消耗歷史表 - 用料與批次關聯

**数据量**: 18,136,445 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `CONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 2 | `FINISHEDRUNCARD` | VARCHAR2(255) | 255 | 是 | None |
| 3 | `PJ_WORKORDER` | VARCHAR2(40) | 40 | 是 | None |
| 4 | `WORKCENTERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 5 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 6 | `SPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 7 | `SPECNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 8 | `MATERIALPARTNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 9 | `DESCRIPTION` | VARCHAR2(255) | 255 | 是 | None |
| 10 | `MATERIALLOTNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 11 | `EQUIPMENTID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 12 | `EQUIPMENTNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 13 | `QTYREQUIRED` | NUMBER | 22 | 是 | 数量 |
| 14 | `CONSUMEFACTOR` | NUMBER | 22 | 是 | None |
| 15 | `QTYCONSUMED` | NUMBER | 22 | 是 | 数量 |
| 16 | `TXNDATE` | DATE | 7 | 是 | None |
| 17 | `VENDORLOTNUMBER` | VARCHAR2(40) | 40 | 是 | None |
| 18 | `MANUFACTUREREXPIRYDATE` | DATE | 7 | 是 | None |
| 19 | `WITHDRAWALTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 20 | `THAWINGTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 21 | `EXPIRYTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 22 | `CONSUMEMATERIALSHISTORYDETAIID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 23 | `LAST_UPDATED_DATE` | DATE | 7 | 是 | None |
| 24 | `PRIMARY_CATEGORY` | VARCHAR2(40) | 40 | 是 | None |
| 25 | `SECONDARY_CATEGORY` | VARCHAR2(40) | 40 | 是 | None |
| 26 | `UOMNAME` | VARCHAR2(40) | 40 | 是 | 名称 |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_LOTMATERIALSHISTORY_IDX1` | 普通索引 | CONTAINERID |
| `DW_MES_LOTMATERIALSHISTORY_IDX2` | 普通索引 | PJ_WORKORDER |
| `DW_MES_LOTMATERIALSHISTORY_IDX3` | 普通索引 | MATERIALPARTNAME |
| `DW_MES_LOTMATERIALSHISTORY_IDX4` | 普通索引 | MATERIALLOTNAME |

---

### DW_MES_LOTREJECTHISTORY

**用途**: 批次不良/報廢歷史表 - 不良原因與數量

**数据量**: 16,103,258 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `HISTORYMAINLINEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 2 | `CONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 3 | `FINISHEDRUNCARD` | VARCHAR2(255) | 255 | 是 | None |
| 4 | `PJ_WORKORDER` | VARCHAR2(40) | 40 | 是 | None |
| 5 | `WORKCENTERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 6 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 7 | `SPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 8 | `SPECNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 9 | `EQUIPMENTNAME` | VARCHAR2(255) | 255 | 是 | 名称 |
| 10 | `MOVEINTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 11 | `MOVEINQTY` | NUMBER | 22 | 是 | 数量 |
| 12 | `MOVEINQTY2` | NUMBER | 22 | 是 | 数量 |
| 13 | `EMPLOYEENAME` | VARCHAR2(100) | 100 | 是 | 名称 |
| 14 | `SHIFTNAME` | VARCHAR2(30) | 30 | 是 | 名称 |
| 15 | `TXNDATE` | DATE | 7 | 是 | None |
| 16 | `COMMENTS` | VARCHAR2(255) | 255 | 是 | None |
| 17 | `LOSSREASONID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 18 | `LOSSREASONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 19 | `WAFERSCRIBENUMBER` | VARCHAR2(40) | 40 | 是 | None |
| 20 | `REJECTCATEGORYNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 21 | `REJECTQTY` | NUMBER | 22 | 是 | 数量 |
| 22 | `STANDBYQTY` | NUMBER | 22 | 是 | 数量 |
| 23 | `QTYTOPROCESS` | NUMBER | 22 | 是 | 数量 |
| 24 | `INPROCESSQTY` | NUMBER | 22 | 是 | 数量 |
| 25 | `PROCESSEDQTY` | NUMBER | 22 | 是 | 数量 |
| 26 | `DEFECTQTY` | NUMBER | 22 | 是 | 数量 |
| 27 | `WAFERREJECTSQTY` | NUMBER | 22 | 是 | 数量 |
| 28 | `REJECTCAUSE` | VARCHAR2(40) | 40 | 是 | None |
| 29 | `REJECTCOMMENT` | VARCHAR2(255) | 255 | 是 | None |
| 30 | `PJ_WAFERID1` | VARCHAR2(255) | 255 | 是 | 唯一标识符 |
| 31 | `PJ_WAFERID2` | VARCHAR2(255) | 255 | 是 | 唯一标识符 |
| 32 | `PJ_WAFERID3` | VARCHAR2(255) | 255 | 是 | 唯一标识符 |
| 33 | `LAST_UPDATED_DATE` | DATE | 7 | 是 | None |
| 34 | `EMPZONE` | VARCHAR2(100) | 100 | 是 | None |
| 35 | `WIPTRACKINGGROUPKEYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 36 | `FROMQTY` | NUMBER | 22 | 是 | 数量 |
| 37 | `FROMQTY2` | NUMBER | 22 | 是 | 数量 |
| 38 | `QTY` | NUMBER | 22 | 是 | 数量 |
| 39 | `QTY2` | NUMBER | 22 | 是 | 数量 |
| 40 | `NOWSPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 41 | `NOWSPECNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 42 | `NOWWORKCENTERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 43 | `NOWWORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_LOTREJECTHISTORY_IDX1` | 普通索引 | CONTAINERID |
| `DW_MES_LOTREJECTHISTORY_IDX2` | 普通索引 | SPECID |
| `DW_MES_LOTREJECTHISTORY_IDX3` | 普通索引 | HISTORYMAINLINEID |
| `DW_MES_LOTREJECTHISTORY_IDX4` | 普通索引 | TXNDATE |
| `DW_MES_LOTREJECTHISTORY_IDX5` | 普通索引 | WIPTRACKINGGROUPKEYID |

---

### DW_MES_LOTWIPDATAHISTORY

**用途**: 在製數據採集歷史表 - 製程量測/參數紀錄

**数据量**: 80,316,112 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `CONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 2 | `FINISHEDRUNCARD` | VARCHAR2(255) | 255 | 是 | None |
| 3 | `PJ_WORKORDER` | VARCHAR2(40) | 40 | 是 | None |
| 4 | `WORKCENTERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 5 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 6 | `SPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 7 | `SPECNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 8 | `EQUIPMENTID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 9 | `EQUIPMENTNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 10 | `EMPLOYEENAME` | VARCHAR2(100) | 100 | 是 | 名称 |
| 11 | `SERVICENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 12 | `TXNTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 13 | `WIPDATANAMEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 14 | `WIPDATANAMENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 15 | `WIPDATAVALUE` | VARCHAR2(4000) | 4000 | 是 | None |
| 16 | `PJ_SPCDATARESULT` | VARCHAR2(40) | 40 | 是 | None |
| 17 | `WIPLOTHISTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 18 | `LAST_UPDATED_DATE` | DATE | 7 | 是 | None |
| 19 | `PROCESSTYPENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 20 | `WAFERSCRIBENUMBER` | VARCHAR2(40) | 40 | 是 | None |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_LOTWIPDATAHISTORY_IDX1` | 普通索引 | CONTAINERID |
| `DW_MES_LOTWIPDATAHISTORY_IDX2` | 普通索引 | WIPLOTHISTORYID |
| `DW_MES_LOTWIPDATAHISTORY_IDX3` | 普通索引 | PJ_WORKORDER |
| `DW_MES_LOTWIPDATAHISTORY_IDX4` | 普通索引 | TXNTIMESTAMP |

---

### DW_MES_LOTWIPHISTORY

**用途**: 在製流轉歷史表 - 批次進出站與流程軌跡

**数据量**: 54,519,619 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `WIPLOTHISTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 2 | `WIPEQUIPMENTHISTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 3 | `CONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 4 | `FINISHEDRUNCARD` | VARCHAR2(255) | 255 | 是 | None |
| 5 | `PJ_WORKORDER` | VARCHAR2(40) | 40 | 是 | None |
| 6 | `WORKCENTERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 7 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 8 | `SPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 9 | `SPECNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 10 | `PJ_WAFERID1` | VARCHAR2(255) | 255 | 是 | 唯一标识符 |
| 11 | `PJ_WAFERID2` | VARCHAR2(255) | 255 | 是 | 唯一标识符 |
| 12 | `PJ_WAFERID3` | VARCHAR2(255) | 255 | 是 | 唯一标识符 |
| 13 | `WORKFLOWNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 14 | `PRODUCTNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 15 | `DESCRIPTION` | VARCHAR2(255) | 255 | 是 | None |
| 16 | `DATECODE` | VARCHAR2(40) | 40 | 是 | None |
| 17 | `MOVEINTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 18 | `MOVEINQTY` | NUMBER | 22 | 是 | 数量 |
| 19 | `MOVEOUTTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 20 | `MOVEOUTQTY` | NUMBER | 22 | 是 | 数量 |
| 21 | `EQUIPMENTID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 22 | `EQUIPMENTNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 23 | `TRACKINTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 24 | `TRACKINQTY` | NUMBER | 22 | 是 | 数量 |
| 25 | `TRACKINEMPLOYEENAME` | VARCHAR2(100) | 100 | 是 | 名称 |
| 26 | `TRACKOUTTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 27 | `TRACKOUTQTY` | NUMBER | 22 | 是 | 数量 |
| 28 | `TRACKOUTEMPLOYEENAME` | VARCHAR2(100) | 100 | 是 | 名称 |
| 29 | `FLAGNAME` | VARCHAR2(255) | 255 | 是 | 名称 |
| 30 | `CARRIERNAME` | VARCHAR2(2000) | 2000 | 是 | 名称 |
| 31 | `LAST_UPDATED_DATE` | DATE | 7 | 是 | None |
| 32 | `LAST_SYNC_DATE` | DATE | 7 | 是 | None |
| 33 | `PROCESSTYPENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 34 | `PACKAGE_LF` | VARCHAR2(60) | 60 | 是 | None |
| 35 | `PROCESSSPECNAME` | VARCHAR2(255) | 255 | 是 | 名称 |
| 36 | `TRACKINEMPZONE` | VARCHAR2(100) | 100 | 是 | None |
| 37 | `TRACKOUTEMPZONE` | VARCHAR2(100) | 100 | 是 | None |
| 38 | `MOVEINQTY2` | NUMBER | 22 | 是 | 数量 |
| 39 | `MOVEOUTQTY2` | NUMBER | 22 | 是 | 数量 |
| 40 | `TRACKINQTY2` | NUMBER | 22 | 是 | 数量 |
| 41 | `TRACKOUTQTY2` | NUMBER | 22 | 是 | 数量 |
| 42 | `WIPTRACKINGGROUPKEYID` | CHAR(16) | 16 | 是 | 唯一标识符 |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_LOTWIPHISTORY_IDX1` | 普通索引 | CONTAINERID |
| `DW_MES_LOTWIPHISTORY_IDX2` | 普通索引 | WIPLOTHISTORYID |
| `DW_MES_LOTWIPHISTORY_IDX3` | 普通索引 | TRACKINTIMESTAMP |
| `DW_MES_LOTWIPHISTORY_IDX4` | 普通索引 | PJ_WORKORDER |
| `DW_MES_LOTWIPHISTORY_IDX5` | 普通索引 | DATECODE |
| `DW_MES_LOTWIPHISTORY_IDX6` | 普通索引 | WORKCENTERID |
| `DW_MES_LOTWIPHISTORY_IDX7` | 普通索引 | WIPEQUIPMENTHISTORYID |
| `DW_MES_LOTWIPHISTORY_IDX8` | 普通索引 | MOVEINTIMESTAMP |
| `DW_MES_LOTWIPHISTORY_IDX9` | 普通索引 | WIPTRACKINGGROUPKEYID |

---

### DW_MES_LOT_V

**用途**: MES 即時 WIP 視圖 - 批次現況、工站、設備與 Hold 資訊

**数据量**: 9,923 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `NO` | NUMBER | 22 | 是 | None |
| 2 | `CONTAINERID` | CHAR(16) | 16 | 否 | 唯一标识符 |
| 3 | `LOTID` | VARCHAR2(40) | 40 | 是 | 唯一标识符 |
| 4 | `QTY` | NUMBER | 22 | 是 | 数量 |
| 5 | `QTY2` | NUMBER | 22 | 是 | 数量 |
| 6 | `STATUS` | VARCHAR2(10) | 10 | 是 | 状态 |
| 7 | `HOLDREASONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 8 | `CURRENTHOLDCOUNT` | NUMBER(10) | 22 | 是 | None |
| 9 | `STARTREASON` | VARCHAR2(40) | 40 | 是 | None |
| 10 | `OWNER` | VARCHAR2(40) | 40 | 是 | None |
| 11 | `STARTDATE` | DATE | 7 | 是 | None |
| 12 | `UTS` | VARCHAR2(10) | 10 | 是 | None |
| 13 | `STARTQTY` | NUMBER | 22 | 是 | 数量 |
| 14 | `STARTQTY2` | NUMBER | 22 | 是 | 数量 |
| 15 | `FIRSTNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 16 | `PRODUCT` | VARCHAR2(40) | 40 | 是 | None |
| 17 | `STEP` | VARCHAR2(40) | 40 | 是 | None |
| 18 | `SPECNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 19 | `WORKCENTERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 20 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 21 | `HOLDLOCATION` | VARCHAR2(40) | 40 | 是 | None |
| 22 | `AGEBYDAYS` | NUMBER | 22 | 是 | None |
| 23 | `REMAINTIME` | NUMBER | 22 | 是 | None |
| 24 | `MOVEINQTY` | NUMBER | 22 | 是 | 数量 |
| 25 | `MOVEINQTY2` | NUMBER | 22 | 是 | 数量 |
| 26 | `MOVEINTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 27 | `MOVEINUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 28 | `EQUIPMENTCOUNT` | NUMBER(10) | 22 | 是 | None |
| 29 | `EQUIPMENTS` | VARCHAR2(4000) | 4000 | 是 | None |
| 30 | `JOBCREATEDATE` | VARCHAR2(4000) | 4000 | 是 | 创建日期 |
| 31 | `JOBCOMMENTS` | VARCHAR2(4000) | 4000 | 是 | None |
| 32 | `MATERIALTYPE` | VARCHAR2(40) | 40 | 是 | None |
| 33 | `PRODUCTLINENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 34 | `PACKAGE_LEF` | VARCHAR2(4000) | 4000 | 是 | None |
| 35 | `PB_FUNCTION` | VARCHAR2(40) | 40 | 是 | None |
| 36 | `WORKFLOWNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 37 | `BOP` | VARCHAR2(40) | 40 | 是 | None |
| 38 | `DATECODE` | VARCHAR2(40) | 40 | 是 | None |
| 39 | `LEADFRAMENAME` | VARCHAR2(4000) | 4000 | 是 | 名称 |
| 40 | `LEADFRAMEDESC` | VARCHAR2(4000) | 4000 | 是 | None |
| 41 | `LEADFRAMEOPTION` | VARCHAR2(4000) | 4000 | 是 | None |
| 42 | `COMNAME` | VARCHAR2(4000) | 4000 | 是 | 名称 |
| 43 | `LOCATIONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 44 | `PJ_FUNCTION` | VARCHAR2(40) | 40 | 是 | None |
| 45 | `PJ_TYPE` | VARCHAR2(40) | 40 | 是 | None |
| 46 | `WAFERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 47 | `WAFERDESC` | VARCHAR2(255) | 255 | 是 | None |
| 48 | `WAFERLOT` | VARCHAR2(160) | 160 | 是 | None |
| 49 | `EVENTNAME` | VARCHAR2(4000) | 4000 | 是 | 名称 |
| 50 | `OCCURRENCEDATE` | VARCHAR2(4000) | 4000 | 是 | None |
| 51 | `RELEASETIME` | VARCHAR2(4000) | 4000 | 是 | None |
| 52 | `RELEASEEMP` | VARCHAR2(4000) | 4000 | 是 | None |
| 53 | `RELEASEREASON` | VARCHAR2(4000) | 4000 | 是 | None |
| 54 | `COMMENT_HOLD` | VARCHAR2(255) | 255 | 是 | None |
| 55 | `CONTAINERCOMMENTS` | VARCHAR2(2000) | 2000 | 是 | None |
| 56 | `COMMENT_DATE` | DATE | 7 | 是 | None |
| 57 | `COMMENT_EMP` | VARCHAR2(255) | 255 | 是 | None |
| 58 | `COMMENT_FUTURE` | VARCHAR2(255) | 255 | 是 | None |
| 59 | `HOLDEMP` | VARCHAR2(255) | 255 | 是 | None |
| 60 | `DEPTNAME` | VARCHAR2(255) | 255 | 是 | 名称 |
| 61 | `PJ_PRODUCEREGION` | VARCHAR2(40) | 40 | 是 | None |
| 62 | `WORKORDER` | VARCHAR2(40) | 40 | 是 | None |
| 63 | `PRIORITYCODENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 64 | `SPECSEQUENCE` | VARCHAR2(10) | 10 | 是 | None |
| 65 | `WORKCENTERSEQUENCE` | VARCHAR2(255) | 255 | 是 | None |
| 66 | `TMTT_R` | CHAR(1) | 1 | 是 | None |
| 67 | `WAFER_FACTOR` | NUMBER | 22 | 是 | None |
| 68 | `WORKCENTER_GROUP` | VARCHAR2(40) | 40 | 是 | None |
| 69 | `WORKCENTERSEQUENCE_GROUP` | VARCHAR2(255) | 255 | 是 | None |
| 70 | `WORKCENTER_SHORT` | VARCHAR2(40) | 40 | 是 | None |
| 71 | `EQUIPMENTNAME` | VARCHAR2(4000) | 4000 | 是 | 名称 |
| 72 | `SYS_DATE` | DATE | 7 | 是 | None |

---

### DW_MES_MAINTENANCE

**用途**: 設備保養/維護紀錄表 - 保養計畫與點檢數據

**数据量**: 55,101,182 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `RESOURCEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 2 | `HISTORYMAINLINEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 3 | `RESOURCENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 4 | `SHIFTNAME` | VARCHAR2(30) | 30 | 是 | 名称 |
| 5 | `TXNDATE` | DATE | 7 | 是 | None |
| 6 | `LASTDATEDUE` | DATE | 7 | 是 | None |
| 7 | `LASTTHRUPUTQTYDUE` | NUMBER | 22 | 是 | 数量 |
| 8 | `LASTTHRUPUTQTYLIMIT` | NUMBER | 22 | 是 | 数量 |
| 9 | `LASTTHRUPUTQTYWARNING` | NUMBER | 22 | 是 | 数量 |
| 10 | `MAINTENANCEREQID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 11 | `MAINTENANCEREQNAME` | VARCHAR2(255) | 255 | 是 | 名称 |
| 12 | `CDOTYPEID` | NUMBER(10) | 22 | 是 | 唯一标识符 |
| 13 | `THRUPUTQTY` | NUMBER | 22 | 是 | 数量 |
| 14 | `CHECKLISTACTION` | NUMBER(10) | 22 | 是 | None |
| 15 | `INSTRUCTION` | VARCHAR2(4000) | 4000 | 是 | None |
| 16 | `DATANAME` | VARCHAR2(255) | 255 | 是 | 名称 |
| 17 | `DATAVALUE` | VARCHAR2(255) | 255 | 是 | None |
| 18 | `LOCATIONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 19 | `USERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 20 | `EMPLOYEENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 21 | `FULLNAME` | VARCHAR2(255) | 255 | 是 | 名称 |
| 22 | `PJ_INSPECTIONLOT` | VARCHAR2(40) | 40 | 是 | None |
| 23 | `DATAPOINTID` | CHAR(16) | 16 | 是 | 唯一标识符 |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_MAINTENANCE_IDX1` | 普通索引 | HISTORYMAINLINEID |
| `DW_MES_MAINTENANCE_IDX2` | 普通索引 | TXNDATE |
| `DW_MES_MAINTENANCE_IDX3` | 普通索引 | MAINTENANCEREQNAME |
| `DW_MES_MAINTENANCE_IDX4` | 普通索引 | RESOURCEID |
| `DW_MES_MAINTENANCE_IDX5` | 普通索引 | MAINTENANCEREQID |
| `DW_MES_MAINTENANCE_IDX6` | 普通索引 | RESOURCENAME |
| `DW_MES_MAINTENANCE_IDX7` | 普通索引 | CDOTYPEID |

---

### DW_MES_PARTREQUESTORDER

**用途**: 維修用料請求表 - 維修/設備零件請領

**数据量**: 61,396 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `DESCRIPTION` | VARCHAR2(255) | 255 | 是 | None |
| 2 | `ISDONE` | NUMBER(10) | 22 | 是 | None |
| 3 | `JOBID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 4 | `PARTREQUESTORDERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 5 | `PARTREQUESTORDERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 6 | `REQUESTSTATUS` | VARCHAR2(40) | 40 | 是 | 状态 |
| 7 | `REQUESTTYPE` | NUMBER(10) | 22 | 是 | None |
| 8 | `REQUIREACKNOWLEDGEEMAIL` | NUMBER(10) | 22 | 是 | None |
| 9 | `RESOURCEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 10 | `CREATIONDATE` | DATE | 7 | 是 | None |
| 11 | `CREATIONUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 12 | `LASTCHANGEDATE` | DATE | 7 | 是 | None |
| 13 | `USERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 14 | `RESOURCENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 15 | `USER_EMPNO` | VARCHAR2(40) | 40 | 是 | 工號 |
| 16 | `USER_NAME` | VARCHAR2(255) | 255 | 是 | 姓名 |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_PARTREQUESTORDER_JOBID` | 普通索引 | JOBID |
| `DW_MES_PARTREQUESTORDER_RESOURCEID` | 普通索引 | RESOURCEID |

---

### DW_MES_PJ_COMBINEDASSYLOTS

**用途**: 併批紀錄表 - 合批/合併批次關聯與數量資訊

**数据量**: 1,994,711 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `CONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 2 | `CONTAINERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 3 | `PJ_WORKORDER` | VARCHAR2(40) | 40 | 是 | None |
| 4 | `PJ_COMBINEDASSEMBLYLOTSID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 5 | `LOTID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 6 | `FINISHEDNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 7 | `PJ_EXCESSLOTQTY` | NUMBER | 22 | 是 | 数量 |
| 8 | `PJ_GOODDIEQTY` | NUMBER | 22 | 是 | 数量 |
| 9 | `PJ_COMBINEDRATIO` | NUMBER | 22 | 是 | None |
| 10 | `PJ_ORIGINALGOODDIEQTY` | NUMBER | 22 | 是 | 数量 |
| 11 | `ORIGINALSTARTDATE` | DATE | 7 | 是 | None |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_PJ_COMBINEDASSYLOTS_IDX1` | 普通索引 | CONTAINERID |
| `DW_MES_PJ_COMBINEDASSYLOTS_IDX2` | 普通索引 | FINISHEDNAME |
| `DW_MES_PJ_COMBINEDASSYLOTS_IDX3` | 普通索引 | PJ_WORKORDER |

---

### DW_MES_RESOURCE

**用途**: 資源表 - 設備/載具等資源基本資料（OBJECTCATEGORY=ASSEMBLY 時，RESOURCENAME 為設備編號）

**数据量**: 91,673 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `AUTOMATIONPLANID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 2 | `BOMBASEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 3 | `BOMID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 4 | `CONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 5 | `DESCRIPTION` | VARCHAR2(255) | 255 | 是 | None |
| 6 | `DOCUMENTSETID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 7 | `EQUIPMENTTYPE` | VARCHAR2(40) | 40 | 是 | None |
| 8 | `FACTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 9 | `LOCATIONID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 10 | `LOTCOUNT` | NUMBER(10) | 22 | 是 | None |
| 11 | `MACHINEGROUPID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 12 | `MAINTENANCECLASSID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 13 | `MAXLOTS` | NUMBER(10) | 22 | 是 | None |
| 14 | `MAXUNITS` | NUMBER | 22 | 是 | None |
| 15 | `MULTILOTSFLAG` | NUMBER(10) | 22 | 是 | None |
| 16 | `NOTES` | VARCHAR2(2000) | 2000 | 是 | None |
| 17 | `OBJECTCATEGORY` | VARCHAR2(40) | 40 | 是 | None |
| 18 | `OBJECTTYPE` | VARCHAR2(40) | 40 | 是 | None |
| 19 | `PACKAGEGROUPID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 20 | `PARAMLISTID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 21 | `PARENTRESOURCEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 22 | `PRODUCTIONSTATUSID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 23 | `RECIPEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 24 | `RESOURCECOMMENTS` | VARCHAR2(2000) | 2000 | 是 | None |
| 25 | `RESOURCEFAMILYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 26 | `RESOURCEID` | CHAR(16) | 16 | 否 | 唯一标识符 |
| 27 | `RESOURCENAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 28 | `SETUPACCESSID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 29 | `SPCSETUPID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 30 | `STATUSMODELID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 31 | `SUBEQUIPMENTLOGICALID` | VARCHAR2(40) | 40 | 是 | 唯一标识符 |
| 32 | `TOOLPLANID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 33 | `TRAININGREQGROUPID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 34 | `UOMID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 35 | `USESPCMATRIX` | NUMBER(10) | 22 | 是 | None |
| 36 | `VENDORID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 37 | `VENDORMODEL` | VARCHAR2(30) | 30 | 是 | None |
| 38 | `VENDORSERIALNUMBER` | VARCHAR2(30) | 30 | 是 | None |
| 39 | `WIPMSGDEFMGRID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 40 | `PJ_DATECODE1` | VARCHAR2(40) | 40 | 是 | None |
| 41 | `PJ_DATECODE2` | VARCHAR2(40) | 40 | 是 | None |
| 42 | `PJ_FINISHEDPRODUCT` | VARCHAR2(40) | 40 | 是 | None |
| 43 | `PJ_OWNER` | VARCHAR2(40) | 40 | 是 | None |
| 44 | `PJ_PROCESSSPEC` | VARCHAR2(40) | 40 | 是 | None |
| 45 | `PJ_WAFERPRODUCT` | VARCHAR2(40) | 40 | 是 | None |
| 46 | `PJ_WORKORDER` | VARCHAR2(40) | 40 | 是 | None |
| 47 | `PJ_CHECKBYHOUR` | NUMBER | 22 | 是 | None |
| 48 | `PJ_CHECKBYIDLETIME` | NUMBER | 22 | 是 | 唯一标识符 |
| 49 | `PJ_CHECKBYLOT` | NUMBER(10) | 22 | 是 | None |
| 50 | `PJ_CHECKBYPRODUCT` | NUMBER(10) | 22 | 是 | None |
| 51 | `PJ_CHECKBYTYPE` | NUMBER(10) | 22 | 是 | None |
| 52 | `PJ_CHECKBYWORKORDER` | NUMBER(10) | 22 | 是 | None |
| 53 | `PJ_VERIFYSPCRESULT` | NUMBER(10) | 22 | 是 | None |
| 54 | `PJ_ASSETSSTATUS` | VARCHAR2(40) | 40 | 是 | 状态 |
| 55 | `PJ_WORKCENTER_ID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 56 | `PJ_AUEQUIPMENTGROUPID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 57 | `PJ_CONTROLLENGTH` | NUMBER(10) | 22 | 是 | None |
| 58 | `PJ_DEPARTMENT` | VARCHAR2(100) | 100 | 是 | None |
| 59 | `PJ_EMPLOYEE` | VARCHAR2(100) | 100 | 是 | None |
| 60 | `PJ_ISAUEQUIPMENT` | NUMBER(10) | 22 | 是 | None |
| 61 | `PJ_LOTID` | VARCHAR2(40) | 40 | 是 | 唯一标识符 |
| 62 | `PJ_SETUPACCESSID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 63 | `PJ_SPCSETUP` | CHAR(16) | 16 | 是 | None |
| 64 | `PJ_WORKCENTERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 65 | `PJ_AUTOMATIONLEVEL` | NUMBER(10) | 22 | 是 | None |
| 66 | `CREATIONDATE` | DATE | 7 | 是 | None |
| 67 | `CREATIONUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 68 | `LASTCHANGEDATE` | DATE | 7 | 是 | None |
| 69 | `USERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 70 | `AUTOMATIONPLANNAME` | VARCHAR2(40) | 40 | 是 | AUTOMATIONPLANID |
| 71 | `LOCATIONNAME` | VARCHAR2(40) | 40 | 是 | LOCATIONID |
| 72 | `RESOURCEFAMILYNAME` | VARCHAR2(30) | 30 | 是 | RESOURCEFAMILYID |
| 73 | `VENDORNAME` | VARCHAR2(40) | 40 | 是 | VENDORID |
| 74 | `PJ_ERPVENDORID` | VARCHAR2(40) | 40 | 是 | VENDORID |
| 75 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | PJ_WORKCENTERID |
| 76 | `PJ_ISPRODUCTION` | NUMBER | 22 | 是 | 20251217 add:生產設備 |
| 77 | `PJ_ISKEY` | NUMBER | 22 | 是 | 20251217 add:關鍵設備 |
| 78 | `PJ_ISMONITOR` | NUMBER | 22 | 是 | 20251217 add:監控設備 |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `OBJECT` | 普通索引 | OBJECTCATEGORY, OBJECTTYPE |
| `RESOURCEID` | 普通索引 | RESOURCEID |

---

### DW_MES_RESOURCESTATUS

**用途**: 設備狀態變更歷史表 - 狀態切換與原因

**数据量**: 67,681,971 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `HISTORYID` | CHAR(16) | 16 | 是 | RESOURCEID |
| 2 | `HISTORYMAINLINEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 3 | `RESOURCESTATUSHISTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 4 | `AVAILABILITY` | NUMBER(10) | 22 | 是 | None |
| 5 | `LASTSTATUSCHANGEDATE` | DATE | 7 | 是 | 状态 |
| 6 | `NEWREASONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 7 | `NEWSTATUSNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 8 | `UPDATELASTSTATUSCHANGEDATE` | NUMBER(10) | 22 | 是 | 状态 |
| 9 | `OLDAVAILABILITY` | NUMBER(10) | 22 | 是 | None |
| 10 | `OLDLASTACTIVITYDATE` | DATE | 7 | 是 | None |
| 11 | `OLDLASTSTATUSCHANGEDATE` | DATE | 7 | 是 | 状态 |
| 12 | `OLDREASONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 13 | `OLDSTATUSNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 14 | `OLDUPDATELASTSTATUSCHANGEDATE` | NUMBER(10) | 22 | 是 | 状态 |
| 15 | `SS_ISDOWNVIAPARENT` | NUMBER(10) | 22 | 是 | None |
| 16 | `JOBID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 17 | `TXNDATE` | DATE | 7 | 是 | 資料更新時間(做差異同步用) |
| 18 | `DESCRIPTION` | VARCHAR2(255) | 255 | 是 | None |
| 19 | `RESOURCEFAMILYNAME` | VARCHAR2(30) | 30 | 是 | RESOURCEFAMILYID |
| 20 | `VENDORNAME` | VARCHAR2(40) | 40 | 是 | VENDORID |
| 21 | `VENDORMODEL` | VARCHAR2(30) | 30 | 是 | None |
| 22 | `PJ_ERPVENDORID` | VARCHAR2(40) | 40 | 是 | VENDORID |
| 23 | `LOCATIONNAME` | VARCHAR2(40) | 40 | 是 | LOCATIONID |
| 24 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | PJ_WORKCENTERID |
| 25 | `PJ_ASSETSSTATUS` | VARCHAR2(40) | 40 | 是 | 状态 |
| 26 | `PJ_DEPARTMENT` | VARCHAR2(100) | 100 | 是 | None |
| 27 | `AUTOMATIONPLANNAME` | VARCHAR2(40) | 40 | 是 | AUTOMATIONPLANID |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `HISTORYID` | 普通索引 | HISTORYID |
| `OLDLASTSTATUSCHANGEDATE` | 普通索引 | OLDLASTSTATUSCHANGEDATE |

---

### DW_MES_RESOURCESTATUS_SHIFT

**用途**: 設備狀態班次彙總表 - 班次級狀態/工時

**数据量**: 76,947,961 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `HISTORYID` | CHAR(16) | 16 | 是 | RESOURCEID |
| 2 | `HISTORYMAINLINEID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 3 | `RESOURCESTATUSHISTORYID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 4 | `AVAILABILITY` | NUMBER(10) | 22 | 是 | None |
| 5 | `LASTSTATUSCHANGEDATE` | DATE | 7 | 是 | 状态 |
| 6 | `NEWREASONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 7 | `NEWSTATUSNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 8 | `UPDATELASTSTATUSCHANGEDATE` | NUMBER(10) | 22 | 是 | 状态 |
| 9 | `OLDAVAILABILITY` | NUMBER(10) | 22 | 是 | None |
| 10 | `OLDLASTACTIVITYDATE` | DATE | 7 | 是 | None |
| 11 | `OLDLASTSTATUSCHANGEDATE` | DATE | 7 | 是 | 状态 |
| 12 | `OLDREASONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 13 | `OLDSTATUSNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 14 | `OLDUPDATELASTSTATUSCHANGEDATE` | NUMBER(10) | 22 | 是 | 状态 |
| 15 | `SS_ISDOWNVIAPARENT` | NUMBER(10) | 22 | 是 | None |
| 16 | `TXNDATE` | DATE | 7 | 是 | None |
| 17 | `HOURS` | NUMBER(12,6) | 22 | 是 | None |
| 18 | `JOBID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 19 | `DATADATE` | DATE | 7 | 是 | None |
| 20 | `SN` | NUMBER | 22 | 是 | None |
| 21 | `DESCRIPTION` | VARCHAR2(255) | 255 | 是 | None |
| 22 | `RESOURCEFAMILYNAME` | VARCHAR2(30) | 30 | 是 | RESOURCEFAMILYID |
| 23 | `VENDORNAME` | VARCHAR2(40) | 40 | 是 | VENDORID |
| 24 | `VENDORMODEL` | VARCHAR2(30) | 30 | 是 | None |
| 25 | `PJ_ERPVENDORID` | VARCHAR2(40) | 40 | 是 | VENDORID |
| 26 | `LOCATIONNAME` | VARCHAR2(40) | 40 | 是 | LOCATIONID |
| 27 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | PJ_WORKCENTERID |
| 28 | `PJ_ASSETSSTATUS` | VARCHAR2(40) | 40 | 是 | 状态 |
| 29 | `PJ_DEPARTMENT` | VARCHAR2(100) | 100 | 是 | None |
| 30 | `AUTOMATIONPLANNAME` | VARCHAR2(40) | 40 | 是 | AUTOMATIONPLANID |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_RESOURCESTATUS_SHIFT_DATADATE` | 普通索引 | DATADATE |
| `DW_MES_RESOURCESTATUS_SHIFT_HISTORYID` | 普通索引 | HISTORYID |
| `DW_MES_RESOURCESTATUS_SHIFT_JOBID` | 普通索引 | JOBID |
| `DW_MES_RESOURCESTATUS_SHIFT_OLDLASTSTATUSCHANGEDATE` | 普通索引 | OLDLASTSTATUSCHANGEDATE |
| `DW_MES_RESOURCESTATUS_SHIFT_TXNDATE` | 普通索引 | TXNDATE |

---

### DW_MES_SPEC_WORKCENTER_V

**用途**: 工站/工序對照視圖 - 用於工站分組與排序映射

**数据量**: 230 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `SPEC` | VARCHAR2(40) | 40 | 是 | None |
| 2 | `SPECSEQUENCE` | VARCHAR2(10) | 10 | 是 | None |
| 3 | `SPEC_ORDER` | VARCHAR2(51) | 51 | 是 | None |
| 4 | `WORK_CENTER` | VARCHAR2(40) | 40 | 是 | None |
| 5 | `WORK_CENTER_SEQUENCE` | VARCHAR2(255) | 255 | 是 | None |
| 6 | `WORK_CENTER_GROUP` | VARCHAR2(40) | 40 | 是 | None |
| 7 | `WORKCENTERSEQUENCE_GROUP` | VARCHAR2(255) | 255 | 是 | None |
| 8 | `WORKCENTERGROUP_ORDER` | VARCHAR2(296) | 296 | 是 | None |
| 9 | `WORK_CENTER_SHORT` | VARCHAR2(40) | 40 | 是 | None |

---

### DW_MES_WIP

**用途**: 在製品現況表（含歷史累積）- 當前 WIP 狀態/數量

**数据量**: 84,271,674 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `CONTAINERID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 2 | `CONTAINERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 3 | `GA_CONTAINERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 4 | `QTY` | NUMBER | 22 | 是 | 数量 |
| 5 | `QTY2` | NUMBER | 22 | 是 | 数量 |
| 6 | `CURRENTHOLDCOUNT` | NUMBER(10) | 22 | 是 | None |
| 7 | `HOLDREASONID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 8 | `ORIGINALSTARTDATE` | DATE | 7 | 是 | None |
| 9 | `STATUS` | NUMBER(10) | 22 | 是 | 状态 |
| 10 | `ORIGINALQTY` | NUMBER | 22 | 是 | 数量 |
| 11 | `ORIGINALQTY2` | NUMBER | 22 | 是 | 数量 |
| 12 | `SPECID` | CHAR(16) | 16 | 是 | 唯一标识符 |
| 13 | `MOVEINTIMESTAMP` | DATE | 7 | 是 | 时间戳 |
| 14 | `MOVEINUSERNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 15 | `MOVEINQTY` | NUMBER | 22 | 是 | 数量 |
| 16 | `MOVEINQTY2` | NUMBER | 22 | 是 | 数量 |
| 17 | `STARTREASONNAME` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 18 | `EXPECTEDENDDATE` | DATE | 7 | 是 | SD |
| 19 | `WORKFLOWNAME` | VARCHAR2(40) | 40 | 是 | SD |
| 20 | `WORKFLOWSTEPNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 21 | `LOCATIONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 22 | `DATECODE` | VARCHAR2(40) | 40 | 是 | None |
| 23 | `CONTAINERCOMMENTS` | VARCHAR2(2000) | 2000 | 是 | None |
| 24 | `COMMENT_DATE` | DATE | 7 | 是 | None |
| 25 | `COMMENT_EMP` | VARCHAR2(40) | 40 | 是 | None |
| 26 | `EQUIPMENTCOUNT` | NUMBER(10) | 22 | 是 | None |
| 27 | `EQUIPMENTS` | VARCHAR2(1000) | 1000 | 是 | EM |
| 28 | `EQP_LOCATIONNAME` | VARCHAR2(1000) | 1000 | 是 | EM |
| 29 | `HOLDEMP` | VARCHAR2(40) | 40 | 是 | None |
| 30 | `HOLDDEPTNAME` | VARCHAR2(255) | 255 | 是 | 名称 |
| 31 | `HOLDLOCATIONNAME` | VARCHAR2(40) | 40 | 是 | 名称 |
| 32 | `HOLDCOMMENT_FUTURE` | VARCHAR2(255) | 255 | 是 | None |
| 33 | `HOLDREASONNAME` | VARCHAR2(40) | 40 | 是 | HOLDREASONID |
| 34 | `EVENTNAME` | VARCHAR2(1000) | 1000 | 是 | NCR |
| 35 | `OCCURRENCEDATE` | VARCHAR2(1000) | 1000 | 是 | NCR |
| 36 | `RELEASETIME` | VARCHAR2(1000) | 1000 | 是 | DW_MES_HOLDRELEASEHISTORY |
| 37 | `RELEASEEMP` | VARCHAR2(1000) | 1000 | 是 | DW_MES_HOLDRELEASEHISTORY |
| 38 | `RELEASEREASON` | VARCHAR2(1000) | 1000 | 是 | DW_MES_HOLDRELEASEHISTORY |
| 39 | `SPECNAME` | VARCHAR2(40) | 40 | 是 | SPECID |
| 40 | `WORKCENTERNAME` | VARCHAR2(40) | 40 | 是 | SPECID |
| 41 | `MFGORDERNAME` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 42 | `PJ_BOP` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 43 | `PJ_PRODUCEREGION` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 44 | `PRODUCTBOMBASEID` | CHAR(16) | 16 | 是 | CONTAINERID |
| 45 | `OWNERNAME` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 46 | `PRIORITYCODENAME` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 47 | `WOQTY` | NUMBER | 22 | 是 | CONTAINERID->MFGORDERID |
| 48 | `WOPLANNEDCOMPLETIONDATE` | DATE | 7 | 是 | CONTAINERID->MFGORDERID |
| 49 | `PJ_TYPE` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 50 | `PJ_FUNCTION` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 51 | `PRODUCTNAME` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 52 | `PRODUCTLINENAME` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 53 | `PRODUCTLINENAME_LEF` | VARCHAR2(40) | 40 | 是 | 名称 |
| 54 | `PRODUCTDESC` | VARCHAR2(255) | 255 | 是 | None |
| 55 | `FIRSTNAME` | VARCHAR2(40) | 40 | 是 | CONTAINERID |
| 56 | `WAFERLOTS1` | VARCHAR2(40) | 40 | 是 | None |
| 57 | `WAFERLOT` | VARCHAR2(255) | 255 | 是 | 3個加起來 |
| 58 | `WAFERNAME` | VARCHAR2(255) | 255 | 是 | 3個加起來 |
| 59 | `WAFERDESC` | VARCHAR2(255) | 255 | 是 | 3個加起來 |
| 60 | `NUMBEROFROWS` | NUMBER(10) | 22 | 是 | CONTAINERID->PRODUCTID |
| 61 | `LEADFRAMENAME` | VARCHAR2(1000) | 1000 | 是 | 名称 |
| 62 | `LEADFRAMEDESC` | VARCHAR2(1000) | 1000 | 是 | None |
| 63 | `LEADFRAMEOPTION` | VARCHAR2(1000) | 1000 | 是 | None |
| 64 | `CONSUMEFACTOR` | NUMBER | 22 | 是 | CF |
| 65 | `TXNDATE` | DATE | 7 | 是 | None |
| 66 | `HOLDTIME` | DATE | 7 | 是 | None |

#### 索引

| 索引名 | 类型 | 字段 |
|--------|------|------|
| `DW_MES_WIP_CONTAINERNAME` | 普通索引 | CONTAINERNAME |
| `DW_MES_WIP_TXNDATE` | 普通索引 | TXNDATE |

---

### ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE

**用途**: ERP 報廢原因排除清單 - 控制需排除的報廢原因代碼

**数据量**: 39 行

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `REASON_ID` | NUMBER | 22 | 否 | 唯一标识符 |
| 2 | `REASON_NAME` | VARCHAR2(30) | 30 | 是 | 報廢原因代碼 |
| 3 | `DESCRIPTION` | VARCHAR2(255) | 255 | 是 | 報廢原因說明 |
| 4 | `ENABLE_FLAG` | VARCHAR2(1) | 1 | 是 | 啟用識別 |
| 5 | `CREATION_DATE` | DATE | 7 | 是 | 新增日期 |

---

### ERP_WIP_MOVETXN

**用途**: ERP 工單移轉與報廢明細 - 工單層級移轉/報廢數量事件

**数据量**: 10,748,846 行

**表注释**: 工單移轉與報廢數量明細檔

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `SEQ_ID` | NUMBER | 22 | 否 | 批號，系統日期轉為NUMBER |
| 2 | `WIP_ENTITY_ID` | NUMBER | 22 | 是 | 工單ID |
| 3 | `WIP_ENTITY_NAME` | VARCHAR2(240) | 240 | 是 | 工單號碼 |
| 4 | `WIP_CLASS_CODE` | VARCHAR2(10) | 10 | 是 | 工單類別 |
| 5 | `ITEM_ID` | NUMBER | 22 | 是 | 料號ID |
| 6 | `OPERATION_SEQ_NUM` | NUMBER | 22 | 是 | 作業序號 |
| 7 | `DEPARTMENT_ID` | NUMBER | 22 | 是 | 站別ID |
| 8 | `DEPARTMENT_NAME` | VARCHAR2(10) | 10 | 是 | 站別 |
| 9 | `TRANSACTION_QUANTITY` | NUMBER | 22 | 是 | 移轉數量 |
| 10 | `SCRAP_QUANTITY` | NUMBER | 22 | 是 | 報廢數量 |
| 11 | `UOM` | VARCHAR2(3) | 3 | 是 | 單位 |
| 12 | `LAST_UPDATED_BY` | NUMBER | 22 | 否 | 標準的who columns |
| 13 | `LAST_UPDATE_DATE` | DATE | 7 | 否 | 標準的who columns |
| 14 | `CREATED_BY` | NUMBER | 22 | 否 | 標準的who columns |
| 15 | `CREATION_DATE` | DATE | 7 | 否 | 標準的who columns |
| 16 | `LAST_UPDATE_LOGIN` | NUMBER | 22 | 是 | 標準的who columns |
| 17 | `TXN_DATE` | DATE | 7 | 是 | 異動時間 |
| 18 | `REASON_CODE` | VARCHAR2(30) | 30 | 是 | 報廢代碼 |
| 19 | `REASON_NAME` | VARCHAR2(240) | 240 | 是 | 報廢原因 |
| 20 | `SOURCE_CODE` | VARCHAR2(30) | 30 | 是 | 來源代碼 |

---

### ERP_WIP_MOVETXN_DETAIL

**用途**: ERP 工單站點損耗明細 - 站點/產品維度移轉與報廢明細

**数据量**: 37,543,032 行

**表注释**: 工單各站損耗明細檔

#### 字段列表

| # | 字段名 | 数据类型 | 长度 | 可空 | 说明 |
|---|--------|----------|------|------|------|
| 1 | `SEQ_ID` | NUMBER | 22 | 否 | Sequence |
| 2 | `WIP_ENTITY_NAME` | VARCHAR2(240) | 240 | 是 | 工單號碼 |
| 3 | `WIP_CLASS_CODE` | VARCHAR2(10) | 10 | 是 | 工單類別 |
| 4 | `ASSEMBLY_ITEM_NAME` | VARCHAR2(40) | 40 | 是 | 組裝料號 |
| 5 | `PACKAGE` | VARCHAR2(40) | 40 | 是 | PACKAGE |
| 6 | `FAMILY` | VARCHAR2(40) | 40 | 是 | FAMILY |
| 7 | `TYPE` | VARCHAR2(40) | 40 | 是 | TYPE |
| 8 | `OPERATION_SEQ_NUM` | NUMBER | 22 | 是 | 作業序號 |
| 9 | `DEPARTMENT_ID` | NUMBER | 22 | 是 | 站別ID |
| 10 | `DEPARTMENT_NAME` | VARCHAR2(10) | 10 | 是 | 站別 |
| 11 | `TRANSACTION_QUANTITY` | NUMBER | 22 | 是 | 移轉數量 |
| 12 | `SCRAP_QUANTITY` | NUMBER | 22 | 是 | 報廢數量 |
| 13 | `UOM` | VARCHAR2(3) | 3 | 是 | 單位 |
| 14 | `PROD_RATIO` | NUMBER | 22 | 是 | 製成率 |
| 15 | `DATE_CLOSED` | DATE | 7 | 是 | 工單關閉時間 |
| 16 | `LAST_UPDATED_BY` | NUMBER | 22 | 是 | 標準的who columns |
| 17 | `LAST_UPDATE_DATE` | DATE | 7 | 是 | 標準的who columns |
| 18 | `CREATED_BY` | NUMBER | 22 | 是 | 標準的who columns |
| 19 | `CREATION_DATE` | DATE | 7 | 是 | 標準的who columns |
| 20 | `LAST_UPDATE_LOGIN` | NUMBER | 22 | 是 | 標準的who columns |
| 21 | `FUNCTION` | VARCHAR2(40) | 40 | 是 | FUNCTION |
| 22 | `LINE` | VARCHAR2(40) | 40 | 是 | LINE |
| 23 | `TXN_DATE` | DATE | 7 | 是 | 異動時間 |
| 24 | `REASON_CODE` | VARCHAR2(30) | 30 | 是 | 報廢代碼 |
| 25 | `REASON_NAME` | VARCHAR2(240) | 240 | 是 | 報廢原因 |
| 26 | `SOURCE_CODE` | VARCHAR2(30) | 30 | 是 | 來源代碼 |

---

## 报表开发注意事项

### 性能优化建议

1. **大数据量表查询优化**
   - 以下表数据量较大，查询时务必添加时间范围限制：
     - `DW_MES_WIP`: 84,271,674 行
     - `DW_MES_LOTWIPDATAHISTORY`: 80,316,112 行
     - `DW_MES_RESOURCESTATUS_SHIFT`: 76,947,961 行
     - `DW_MES_RESOURCESTATUS`: 67,681,971 行
     - `DW_MES_MAINTENANCE`: 55,101,182 行
     - `DW_MES_LOTWIPHISTORY`: 54,519,619 行
     - `DW_MES_HM_LOTMOVEOUT`: 49,429,401 行
     - `ERP_WIP_MOVETXN_DETAIL`: 37,543,032 行
     - `DW_MES_LOTMATERIALSHISTORY`: 18,136,445 行
     - `DW_MES_LOTREJECTHISTORY`: 16,103,258 行
     - `ERP_WIP_MOVETXN`: 10,748,846 行

2. **索引使用**
   - 查询时尽量使用已建立索引的字段作为查询条件
   - 避免在索引字段上使用函数，会导致索引失效

3. **连接池配置**
   - 建议使用连接池管理数据库连接
   - 推荐连接池大小：5-10 个连接

4. **查询超时设置**
   - 建议设置查询超时时间为 30-60 秒
   - 避免长时间运行的查询影响系统性能

### 数据时效性

- **实时数据表**: `DW_MES_WIP`（含歷史累積）, `DW_MES_RESOURCESTATUS`
- **历史数据表**: 带有 `HISTORY` 后缀的表
- **主数据表**: `DW_MES_RESOURCE`, `DW_MES_CONTAINER`

### 常用时间字段

大多数历史表包含以下时间相关字段：
- `CREATEDATE` / `CREATETIMESTAMP`: 记录创建时间
- `UPDATEDATE` / `UPDATETIMESTAMP`: 记录更新时间
- `TRANSACTIONDATE`: 交易发生时间

### 数据权限

- 當前帳號為唯讀帳號 (詳見 .env 中的 DB_USER)
- 仅可执行 SELECT 查询
- 无法进行 INSERT, UPDATE, DELETE 操作

---

## 常用查询示例

### 1. 查询当前在制品数量

```sql
SELECT COUNT(*) as WIP_COUNT
FROM DW_MES_WIP
WHERE CURRENTSTATUSID IS NOT NULL;
```

### 2. 查询设备状态统计

```sql
SELECT
    CURRENTSTATUSID,
    COUNT(*) as COUNT
FROM DW_MES_RESOURCESTATUS
GROUP BY CURRENTSTATUSID
ORDER BY COUNT DESC;
```

### 3. 查询最近 7 天的批次历史

```sql
SELECT *
FROM DW_MES_LOTWIPHISTORY
WHERE CREATEDATE >= SYSDATE - 7
ORDER BY CREATEDATE DESC;
```

### 4. 查询工单完成情况

```sql
SELECT
    JOBID,
    JOBSTATUS,
    COUNT(*) as COUNT
FROM DW_MES_JOB
GROUP BY JOBID, JOBSTATUS
ORDER BY JOBID;
```

### 5. 按日期统计生产数量

```sql
SELECT
    TRUNC(CREATEDATE) as PRODUCTION_DATE,
    COUNT(*) as LOT_COUNT
FROM DW_MES_HM_LOTMOVEOUT
WHERE CREATEDATE >= SYSDATE - 30
GROUP BY TRUNC(CREATEDATE)
ORDER BY PRODUCTION_DATE DESC;
```

### 6. 联表查询示例（批次与容器）

```sql
SELECT
    w.LOTID,
    w.CONTAINERNAME,
    c.CURRENTSTATUSID,
    c.CUSTOMERID
FROM DW_MES_WIP w
LEFT JOIN DW_MES_CONTAINER c ON w.CONTAINERID = c.CONTAINERID
WHERE w.CREATEDATE >= SYSDATE - 1
ORDER BY w.CREATEDATE DESC;
```

---

## 附录

### 文档更新记录

- 2026-03-18: 初始版本创建

### 联系方式

如有疑问或需要补充信息，请联系数据库管理员。
