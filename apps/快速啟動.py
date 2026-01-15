"""
快速啟動腳本 - 可以直接用 Python 運行
使用方法: python apps\快速啟動.py
"""

import sys
import os

# 檢查依賴
try:
    import flask
    import pandas
    import oracledb
    print("✓ 所有依賴已安裝")
except ImportError as e:
    print(f"[錯誤] 缺少依賴: {e}")
    print("\n請先執行以下命令安裝依賴:")
    print("  pip install flask pandas oracledb")
    print("\n或者運行: scripts\\0_初始化環境.bat")
    sys.exit(1)

# 啟動應用
print("\n正在啟動 MES 報表入口...")
print("請訪問: http://localhost:5000")
print("按 Ctrl+C 停止服務器\n")

# 導入並運行
from portal import app
app.run(debug=True, host='0.0.0.0', port=5000)
