# -*- coding: utf-8 -*-
"""
analyze.py
テーマ強度分析・銘柄選定傾向分析・候補推定・バックテストを実行
"""

import os
import sys
import json
import math
import re
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import (
    THEME_KEYWORDS, SIGNAL_KEYWORDS, EVALUATION_ASPECTS,
    CANDIDATE_UNIVERSE, SCORE_WEIGHTS, BACKTEST_CONFIG,
)

# =============================================================================
# テーマ強度分析
# =============================================================================

def compute_theme_intensity(reports: list) -> list:
    """
    月次テーマ強度を算出
    各テーマのキーワード出現数を正規化してスコア化
    """
    results = []
    for report in reports:
        month = report.get("report_month", "")
        kw_data = report.get("theme_keywords", {})
        
        theme_scores = {}
        total_keywords = sum(
            d.get("count", 0) for d in kw_data.values()
        )
        # ゼロ除算防止
        if total_keywords == 0:
            total_keywords = 1
            
        for theme, data in kw_data.items():
            count = data.get("count", 0)
            # 正規化スコア (0-100)
            raw = count / total_keywords * 100
            theme_scores[theme] = round(raw, 2)
        
        results.append({
            "month": month,
            "scores": theme_scores,
            "total_keywords": total_keywords,
        })
    
    return results


def compute_theme_trend(theme_intensity: list, window: int = 3) -> dict:
    """
    テーマの強まり/弱まり （移動平均の差分）を計算
    """
    themes = set()
    for item in theme_intensity:
        themes.update(item["scores"].keys())
    
    trends = {}
    for theme in themes:
        values = [item["scores"].get(theme, 0) for item in theme_intensity]
        months = [item["month"] for item in theme_intensity]
        
        # 移動平均
        ma = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            ma.append(sum(values[start:i+1]) / (i - start + 1))
        
        # 差分（強まり/弱まり）
        deltas = [0] + [ma[i] - ma[i-1] for i in range(1, len(ma))]
        
        trend_data = []
        for i, month in enumerate(months):
            trend_data.append({
                "month": month,
                "value": round(values[i], 2),
                "ma": round(ma[i], 2),
                "delta": round(deltas[i], 2),
                "direction": "up" if deltas[i] > 0.5 else ("down" if deltas[i] < -0.5 else "stable"),
            })
        trends[theme] = trend_data
    
    return trends


# =============================================================================
# 銘柄選定傾向分析
# =============================================================================

def analyze_holdings_history(reports: list) -> dict:
    """
    上位銘柄の登場履歴・継続期間・順位変動を分析
    """
    # 銘柄ごとの登場履歴
    stock_history = defaultdict(list)
    
    for report in reports:
        month = report.get("report_month", "")
        holdings = report.get("holdings", [])
        for h in holdings:
            name = h.get("name", "")
            if name:
                stock_history[name].append({
                    "month": month,
                    "rank": h.get("rank", 0),
                    "weight": h.get("weight", ""),
                })
    
    # 各銘柄の分析
    analysis = {}
    total_months = len(reports)
    
    for name, history in stock_history.items():
        months_present = len(history)
        ranks = [h["rank"] for h in history]
        
        # 連続登場月数（直近）
        all_months = [r.get("report_month", "") for r in reports]
        present_months = set(h["month"] for h in history)
        
        consecutive = 0
        for m in reversed(all_months):
            if m in present_months:
                consecutive += 1
            else:
                break
        
        # 順位変動
        rank_changes = []
        for i in range(1, len(history)):
            rank_changes.append(history[i]["rank"] - history[i-1]["rank"])
        
        analysis[name] = {
            "total_appearances": months_present,
            "appearance_rate": round(months_present / max(total_months, 1) * 100, 1),
            "avg_rank": round(sum(ranks) / len(ranks), 1),
            "best_rank": min(ranks),
            "consecutive_months": consecutive,
            "history": history,
            "rank_volatility": round(
                sum(abs(rc) for rc in rank_changes) / max(len(rank_changes), 1), 2
            ),
        }
    
    return analysis


