# -*- coding: utf-8 -*-
"""
generate_sample.py
デモ用サンプルデータを生成する（PDFなしでダッシュボード動作確認が可能）
情報エレクトロニクスファンドの実際の傾向を模したリアルな構造のデータ
"""

import os
import sys
import json
import random
import math
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import THEME_KEYWORDS, SIGNAL_KEYWORDS, CANDIDATE_UNIVERSE

random.seed(42)  # 再現性のため

# =============================================================================
# サンプルデータ定義
# =============================================================================

# 銘柄プール（セクターごとに分類）
STOCK_POOL = {
    "半導体製造装置": [
        ("東京エレクトロン", "8035"), ("アドバンテスト", "6857"),
        ("ディスコ", "6146"), ("レーザーテック", "6920"),
        ("SCREEN", "7735"), ("KOKUSAI ELECTRIC", "6525"),
    ],
    "半導体": [
        ("ルネサスエレクトロニクス", "6723"), ("ソシオネクスト", "6526"),
        ("ローム", "6963"),
    ],
    "半導体材料": [
        ("信越化学工業", "4063"), ("SUMCO", "3436"),
        ("東京応化工業", "4186"),
    ],
    "電子部品": [
        ("村田製作所", "6981"), ("TDK", "6762"),
        ("太陽誘電", "6976"), ("京セラ", "6971"),
        ("イビデン", "4062"), ("日東電工", "6988"),
    ],
    "IT・通信": [
        ("NTTデータグループ", "9613"), ("富士通", "6702"),
        ("日本電気", "6701"), ("野村総合研究所", "4307"),
    ],
    "エレクトロニクス": [
        ("ソニーグループ", "6758"), ("日立製作所", "6501"),
        ("キーエンス", "6861"), ("HOYA", "7741"),
    ],
    "ゲーム・コンテンツ": [
        ("任天堂", "7974"), ("カプコン", "9697"),
    ],
    "車載": [
        ("デンソー", "6902"), ("日本電産", "6594"),
    ],
}

# 期間定義
MONTHS = []
for y in range(2022, 2025):
    for m in range(1, 13):
        MONTHS.append(f"{y}-{m:02d}")

# テーマ強度の時系列シナリオ（段階的変化）
THEME_SCENARIOS = {
    "半導体": {
        # 2022: 中程度 → 2023: 上昇 → 2024: 高水準
        "base": 25, "trend": [0, 0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 5,  # 2022
                              6, 7, 8, 9, 10, 10, 10, 11, 12, 12, 12, 13,  # 2023
                              13, 14, 14, 15, 15, 14, 14, 13, 14, 15, 15, 16],  # 2024
    },
    "AI・データセンター": {
        # 2022: 低 → 2023前半: 急上昇（ChatGPTブーム） → 2024: 高水準定着
        "base": 10, "trend": [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3,
                              4, 6, 10, 14, 18, 20, 22, 23, 24, 24, 25, 25,
                              26, 26, 27, 27, 28, 28, 27, 28, 29, 30, 30, 30],
    },
    "通信インフラ": {
        "base": 15, "trend": [0, 0, 0, -1, -1, -1, -2, -2, -2, -2, -3, -3,
                              -3, -3, -4, -4, -3, -3, -2, -2, -1, -1, 0, 0,
                              0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4],
    },
    "車載・電装": {
        "base": 15, "trend": [0, 1, 1, 2, 2, 3, 3, 3, 2, 2, 1, 1,
                              0, 0, -1, -1, -2, -2, -2, -1, -1, 0, 0, 1,
                              1, 2, 2, 3, 3, 4, 4, 5, 5, 5, 6, 6],
    },
    "コンテンツ・エンタメ×テクノロジー": {
        "base": 8, "trend": [0, 0, 1, 1, 1, 2, 2, 1, 1, 0, 0, 1,
                              1, 1, 2, 2, 2, 3, 3, 2, 2, 1, 1, 1,
                              0, 0, 1, 1, 2, 2, 2, 3, 3, 3, 3, 4],
    },
    "セキュリティ・防衛": {
        "base": 5, "trend": [0, 0, 0, 1, 1, 1, 2, 2, 3, 3, 3, 4,
                              4, 4, 5, 5, 5, 5, 5, 6, 6, 6, 6, 7,
                              7, 7, 7, 7, 8, 8, 8, 8, 9, 9, 9, 9],
    },
    "設備投資・FA": {
        "base": 12, "trend": [0, 0, 1, 1, 1, 0, 0, -1, -1, -2, -2, -2,
                              -2, -1, -1, 0, 0, 1, 1, 2, 2, 3, 3, 3,
                              3, 4, 4, 4, 5, 5, 5, 5, 4, 4, 5, 5],
    },
    "電子部品・デバイス": {
        "base": 18, "trend": [0, 0, 0, -1, -1, -2, -2, -3, -3, -3, -2, -2,
                              -1, -1, 0, 0, 1, 1, 2, 2, 2, 3, 3, 3,
                              3, 3, 2, 2, 2, 1, 1, 1, 2, 2, 3, 3],
    },
}

