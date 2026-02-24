# -*- coding: utf-8 -*-
"""
extract_reports.py
月報PDFからテキスト・テーブル・メタ情報を抽出し、JSON形式で保存する
"""

import os
import sys
import re
import json
import glob
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber が必要です。pip install pdfplumber を実行してください。")
    sys.exit(1)

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import (
    SECTION_PATTERNS,
    THEME_KEYWORDS,
    SIGNAL_KEYWORDS,
    NORMALIZATION_RULES,
)


# =============================================================================
# ユーティリティ関数
# =============================================================================

def normalize_text(text: str) -> str:
    """テキストの正規化（全角→半角、余分な空白除去）"""
    if not text:
        return ""
    # NFKC正規化（全角英数→半角、半角カナ→全角）
    text = unicodedata.normalize("NFKC", text)
    # 行単位で処理し、行内の連続空白を1つに
    lines = text.split("\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    text = "\n".join(lines)
    return text


def normalize_stock_name(name: str) -> str:
    """銘柄名の正規化"""
    if not name:
        return ""
    name = normalize_text(name)
    # 除去パターン
    for pattern in NORMALIZATION_RULES["remove_patterns"]:
        name = re.sub(pattern, "", name)
    name = name.strip()
    # エイリアス辞書
    aliases = NORMALIZATION_RULES.get("aliases", {})
    if name in aliases:
        name = aliases[name]
    return name


def extract_date_from_filename(filename: str) -> str:
    """
    ファイル名から年月を推定する
    対応パターン: 202301, 2023-01, 2023_01, 2023年1月 など
    """
    basename = os.path.splitext(os.path.basename(filename))[0]
    # パターン1: YYYYMM or YYYY-MM or YYYY_MM
    match = re.search(r"(20\d{2})[-_]?(\d{2})", basename)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    # パターン2: YYYY年M月 or YYYY年MM月
    match = re.search(r"(20\d{2})年(\d{1,2})月", basename)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    return ""


def extract_date_from_text(text: str) -> dict:
    """テキストからメタ日付情報を抽出"""
    result = {
        "report_date": "",
        "nav_date": "",
    }
    # 基準価額日: 「2023年12月29日現在」等
    match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*現在", text)
    if match:
        result["nav_date"] = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    # 作成日: 「作成基準日 2024年1月10日」等
    match = re.search(r"作成.*?(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
    if match:
        result["report_date"] = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return result


# =============================================================================
# セクション分割
# =============================================================================

def identify_sections(text: str) -> dict:
    """
    テキストをセクションに分割する
    各セクションの開始位置を検出し、セクション間のテキストを抽出
    """
    sections = {}
    positions = []

    for section_key, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                positions.append((match.start(), section_key))
                break

    # 位置順にソート
    positions.sort(key=lambda x: x[0])

    # 各セクションのテキストを抽出
    for i, (pos, key) in enumerate(positions):
        if i + 1 < len(positions):
            end_pos = positions[i + 1][0]
        else:
            end_pos = len(text)
        section_text = text[pos:end_pos].strip()
        # セクション見出し行を除去
        lines = section_text.split("\n")
        if len(lines) > 1:
            section_text = "\n".join(lines[1:]).strip()
        sections[key] = section_text

    return sections


# =============================================================================
# キーワード抽出
# =============================================================================

def extract_keywords(text: str) -> dict:
    """テーマキーワードの出現頻度を計算"""
    result = {}
    for theme, keywords in THEME_KEYWORDS.items():
        count = 0
        found = []
        for kw in keywords:
            c = text.count(kw)
            if c > 0:
                count += c
                found.append(kw)
        result[theme] = {
            "count": count,
            "found_keywords": found,
        }
    return result


def extract_signals(text: str) -> dict:
    """売買シグナルキーワードの抽出"""
    result = {}
    for signal_type, keywords in SIGNAL_KEYWORDS.items():
        found = []
        for kw in keywords:
            if kw in text:
                found.append(kw)
        result[signal_type] = found
    return result


# =============================================================================
# テーブル抽出 (組入上位銘柄)
# =============================================================================

def extract_holdings_table(pdf) -> list:
    """
    pdfplumberのテーブル検出を使い、組入上位銘柄テーブルを抽出
    """
    holdings = []

    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if not table or len(table) < 2:
                continue
            # ヘッダー行で「銘柄」を含むテーブルを探す
            header = [str(cell).strip() if cell else "" for cell in table[0]]
            header_text = "".join(header)

            is_holdings_table = any(
                kw in header_text for kw in ["銘柄", "組入", "上位"]
            )

            if not is_holdings_table:
                # 2行目もチェック（ヘッダーが2行にまたがる場合）
                if len(table) > 1:
                    row2 = [str(cell).strip() if cell else "" for cell in table[1]]
                    row2_text = "".join(row2)
                    is_holdings_table = any(
                        kw in row2_text for kw in ["銘柄", "組入", "上位"]
                    )
                    if is_holdings_table:
                        table = table[1:]  # ヘッダー行を調整

            if is_holdings_table:
                for i, row in enumerate(table[1:], 1):
                    cells = [str(cell).strip() if cell else "" for cell in row]
                    if not any(cells):
                        continue

                    holding = {
                        "rank": i,
                        "name": "",
                        "weight": "",
                        "sector": "",
                    }

                    # 銘柄名を探す（日本語が含まれるセル、30文字以下）
                    for cell in cells:
                        if re.search(r"[\u3040-\u9fff]", cell) and 1 < len(cell) <= 30:
                            holding["name"] = normalize_stock_name(cell)
                            break

                    # 比率を探す（%を含むセル）
                    for cell in cells:
                        if "%" in cell or re.search(r"\d+\.\d+", cell):
                            holding["weight"] = cell.replace("%", "").strip()
                            break

                    if holding["name"]:
                        holdings.append(holding)

    # 最大10銘柄
    return holdings[:10]


def extract_holdings_from_text(text: str) -> list:
    """
    テキストから組入上位銘柄を抽出する
    実際のPDFでは「銘柄名 業種 市場 比率%」形式の行が並ぶ
    """
    holdings = []
    
    # パターン1: 「銘柄名 業種 東証プライム/スタンダード 8.0%」
    #   例: 古河電気工業 非鉄金属 東証プライム 8.0%
    pattern1 = re.compile(
        r'^([\u3040-\u9fffA-Za-z\s・ー]+?)\s+'
        r'([\u3040-\u9fff・]+)\s+'
        r'(東証[\u3040-\u9fff]+)\s+'
        r'(\d+\.\d+)\s*%',
        re.MULTILINE
    )
    
    for m in pattern1.finditer(text):
        name = normalize_stock_name(m.group(1).strip())
        if name and len(name) > 1:
            holdings.append({
                "rank": len(holdings) + 1,
                "name": name,
                "weight": m.group(4),
                "sector": m.group(2).strip(),
            })
    
    # パターン2: 数字で始まる「1 古河電気工業 ...」
    if not holdings:
        pattern2 = re.compile(
            r'(\d{1,2})\s+([\u3040-\u9fffA-Za-z\s・ー]+?)\s+'
            r'(?:[\u3040-\u9fff・]+\s+)?'
            r'(?:東証[\u3040-\u9fff]+\s+)?'
            r'(\d+\.\d+)\s*%?',
            re.MULTILINE
        )
        for m in pattern2.finditer(text):
            name = normalize_stock_name(m.group(2).strip())
            if name and len(name) > 1:
                holdings.append({
                    "rank": int(m.group(1)),
                    "name": name,
                    "weight": m.group(3),
                    "sector": "",
                })

    # パターン3: 解説文内の「N 銘柄名」形式
    #   例: 1 古河電気工業
    if not holdings:
        pattern3 = re.compile(
            r'^(\d{1,2})\s+([\u3040-\u9fffA-Za-z・ー]{2,20})\s',
            re.MULTILINE
        )
        for m in pattern3.finditer(text):
            name = normalize_stock_name(m.group(2).strip())
            if name and len(name) > 1:
                existing_names = [h["name"] for h in holdings]
                if name not in existing_names:
                    holdings.append({
                        "rank": int(m.group(1)),
                        "name": name,
                        "weight": "",
                        "sector": "",
                    })
    
    return holdings[:10]


# =============================================================================
# パフォーマンス抽出
# =============================================================================

def extract_performance(text: str) -> dict:
    """月次騰落率など定量情報を抽出"""
    result = {
        "monthly_return": "",
        "nav": "",
        "benchmark_info": "",
    }

    # 基準価額: 「基準価額 12,345円」
    match = re.search(r"基準価額\s*[：:]*\s*([\d,]+)\s*円", text)
    if match:
        result["nav"] = match.group(1).replace(",", "")

    # 月次騰落率: 「騰落率 +3.5%」
    match = re.search(r"騰落率\s*[：:]*\s*([+\-−]?\d+\.?\d*)%?", text)
    if match:
        result["monthly_return"] = match.group(1)

    # ベンチマーク記載
    bm_keywords = ["ベンチマーク", "参考指数", "TOPIX", "日経平均"]
    for kw in bm_keywords:
        if kw in text:
            # キーワード周辺のテキストを抽出
            idx = text.index(kw)
            start = max(0, idx - 20)
            end = min(len(text), idx + 100)
            snippet = text[start:end].replace("\n", " ").strip()
            result["benchmark_info"] = snippet
            break

    return result


# =============================================================================
# メインパイプライン
# =============================================================================

def process_single_pdf(filepath: str) -> dict:
    """
    1つのPDFファイルを処理して構造化データを返す
    """
    result = {
        "source_file": os.path.basename(filepath),
        "report_month": "",
        "meta": {
            "report_date": "",
            "nav_date": "",
        },
        "sections": {
            "manager_comment": "",
            "investment_environment": "",
            "operation_review": "",
            "future_policy": "",
            "holdings_description": "",
        },
        "theme_keywords": {},
        "signals": {},
        "holdings": [],
        "performance": {},
        "quality": {
            "extraction_success": True,
            "issues": [],
            "extracted_fields": [],
            "missing_fields": [],
        },
    }

    # ファイル名から年月推定
    result["report_month"] = extract_date_from_filename(filepath)

    try:
        with pdfplumber.open(filepath) as pdf:
            # 全ページのテキストを結合（改行を維持）
            full_text = ""
            page_texts = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    page_texts.append(page_text)
                    full_text += page_text + "\n"

            if not full_text.strip():
                result["quality"]["extraction_success"] = False
                result["quality"]["issues"].append("テキスト抽出不可（画像PDFの可能性）")
                return result

            full_text_norm = normalize_text(full_text)

            # メタ日付
            dates = extract_date_from_text(full_text_norm)
            result["meta"].update(dates)
            if dates["nav_date"]:
                result["quality"]["extracted_fields"].append("nav_date")
            else:
                result["quality"]["missing_fields"].append("nav_date")

            # セクション分割
            sections = identify_sections(full_text_norm)
            section_keys = ["manager_comment", "investment_environment",
                          "operation_review", "future_policy", "holdings_description"]
            for key in section_keys:
                if key in sections:
                    result["sections"][key] = sections[key]
                    result["quality"]["extracted_fields"].append(key)
                else:
                    result["quality"]["missing_fields"].append(key)

            # テーマキーワード（方針 + 経過 + マネージャーコメント + 解説文を結合）
            analysis_text = " ".join([
                sections.get("future_policy", ""),
                sections.get("operation_review", ""),
                sections.get("manager_comment", ""),
                sections.get("holdings_description", ""),
            ])
            result["theme_keywords"] = extract_keywords(analysis_text)

            # 売買シグナル
            result["signals"] = extract_signals(analysis_text)

            # 組入上位銘柄（テーブル抽出 → テキストフォールバック）
            holdings = extract_holdings_table(pdf)
            
            if not holdings or len(holdings) < 5:
                # テキストベースフォールバック: 全ページテキストから抽出
                text_holdings = extract_holdings_from_text(full_text_norm)
                if len(text_holdings) > len(holdings):
                    holdings = text_holdings
                    if holdings:
                        result["quality"]["issues"].append("銘柄テーブル抽出はテキストフォールバックを使用")

            if holdings:
                result["holdings"] = holdings
                result["quality"]["extracted_fields"].append("holdings")
            else:
                result["quality"]["missing_fields"].append("holdings")
                result["quality"]["issues"].append("組入銘柄の抽出に失敗")

            # パフォーマンス
            perf = extract_performance(full_text_norm)
            result["performance"] = perf
            if perf["nav"]:
                result["quality"]["extracted_fields"].append("nav")
            if perf["monthly_return"]:
                result["quality"]["extracted_fields"].append("monthly_return")

    except Exception as e:
        result["quality"]["extraction_success"] = False
        result["quality"]["issues"].append(f"PDF処理エラー: {str(e)}")

    return result


def run_extraction():
    """
    reports/ フォルダの全PDFを処理し、JSONに出力する
    """
    reports_dir = PROJECT_ROOT / "reports"
    output_dir = PROJECT_ROOT / "data"

    # ディレクトリ作成
    os.makedirs(reports_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # PDF一覧取得 (latestは除外 - 最新月と重複するため)
    pdf_files = sorted([
        f for f in glob.glob(str(reports_dir / "*.pdf"))
        if "latest" not in os.path.basename(f).lower()
    ])

    if not pdf_files:
        print(f"警告: {reports_dir} にPDFファイルが見つかりません。")
        print("月報PDFを reports/ フォルダに配置してから再実行してください。")
        print("ファイル名は年月が分かる形式にしてください（例: 202301.pdf, 2023-01_月報.pdf）")
        return

    print(f"=== 月報PDF抽出パイプライン ===")
    print(f"対象: {len(pdf_files)} ファイル")
    print()

    all_reports = []

    for filepath in pdf_files:
        filename = os.path.basename(filepath)
        print(f"処理中: {filename} ... ", end="", flush=True)

        report = process_single_pdf(filepath)
        all_reports.append(report)

        if report["quality"]["extraction_success"]:
            n_fields = len(report["quality"]["extracted_fields"])
            n_holdings = len(report["holdings"])
            print(f"OK (抽出フィールド: {n_fields}, 銘柄数: {n_holdings})")
        else:
            print(f"WARN: {', '.join(report['quality']['issues'])}")

    # 年月順にソート
    all_reports.sort(key=lambda x: x["report_month"])

    # JSON出力
    output_path = output_dir / "reports_data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "fund_name": "情報エレクトロニクスファンド",
                "management_company": "野村アセットマネジメント",
                "extracted_at": datetime.now().isoformat(),
                "total_reports": len(all_reports),
                "reports": all_reports,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(f"=== 完了 ===")
    print(f"出力: {output_path}")
    print(f"総レポート数: {len(all_reports)}")

    # 品質サマリー
    success_count = sum(1 for r in all_reports if r["quality"]["extraction_success"])
    print(f"抽出成功: {success_count}/{len(all_reports)}")


if __name__ == "__main__":
    run_extraction()