def detect_holding_changes(reports: list) -> list:
    """
    月ごとの新規登場・除外・順位変動を検出
    """
    changes = []
    
    for i in range(len(reports)):
        month = reports[i].get("report_month", "")
        current = {h["name"]: h["rank"] for h in reports[i].get("holdings", []) if h.get("name")}
        
        if i == 0:
            changes.append({
                "month": month,
                "new_entries": list(current.keys()),
                "removed": [],
                "rank_up": [],
                "rank_down": [],
            })
            continue
        
        previous = {h["name"]: h["rank"] for h in reports[i-1].get("holdings", []) if h.get("name")}
        
        new_entries = [n for n in current if n not in previous]
        removed = [n for n in previous if n not in current]
        
        rank_up = []
        rank_down = []
        for name in current:
            if name in previous:
                diff = previous[name] - current[name]  # 順位は小さいほど上位
                if diff > 0:
                    rank_up.append({"name": name, "change": diff})
                elif diff < 0:
                    rank_down.append({"name": name, "change": diff})
        
        changes.append({
            "month": month,
            "new_entries": new_entries,
            "removed": removed,
            "rank_up": rank_up,
            "rank_down": rank_down,
        })
    
    return changes


# =============================================================================
# 銘柄評価観点スコア
# =============================================================================

def compute_aspect_scores(reports: list) -> dict:
    """
    各銘柄について、解説文から評価観点スコアを算出
    （ファンドがどの観点で評価しているか）
    """
    # 全レポートの運用方針テキストを銘柄ごとに結合
    stock_texts = defaultdict(str)
    for report in reports:
        policy = report.get("sections", {}).get("future_policy", "")
        review = report.get("sections", {}).get("operation_review", "")
        combined = policy + " " + review
        
        # 銘柄名が言及されているコンテキストを抽出
        for h in report.get("holdings", []):
            name = h.get("name", "")
            if name:
                stock_texts[name] += " " + combined
    
    # 評価観点スコア
    aspect_scores = {}
    for name, text in stock_texts.items():
        scores = {}
        for aspect, keywords in EVALUATION_ASPECTS.items():
            count = sum(text.count(kw) for kw in keywords)
            scores[aspect] = count
        
        # 正規化 (0-1)
        max_score = max(scores.values()) if scores.values() else 1
        if max_score > 0:
            scores = {k: round(v / max_score, 2) for k, v in scores.items()}
        
        aspect_scores[name] = scores
    
    return aspect_scores


# =============================================================================
# 候補銘柄推定（説明可能スコアリング）
# =============================================================================