# 運用方針テキストテンプレート
POLICY_TEMPLATES = {
    "semiconductor_high": [
        "半導体関連銘柄について、AI向けの需要拡大が続くことから、引き続き注目していきます。特にAIサーバー向け半導体需要の拡大に伴い、製造装置や材料関連の好調が継続する見通しです。",
        "半導体セクターでは、生成AI向けの先端半導体需要が引き続き旺盛であり、関連銘柄への投資を継続する方針です。特にEUV関連や後工程装置への需要増加に注目しています。",
    ],
    "ai_boom": [
        "AI関連投資は引き続き積極的に行う方針です。データセンター向けGPU需要の拡大、生成AIの企業導入拡大が半導体やネットワーク機器メーカーの成長を牽引すると期待しています。",
        "生成AI市場の急速な拡大を背景に、AIインフラ関連銘柄への投資を強化します。GPUサーバー、高速ネットワーク、冷却装置など、AIインフラを支える企業群に注目しています。",
    ],
    "cautious": [
        "マクロ環境の不透明感が高まる中、銘柄選別を強化し、業績への確信度が高い銘柄に絞り込む方針です。バリュエーションにも注意を払い、慎重に投資判断を行っていきます。",
        "地政学リスクや金利動向を注視しつつ、成長持続性の高い情報エレクトロニクス関連銘柄を選別する方針です。短期的な変動に惑わされず、中長期的な成長テーマに沿った投資を行います。",
    ],
    "ev_focus": [
        "車載半導体やEV関連の需要回復が期待される局面にあり、電動化の進展に伴う需要拡大を見込む銘柄の比率を引き上げる方針です。ADAS・自動運転関連にも注目しています。",
    ],
    "default": [
        "情報エレクトロニクス分野において、中長期的な成長が期待される銘柄を中心に投資を行う方針です。テクノロジーの進化に伴い恩恵を受ける企業を選別していきます。",
    ],
}

ENVIRONMENT_TEMPLATES = [
    "当月の株式市場は、米国の金融政策をめぐる動向や地政学リスクへの懸念が上値を抑える展開となりました。日経平均株価は前月比{change}%となりました。",
    "当月は、米国経済指標の堅調さやAI関連銘柄への期待から、テック関連を中心に上昇基調が継続しました。情報エレクトロニクスセクターは特に堅調な推移となりました。",
    "世界的な半導体需要の回復期待が高まる中、関連銘柄を中心に上昇しました。一方で、景気減速懸念から選別色が強まる展開ともなりました。",
]

REVIEW_TEMPLATES = [
    "当ファンドでは、{action1}を実施しました。{stock1}は{reason1}を背景に堅調な推移となりました。一方、{stock2}については{reason2}の動きが見られ、ポジションを調整しました。",
    "運用面では、{action1}に注力しました。上位銘柄では{stock1}が{reason1}から好調を維持しました。{stock2}は{reason2}の影響を受ける展開でした。",
]


