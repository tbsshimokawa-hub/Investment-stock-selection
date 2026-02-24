# -*- coding: utf-8 -*-
"""
download_reports.py
野村アセットマネジメントのサイトから月報PDFをダウンロードする
"""

import os
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
os.makedirs(REPORTS_DIR, exist_ok=True)

BASE_URL = "https://www.nomura-am.co.jp/special/japanequity/fukudacpm/140012m-report/M1140012_{ym}.pdf"
LATEST_URL = "https://www.nomura-am.co.jp/fund/monthly1/M1140012.pdf"

# 2020-01 ~ 2025-12
months = []
for year in range(2020, 2026):
    for month in range(1, 13):
        months.append(f"{year}{month:02d}")

# ヘッダー（User-Agent設定）
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

downloaded = 0
skipped = 0
failed = 0

print(f"=== 月報PDFダウンロード ===")
print(f"対象: {len(months)} ファイル + 最新版")
print(f"保存先: {REPORTS_DIR}")
print()

for ym in months:
    filename = f"M1140012_{ym}.pdf"
    filepath = REPORTS_DIR / filename
    
    if filepath.exists():
        skipped += 1
        continue
    
    url = BASE_URL.format(ym=ym)
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            with open(filepath, "wb") as f:
                f.write(data)
            size_kb = len(data) / 1024
            print(f"  OK: {filename} ({size_kb:.0f} KB)")
            downloaded += 1
    except Exception as e:
        err_msg = str(e)
        if "404" in err_msg or "Not Found" in err_msg:
            print(f"  SKIP (not found): {filename}")
        else:
            print(f"  FAIL: {filename} - {err_msg}")
            failed += 1
    
    # サーバーに負荷をかけないよう少し待つ
    time.sleep(0.5)

# 最新版もダウンロード
latest_path = REPORTS_DIR / "M1140012_latest.pdf"
if not latest_path.exists():
    try:
        req = urllib.request.Request(LATEST_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            with open(latest_path, "wb") as f:
                f.write(data)
            print(f"  OK: M1140012_latest.pdf ({len(data)/1024:.0f} KB)")
            downloaded += 1
    except Exception as e:
        print(f"  FAIL: latest - {e}")
        failed += 1

print()
print(f"=== 完了 ===")
print(f"ダウンロード: {downloaded}, スキップ(既存): {skipped}, 失敗: {failed}")