def estimate_candidates(
    reports: list,
    cutoff_idx: int,
    theme_trends: dict,
    holdings_analysis: dict,
    holding_changes: list,
) -> list:
    """
    cutoff_idx までのデータを使い、次月の候補銘柄を推定
    データリーク防止: cutoff_idx+1 以降のデータは一切使わない
    
    Returns:
        list of candidate dicts with scores and explanations
    """
    if cutoff_idx < 0 or cutoff_idx >= len(reports):
        return []
    
    # cutoffまでのデータのみ使用
    train_reports = reports[:cutoff_idx + 1]
    latest = train_reports[-1]
    latest_month = latest.get("report_month", "")
    
    # 現在の上位銘柄
    current_holdings = {h["name"] for h in latest.get("holdings", []) if h.get("name")}
    
    # --- テーマ一致度の算出 ---
    latest_themes = {}
    for theme, trend_data in theme_trends.items():
        for td in trend_data:
            if td["month"] == latest_month:
                latest_themes[theme] = td["value"]
                break
    
    # --- 過去出現銘柄の収集（Cutoffまで）---
    past_stocks = set()
    stock_appearances = Counter()
    for r in train_reports:
        for h in r.get("holdings", []):
            name = h.get("name", "")
            if name:
                past_stocks.add(name)
                stock_appearances[name] += 1
    
    # --- 候補ユニバース構築 ---
    candidates = set()
    # Option A: 過去出現銘柄
    candidates.update(past_stocks)
    # Option C: 事前定義リスト
    for c in CANDIDATE_UNIVERSE:
        candidates.add(c["name"])
    
    # 現在の上位から除外（既に組入済みの銘柄は「新規候補」ではない）
    # ただし、順位上昇候補としては含める
    candidates_list = sorted(candidates)
    
    # --- 各候補のスコアリング ---
    results = []
    
    for cand_name in candidates_list:
        score_components = {}
        explanations = []
        
        # 1. テーマ一致度 (0-1)
        theme_score = 0
        theme_matches = []
        # 候補のセクターを取得
        cand_sectors = []
        for c in CANDIDATE_UNIVERSE:
            if c["name"] == cand_name:
                cand_sectors.append(c["sector"])
        
        # 候補名・セクターがテーマキーワードに含まれるか
        for theme, keywords_list in THEME_KEYWORDS.items():
            theme_val = latest_themes.get(theme, 0)
            for kw in keywords_list:
                if kw in cand_name or any(kw in s for s in cand_sectors):
                    theme_score += theme_val / 100
                    theme_matches.append(theme)
                    break
        
        theme_score = min(theme_score, 1.0)
        score_components["theme_match"] = round(theme_score, 3)
        if theme_matches:
            explanations.append(f"テーマ一致: {', '.join(set(theme_matches))}")
        
        # 2. 過去採用頻度 (0-1)
        total_months = len(train_reports)
        freq = stock_appearances.get(cand_name, 0) / max(total_months, 1)
        # 再登場ボーナス（過去にいたが直近はいない）
        if cand_name in past_stocks and cand_name not in current_holdings:
            freq *= 1.3  # 再登場傾向ボーナス
            explanations.append(f"過去{stock_appearances.get(cand_name, 0)}回採用（再登場候補）")
        elif cand_name in past_stocks:
            explanations.append(f"過去{stock_appearances.get(cand_name, 0)}回採用")
        
        score_components["past_frequency"] = round(min(freq, 1.0), 3)
        
        # 3. 解説文特徴との類似度 (0-1)
        desc_score = 0
        policy_text = latest.get("sections", {}).get("future_policy", "")
        for aspect, keywords in EVALUATION_ASPECTS.items():
            for kw in keywords:
                if kw in cand_name or any(kw in s for s in cand_sectors):
                    # 方針文中にそのキーワードが出現
                    if kw in policy_text:
                        desc_score += 0.2
                        break
        
        desc_score = min(desc_score, 1.0)
        score_components["description_sim"] = round(desc_score, 3)
        if desc_score > 0.3:
            explanations.append("運用方針テキストとの特徴類似度が高い")
        
        # 4. 業種配分変化方向 (0-1)
        sector_score = 0
        if len(train_reports) >= 2:
            prev_sectors = Counter()
            curr_sectors = Counter()
            for h in train_reports[-2].get("holdings", []):
                s = h.get("sector", "その他")
                if s:
                    prev_sectors[s] += 1
            for h in latest.get("holdings", []):
                s = h.get("sector", "その他")
                if s:
                    curr_sectors[s] += 1
            
            for s in cand_sectors:
                if curr_sectors.get(s, 0) > prev_sectors.get(s, 0):
                    sector_score = 0.7
                    explanations.append(f"業種「{s}」の配分増加傾向")
                    break
                elif curr_sectors.get(s, 0) == prev_sectors.get(s, 0) and curr_sectors.get(s, 0) > 0:
                    sector_score = 0.4
                    break
        
        score_components["sector_trend"] = round(sector_score, 3)
        
        # 5. 売買示唆文との整合 (0-1)
        signal_score = 0
        signals = latest.get("signals", {})
        positive_signals = signals.get("positive", [])
        cautious_signals = signals.get("cautious", [])
        
        # ポジティブシグナルが多い場合、新規組入の可能性UP
        if len(positive_signals) > len(cautious_signals):
            signal_score = 0.6
        elif positive_signals:
            signal_score = 0.3
        
        # 候補セクターに関するポジティブ表現
        for s in cand_sectors:
            for theme, kws in THEME_KEYWORDS.items():
                if any(kw in s for kw in kws):
                    if theme in latest_themes and latest_themes[theme] > 15:
                        signal_score = min(signal_score + 0.2, 1.0)
                        break
        
        score_components["signal_match"] = round(signal_score, 3)
        if signal_score > 0.5:
            explanations.append("直近方針でポジティブシグナル")
        
        # 6. 入替サイクル傾向 (0-1)
        cycle_score = 0
        if cand_name in holdings_analysis:
            ha = holdings_analysis[cand_name]
            if ha["consecutive_months"] == 0 and ha["total_appearances"] > 1:
                # 過去に複数回入っているが現在は外れている → 再登場傾向
                cycle_score = 0.7
                explanations.append(f"入替サイクル: 過去{ha['total_appearances']}回登場、再登場パターン")
            elif ha["rank_volatility"] > 2:
                cycle_score = 0.4
        
        score_components["cycle_tendency"] = round(cycle_score, 3)
        
        # --- 総合スコア ---
        total_score = sum(
            SCORE_WEIGHTS[key] * score_components.get(key, 0)
            for key in SCORE_WEIGHTS
        )
        
        # 信頼度
        if total_score >= 0.5:
            confidence = "High"
        elif total_score >= 0.3:
            confidence = "Medium"
        else:
            confidence = "Low"
        
        # 既に組入済みかどうか
        is_current = cand_name in current_holdings
        
        results.append({
            "name": cand_name,
            "total_score": round(total_score, 3),
            "confidence": confidence,
            "is_current_holding": is_current,
            "score_breakdown": score_components,
            "explanations": explanations if explanations else ["該当する特徴なし"],
        })
    
    # スコア降順ソート
    results.sort(key=lambda x: x["total_score"], reverse=True)
    
    return results