def generate_theme_keywords(month_idx: int) -> dict:
    """月次テーマキーワードを生成"""
    result = {}
    for theme, scenario in THEME_SCENARIOS.items():
        base = scenario["base"]
        trend_val = scenario["trend"][min(month_idx, len(scenario["trend"]) - 1)]
        score = max(0, base + trend_val + random.randint(-3, 3))
        
        # THEME_KEYWORDS からキーワードをランダム選択
        kws = THEME_KEYWORDS.get(theme, [])
        n_found = min(score // 5 + 1, len(kws))
        found = random.sample(kws, min(n_found, len(kws))) if kws else []
        
        result[theme] = {
            "count": score,
            "found_keywords": found,
        }
    return result


def generate_holdings(month_idx: int) -> list:
    """
    月次上位10銘柄を生成（現実的な変動パターン）
    """
    # 基本的な上位銘柄（安定株）
    stable_stocks = [
        ("東京エレクトロン", "半導体製造装置"),
        ("アドバンテスト", "半導体製造装置"),
        ("信越化学工業", "半導体材料"),
        ("ソニーグループ", "エレクトロニクス"),
        ("キーエンス", "FA"),
        ("村田製作所", "電子部品"),
        ("日立製作所", "エレクトロニクス"),
    ]
    
    # 時期によって入る銘柄
    rotation_stocks = {
        (0, 12): [  # 2022
            ("レーザーテック", "半導体製造装置"),
            ("デンソー", "車載"),
            ("ローム", "半導体"),
            ("TDK", "電子部品"),
        ],
        (12, 24): [  # 2023 (AI ブーム)
            ("ディスコ", "半導体製造装置"),
            ("ルネサスエレクトロニクス", "半導体"),
            ("HOYA", "光学"),
            ("富士通", "IT・通信"),
            ("ソシオネクスト", "半導体"),
        ],
        (24, 36): [  # 2024
            ("ディスコ", "半導体製造装置"),
            ("SCREEN", "半導体製造装置"),
            ("NTTデータグループ", "IT・通信"),
            ("イビデン", "電子部品"),
            ("野村総合研究所", "IT・通信"),
        ],
    }
    
    # このperiodのrotation stockを選択
    period_stocks = []
    for (start, end), stocks in rotation_stocks.items():
        if start <= month_idx < end:
            period_stocks = stocks
            break
    
    # 10銘柄を構成
    holdings = []
    all_candidates = stable_stocks + period_stocks
    
    # ランダムに1-2銘柄のゆらぎ
    random.shuffle(all_candidates)
    selected = all_candidates[:10]
    
    # 上位は安定株が来やすい
    selected.sort(key=lambda x: (
        0 if x in stable_stocks[:3] else
        1 if x in stable_stocks[3:] else
        2
    ))
    
    for i, (name, sector) in enumerate(selected):
        weight = round(max(2.0, 12.0 - i * 1.0 + random.uniform(-0.5, 0.5)), 1)
        holdings.append({
            "rank": i + 1,
            "name": name,
            "weight": str(weight),
            "sector": sector,
        })
    
    return holdings


def generate_sections(month_idx: int, holdings: list) -> dict:
    """運用テキストセクションを生成"""
    # テーマ強度から方針テンプレートを選択
    ai_strength = THEME_SCENARIOS["AI・データセンター"]["trend"][min(month_idx, 35)]
    semi_strength = THEME_SCENARIOS["半導体"]["trend"][min(month_idx, 35)]
    ev_strength = THEME_SCENARIOS["車載・電装"]["trend"][min(month_idx, 35)]
    
    # 投資環境
    change = round(random.uniform(-5, 8), 1)
    env = random.choice(ENVIRONMENT_TEMPLATES).format(change=change)
    
    # 運用経過
    stock1 = holdings[0]["name"] if holdings else "東京エレクトロン"
    stock2 = holdings[-1]["name"] if holdings else "村田製作所"
    actions = ["半導体関連銘柄の比率引き上げ", "AI関連銘柄への新規投資",
               "ポートフォリオの銘柄入れ替え", "電子部品セクターのリバランス"]
    reasons1 = ["AI向け需要の拡大", "堅調な業績", "構造改革の進展", "海外展開の加速"]
    reasons2 = ["バリュエーション調整", "業績の一時的な減速", "セクターローテーション",
                "利益確定売り"]
    
    review = random.choice(REVIEW_TEMPLATES).format(
        action1=random.choice(actions),
        stock1=stock1, reason1=random.choice(reasons1),
        stock2=stock2, reason2=random.choice(reasons2),
    )
    
    # 今後の運用方針
    if ai_strength > 15:
        policy = random.choice(POLICY_TEMPLATES["ai_boom"])
    elif semi_strength > 10:
        policy = random.choice(POLICY_TEMPLATES["semiconductor_high"])
    elif ev_strength > 3:
        policy = random.choice(POLICY_TEMPLATES["ev_focus"])
    elif random.random() < 0.3:
        policy = random.choice(POLICY_TEMPLATES["cautious"])
    else:
        policy = random.choice(POLICY_TEMPLATES["default"])
    
    return {
        "investment_environment": env,
        "operation_review": review,
        "future_policy": policy,
    }


def generate_signals(month_idx: int) -> dict:
    """売買シグナルを生成"""
    pos = random.sample(SIGNAL_KEYWORDS["positive"], random.randint(2, 5))
    cau = random.sample(SIGNAL_KEYWORDS["cautious"], random.randint(1, 3))
    return {
        "positive": pos,
        "cautious": cau,
    }


def generate_performance(month_idx: int) -> dict:
    """パフォーマンス情報を生成"""
    base_nav = 15000
    # 右肩上がり基調 + ノイズ
    nav = int(base_nav + month_idx * 200 + random.randint(-500, 800))
    monthly_return = round(random.uniform(-5, 8), 1)
    
    return {
        "monthly_return": str(monthly_return),
        "nav": str(nav),
        "benchmark_info": "参考指数: TOPIX（配当込み）",
    }


def generate_sample_data():
    """サンプルデータ生成メイン"""
    data_dir = PROJECT_ROOT / "data"
    os.makedirs(data_dir, exist_ok=True)
    
    reports = []
    
    for i, month in enumerate(MONTHS):
        year, mon = month.split("-")
        
        holdings = generate_holdings(i)
        sections = generate_sections(i, holdings)
        
        report = {
            "source_file": f"{year}{mon}_monthly_report.pdf",
            "report_month": month,
            "meta": {
                "report_date": f"{year}-{mon}-15",
                "nav_date": f"{year}-{mon}-{28 if int(mon) != 2 else 27}",
            },
            "sections": sections,
            "theme_keywords": generate_theme_keywords(i),
            "signals": generate_signals(i),
            "holdings": holdings,
            "performance": generate_performance(i),
            "quality": {
                "extraction_success": True,
                "issues": [] if random.random() > 0.1 else ["一部テーブル抽出精度低"],
                "extracted_fields": [
                    "nav_date", "report_date",
                    "investment_environment", "operation_review", "future_policy",
                    "holdings", "nav", "monthly_return",
                ],
                "missing_fields": [],
            },
        }
        reports.append(report)
    
    output = {
        "fund_name": "情報エレクトロニクスファンド",
        "management_company": "野村アセットマネジメント",
        "extracted_at": datetime.now().isoformat(),
        "total_reports": len(reports),
        "reports": reports,
    }
    
    output_path = data_dir / "reports_data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"=== サンプルデータ生成完了 ===")
    print(f"出力: {output_path}")
    print(f"期間: {MONTHS[0]} ～ {MONTHS[-1]} ({len(MONTHS)}ヶ月)")
    print(f"テーマ数: {len(THEME_SCENARIOS)}")


if __name__ == "__main__":
    generate_sample_data()