# =============================================================================
# バックテスト
# =============================================================================

def run_backtest(reports: list) -> dict:
    """
    ローリング方式バックテスト
    データリーク防止: t月の予測に t+1以降の情報を使わない
    """
    min_train = BACKTEST_CONFIG["min_training_months"]
    top_k_values = BACKTEST_CONFIG["top_k_values"]
    
    if len(reports) < min_train + 1:
        return {
            "error": f"バックテストには最低{min_train + 1}ヶ月のデータが必要です",
            "results": [],
        }
    
    backtest_results = []
    
    for cutoff_idx in range(min_train, len(reports) - 1):
        # cutoff_idxまでのデータで学習
        train_reports = reports[:cutoff_idx + 1]
        
        # cutoff+1 が予測対象月
        target_report = reports[cutoff_idx + 1]
        target_month = target_report.get("report_month", "")
        target_holdings = {h["name"] for h in target_report.get("holdings", []) if h.get("name")}
        
        # 前月の上位銘柄
        current_holdings = {h["name"] for h in train_reports[-1].get("holdings", []) if h.get("name")}
        
        # 新規登場銘柄
        new_entries = target_holdings - current_holdings
        
        # 分析実行（学習データのみ使用）
        theme_intensity = compute_theme_intensity(train_reports)
        theme_trends = compute_theme_trend(theme_intensity)
        holdings_analysis = analyze_holdings_history(train_reports)
        holding_changes = detect_holding_changes(train_reports)
        
        # 候補推定
        candidates = estimate_candidates(
            train_reports, cutoff_idx,
            theme_trends, holdings_analysis, holding_changes,
        )
        
        # 非現保有の候補のみ（新規組入予測）
        new_candidates = [c for c in candidates if not c["is_current_holding"]]
        
        # 評価
        result = {
            "train_until": train_reports[-1].get("report_month", ""),
            "predicted_month": target_month,
            "actual_new_entries": list(new_entries),
            "metrics": {},
        }
        
        for k in top_k_values:
            top_k_names = {c["name"] for c in new_candidates[:k]}
            hits = top_k_names & new_entries
            
            precision = len(hits) / k if k > 0 else 0
            recall = len(hits) / max(len(new_entries), 1)
            hit_rate = 1 if len(hits) > 0 else 0
            
            result["metrics"][f"top_{k}"] = {
                "predicted": list(top_k_names),
                "hits": list(hits),
                "hit_count": len(hits),
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "hit_rate": hit_rate,
            }
        
        # ヒット/ミスの理由
        hit_explanations = []
        for c in new_candidates[:max(top_k_values)]:
            if c["name"] in new_entries:
                hit_explanations.append({
                    "name": c["name"],
                    "type": "hit",
                    "score": c["total_score"],
                    "reason": "; ".join(c["explanations"]),
                })
            elif c["name"] in target_holdings:
                hit_explanations.append({
                    "name": c["name"],
                    "type": "continuation",
                    "score": c["total_score"],
                    "reason": "継続保有（新規ではない）",
                })
        
        result["explanations"] = hit_explanations
        backtest_results.append(result)
    
    # 集計
    summary = {}
    for k in top_k_values:
        hit_rates = [r["metrics"][f"top_{k}"]["hit_rate"] for r in backtest_results]
        precisions = [r["metrics"][f"top_{k}"]["precision"] for r in backtest_results]
        recalls = [r["metrics"][f"top_{k}"]["recall"] for r in backtest_results]
        
        summary[f"top_{k}"] = {
            "avg_hit_rate": round(sum(hit_rates) / max(len(hit_rates), 1), 3),
            "avg_precision": round(sum(precisions) / max(len(precisions), 1), 3),
            "avg_recall": round(sum(recalls) / max(len(recalls), 1), 3),
            "total_periods": len(backtest_results),
        }
    
    return {
        "summary": summary,
        "results": backtest_results,
    }


# =============================================================================
# メイン実行
# =============================================================================

def run_analysis():
    """
    メイン分析パイプライン
    """
    data_dir = PROJECT_ROOT / "data"
    input_path = data_dir / "reports_data.json"
    output_path = data_dir / "analysis_results.json"
    
    if not input_path.exists():
        print(f"ERROR: {input_path} が見つかりません。")
        print("先に extract_reports.py または generate_sample.py を実行してください。")
        sys.exit(1)
    
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    reports = data.get("reports", [])
    print(f"=== 分析パイプライン ===")
    print(f"対象レポート数: {len(reports)}")
    
    # 1. テーマ強度分析
    print("1. テーマ強度分析...")
    theme_intensity = compute_theme_intensity(reports)
    theme_trends = compute_theme_trend(theme_intensity)
    
    # 2. 銘柄選定傾向分析
    print("2. 銘柄選定傾向分析...")
    holdings_analysis = analyze_holdings_history(reports)
    holding_changes = detect_holding_changes(reports)
    aspect_scores = compute_aspect_scores(reports)
    
    # 3. 候補銘柄推定（最新データ使用）
    print("3. 候補銘柄推定...")
    latest_idx = len(reports) - 1
    candidates = estimate_candidates(
        reports, latest_idx,
        theme_trends, holdings_analysis, holding_changes,
    )
    
    # Top 20候補
    top_candidates = candidates[:20]
    
    # 4. バックテスト
    print("4. バックテスト実行...")
    backtest = run_backtest(reports)
    
    # 5. データ品質サマリー
    quality_summary = {
        "total_reports": len(reports),
        "successful_extractions": sum(
            1 for r in reports if r.get("quality", {}).get("extraction_success", False)
        ),
        "reports_with_holdings": sum(
            1 for r in reports if len(r.get("holdings", [])) > 0
        ),
        "per_report": [
            {
                "month": r.get("report_month", ""),
                "success": r.get("quality", {}).get("extraction_success", False),
                "extracted_fields": r.get("quality", {}).get("extracted_fields", []),
                "missing_fields": r.get("quality", {}).get("missing_fields", []),
                "issues": r.get("quality", {}).get("issues", []),
            }
            for r in reports
        ],
    }
    
    # 6. 結果の組み立て
    # 期間情報
    months = [r.get("report_month", "") for r in reports if r.get("report_month")]
    data_period = {
        "start": min(months) if months else "",
        "end": max(months) if months else "",
        "total_months": len(months),
    }
    
    # 直近テーマTop5
    latest_themes = theme_intensity[-1]["scores"] if theme_intensity else {}
    top_themes = sorted(latest_themes.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # 直近の組入変化件数
    recent_changes = holding_changes[-1] if holding_changes else {}
    change_count = (
        len(recent_changes.get("new_entries", []))
        + len(recent_changes.get("removed", []))
    )
    
    output = {
        "fund_name": data.get("fund_name", "情報エレクトロニクスファンド"),
        "management_company": data.get("management_company", "野村アセットマネジメント"),
        "analyzed_at": datetime.now().isoformat(),
        "data_period": data_period,
        "summary_kpi": {
            "total_reports": len(reports),
            "top_themes": [{"theme": t[0], "score": t[1]} for t in top_themes],
            "recent_change_count": change_count,
            "backtest_top5_hit_rate": backtest.get("summary", {}).get("top_5", {}).get("avg_hit_rate", 0),
        },
        "theme_intensity": theme_intensity,
        "theme_trends": theme_trends,
        "holdings_analysis": {
            name: {k: v for k, v in info.items() if k != "history"}
            for name, info in holdings_analysis.items()
        },
        "holdings_history": {
            name: info["history"]
            for name, info in holdings_analysis.items()
        },
        "holding_changes": holding_changes,
        "aspect_scores": aspect_scores,
        "candidates": top_candidates,
        "backtest": backtest,
        "quality": quality_summary,
        "reports_text": [
            {
                "month": r.get("report_month", ""),
                "sections": r.get("sections", {}),
                "signals": r.get("signals", {}),
                "theme_keywords": r.get("theme_keywords", {}),
                "holdings": r.get("holdings", []),
                "performance": r.get("performance", {}),
            }
            for r in reports
        ],
        "disclaimer": "本ツールは投資助言ではなくリサーチ支援ツールです。将来の運用成果を保証するものではありません。予測結果は過去データに基づく仮説であり、実際の運用判断の根拠として使用しないでください。",
    }
    
    # JSON出力
    os.makedirs(data_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print()
    print(f"=== 完了 ===")
    print(f"出力: {output_path}")
    print(f"候補銘柄数: {len(top_candidates)}")
    if backtest.get("summary"):
        for k, v in backtest["summary"].items():
            print(f"  {k}: Hit Rate={v['avg_hit_rate']:.1%}, Precision={v['avg_precision']:.1%}")


if __name__ == "__main__":
    run_analysis()
