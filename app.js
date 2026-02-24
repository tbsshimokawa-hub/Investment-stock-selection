/**
 * app.js - ファンド月報分析ダッシュボード フロントエンドロジック
 * 
 * データ読込 → 各セクション描画 → インタラクション制御
 * ECharts でグラフ描画、Vanilla JS でUI制御
 */

// =============================================================================
// グローバル状態
// =============================================================================
const AppState = {
    data: null,
    holdingsMonthIdx: 0,
    policyMonthIdx: 0,
    activeThemes: new Set(),
    themePeriod: 'all',
    charts: {},
};

// テーマカラーマップ
const THEME_COLORS = {
    '半導体': '#6366f1',
    'AI・データセンター': '#8b5cf6',
    '通信インフラ': '#06b6d4',
    '車載・電装': '#f97316',
    'コンテンツ・エンタメ×テクノロジー': '#ec4899',
    'セキュリティ・防衛': '#ef4444',
    '設備投資・FA': '#10b981',
    '電子部品・デバイス': '#f59e0b',
};

// =============================================================================
// データ読込
// =============================================================================
async function loadData() {
    try {
        const res = await fetch('data/analysis_results.json');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        AppState.data = await res.json();
        return true;
    } catch (e) {
        console.error('データ読込エラー:', e);
        document.getElementById('loading-overlay').innerHTML = `
            <div class="loader">
                <p style="color:#ef4444;font-size:1rem;">⚠ データの読込に失敗しました</p>
                <p style="color:#9ca3af;font-size:0.85rem;margin-top:8px;">
                    data/analysis_results.json が見つかりません。<br>
                    以下のコマンドを実行してデータを生成してください:
                </p>
                <pre style="background:#1c1f2e;padding:12px;border-radius:8px;margin-top:12px;color:#a78bfa;font-size:0.82rem;text-align:left;">
python src/generate_sample.py
python src/analyze.py</pre>
            </div>`;
        return false;
    }
}

// =============================================================================
// 初期化
// =============================================================================
async function init() {
    const ok = await loadData();
    if (!ok) return;

    const d = AppState.data;

    // ヘッダーメタ
    const period = d.data_period || {};
    document.getElementById('data-period').textContent =
        period.start && period.end ? `${period.start} ～ ${period.end}` : '--';
    document.getElementById('last-updated').textContent =
        d.analyzed_at ? d.analyzed_at.split('T')[0] : '--';

    // 最新月indexを設定
    const reports = d.reports_text || [];
    AppState.holdingsMonthIdx = Math.max(0, reports.length - 1);
    AppState.policyMonthIdx = Math.max(0, reports.length - 1);

    // セクション描画
    renderKPI(d);
    renderThemeChart(d);
    renderHoldings(d);
    renderPolicy(d);
    renderCandidates(d);

    renderQuality(d);

    // ローディング非表示
    document.getElementById('loading-overlay').classList.add('hidden');
    setTimeout(() => {
        document.getElementById('loading-overlay').style.display = 'none';
    }, 500);

    // リサイズ対応
    window.addEventListener('resize', () => {
        Object.values(AppState.charts).forEach(c => c && c.resize());
    });
}

// =============================================================================
// セクション1: KPI
// =============================================================================
function renderKPI(d) {
    const kpi = d.summary_kpi || {};

    document.getElementById('kpi-total-reports').textContent = kpi.total_reports || 0;

    // Top themes
    const themesEl = document.getElementById('kpi-top-themes');
    const themes = kpi.top_themes || [];
    themesEl.innerHTML = themes.map(t =>
        `<span class="kpi-tag">${t.theme}</span>`
    ).join('');

    document.getElementById('kpi-change-count').textContent = kpi.recent_change_count || 0;

    const hitRate = kpi.backtest_top5_hit_rate;
    document.getElementById('kpi-hit-rate').textContent =
        hitRate != null ? `${(hitRate * 100).toFixed(0)}%` : '--%';
}

// =============================================================================
// セクション2: テーマ時系列
// =============================================================================
function renderThemeChart(d) {
    const intensity = d.theme_intensity || [];
    if (!intensity.length) return;

    const themes = Object.keys(intensity[0].scores || {});
    AppState.activeThemes = new Set(themes);

    // テーマトグルボタン生成
    const togglesEl = document.getElementById('theme-toggles');
    togglesEl.innerHTML = themes.map(theme => {
        const color = THEME_COLORS[theme] || '#888';
        return `<button class="theme-toggle active" data-theme="${theme}">
            <span class="dot" style="background:${color}"></span>
            ${theme}
        </button>`;
    }).join('');

    // トグルイベント
    togglesEl.querySelectorAll('.theme-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            const theme = btn.dataset.theme;
            if (AppState.activeThemes.has(theme)) {
                AppState.activeThemes.delete(theme);
                btn.classList.remove('active');
            } else {
                AppState.activeThemes.add(theme);
                btn.classList.add('active');
            }
            updateThemeChart();
        });
    });

    // 期間セレクタ
    document.querySelectorAll('.period-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            AppState.themePeriod = btn.dataset.period;
            updateThemeChart();
        });
    });

    // 初回描画
    updateThemeChart();
}

function updateThemeChart() {
    const d = AppState.data;
    const intensity = d.theme_intensity || [];
    if (!intensity.length) return;

    // 期間フィルタ
    let filtered = intensity;
    const now = intensity[intensity.length - 1].month;
    const nowYear = parseInt(now.split('-')[0]);

    switch (AppState.themePeriod) {
        case '1y':
            filtered = intensity.filter(i => {
                const diff = monthDiff(i.month, now);
                return diff <= 12;
            });
            break;
        case '3y':
            filtered = intensity.filter(i => {
                const diff = monthDiff(i.month, now);
                return diff <= 36;
            });
            break;
        case 'ytd':
            filtered = intensity.filter(i => i.month.startsWith(String(nowYear)));
            break;
    }

    const months = filtered.map(i => i.month);
    const series = [];

    for (const theme of AppState.activeThemes) {
        const color = THEME_COLORS[theme] || '#888';
        series.push({
            name: theme,
            type: 'line',
            smooth: true,
            symbol: 'circle',
            symbolSize: 4,
            lineStyle: { width: 2.5, color },
            itemStyle: { color },
            data: filtered.map(i => (i.scores[theme] || 0)),
        });
    }

    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            backgroundColor: '#1c1f2e',
            borderColor: '#333',
            textStyle: { color: '#e8eaed', fontSize: 12 },
        },
        legend: {
            show: false,
        },
        grid: {
            left: 50, right: 20, top: 20, bottom: 40,
        },
        xAxis: {
            type: 'category',
            data: months,
            axisLine: { lineStyle: { color: '#333' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
        },
        yAxis: {
            type: 'value',
            name: 'テーマ強度',
            nameTextStyle: { color: '#6b7280', fontSize: 11 },
            axisLine: { show: false },
            splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
            axisLabel: { color: '#6b7280', fontSize: 11 },
        },
        series,
    };

    if (!AppState.charts.theme) {
        const el = document.getElementById('chart-themes');
        AppState.charts.theme = echarts.init(el, null, { renderer: 'canvas' });
    }
    AppState.charts.theme.setOption(option, true);
}

// =============================================================================
// セクション3: 組入銘柄変化
// =============================================================================
function renderHoldings(d) {
    const changes = d.holding_changes || [];
    if (!changes.length) return;

    const updateView = () => {
        const idx = AppState.holdingsMonthIdx;
        const change = changes[idx] || {};
        const reports = d.reports_text || [];
        const report = reports[idx] || {};
        const holdings = report.holdings || [];
        const month = change.month || report.month || '--';

        document.getElementById('holdings-month-display').textContent = month;

        // テーブル描画
        const tbody = document.getElementById('holdings-tbody');
        tbody.innerHTML = holdings.map(h => {
            let changeBadge = '<span class="change-same">—</span>';
            if (change.new_entries && change.new_entries.includes(h.name)) {
                changeBadge = '<span class="change-badge change-new">NEW</span>';
            } else {
                const up = (change.rank_up || []).find(r => r.name === h.name);
                const down = (change.rank_down || []).find(r => r.name === h.name);
                if (up) changeBadge = `<span class="change-badge change-up">▲${up.change}</span>`;
                if (down) changeBadge = `<span class="change-badge change-down">▼${Math.abs(down.change)}</span>`;
            }

            return `<tr data-stock="${h.name}">
                <td>${h.rank}</td>
                <td><span class="stock-name">${h.name}</span></td>
                <td>${h.weight ? h.weight + '%' : '-'}</td>
                <td>${changeBadge}</td>
            </tr>`;
        }).join('');

        // 除外銘柄表示
        if (change.removed && change.removed.length) {
            const removedRows = change.removed.map(name =>
                `<tr style="opacity:0.5">
                    <td>-</td>
                    <td><span class="stock-name" style="text-decoration:line-through">${name}</span></td>
                    <td>-</td>
                    <td><span class="change-badge change-removed">除外</span></td>
                </tr>`
            ).join('');
            tbody.innerHTML += removedRows;
        }

        // 銘柄クリックイベント
        tbody.querySelectorAll('tr[data-stock]').forEach(tr => {
            tr.addEventListener('click', () => {
                tbody.querySelectorAll('tr').forEach(r => r.classList.remove('selected'));
                tr.classList.add('selected');
                showStockDetail(tr.dataset.stock, d);
            });
        });
    };

    // ナビゲーション
    document.getElementById('holdings-prev').addEventListener('click', () => {
        if (AppState.holdingsMonthIdx > 0) {
            AppState.holdingsMonthIdx--;
            updateView();
        }
    });
    document.getElementById('holdings-next').addEventListener('click', () => {
        if (AppState.holdingsMonthIdx < changes.length - 1) {
            AppState.holdingsMonthIdx++;
            updateView();
        }
    });

    updateView();
}

function showStockDetail(stockName, d) {
    const detailEl = document.getElementById('holdings-detail');
    const history = (d.holdings_history || {})[stockName] || [];
    const analysis = (d.holdings_analysis || {})[stockName] || {};

    if (!history.length) {
        detailEl.innerHTML = `<div class="detail-placeholder"><p>この銘柄の履歴データがありません</p></div>`;
        return;
    }

    // 詳細情報
    let html = `<div class="detail-stock-name">${stockName}</div>`;
    html += `<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px;font-size:0.82rem;">
        <div><span style="color:#6b7280">登場回数:</span> ${analysis.total_appearances || 0}回</div>
        <div><span style="color:#6b7280">平均順位:</span> ${analysis.avg_rank || '-'}位</div>
        <div><span style="color:#6b7280">連続月数:</span> ${analysis.consecutive_months || 0}ヶ月</div>
    </div>`;

    // ミニチャート
    html += `<div class="detail-chart" id="stock-detail-chart"></div>`;

    // 履歴リスト
    html += `<div class="detail-history">`;
    history.slice(-12).reverse().forEach(h => {
        html += `<div class="detail-history-item">
            <span>${h.month}</span>
            <span>${h.rank}位${h.weight ? ' (' + h.weight + '%)' : ''}</span>
        </div>`;
    });
    html += `</div>`;

    detailEl.innerHTML = html;

    // ミニチャート描画
    setTimeout(() => {
        const chartEl = document.getElementById('stock-detail-chart');
        if (!chartEl) return;
        const chart = echarts.init(chartEl, null, { renderer: 'canvas' });
        chart.setOption({
            backgroundColor: 'transparent',
            grid: { left: 40, right: 10, top: 10, bottom: 30 },
            xAxis: {
                type: 'category',
                data: history.map(h => h.month),
                axisLabel: { color: '#6b7280', fontSize: 10, rotate: 45 },
                axisLine: { lineStyle: { color: '#333' } },
            },
            yAxis: {
                type: 'value',
                inverse: true,
                min: 1,
                max: 10,
                name: '順位',
                nameTextStyle: { color: '#6b7280', fontSize: 10 },
                axisLine: { show: false },
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
                axisLabel: { color: '#6b7280', fontSize: 10 },
            },
            series: [{
                type: 'line',
                smooth: true,
                data: history.map(h => h.rank),
                lineStyle: { color: '#6366f1', width: 2 },
                itemStyle: { color: '#6366f1' },
                areaStyle: {
                    color: {
                        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(99,102,241,0.3)' },
                            { offset: 1, color: 'rgba(99,102,241,0.02)' },
                        ],
                    },
                },
            }],
            tooltip: {
                trigger: 'axis',
                backgroundColor: '#1c1f2e',
                borderColor: '#333',
                textStyle: { color: '#e8eaed', fontSize: 11 },
                formatter: p => `${p[0].name}<br/>順位: ${p[0].value}位`,
            },
        });
        AppState.charts.stockDetail = chart;
    }, 50);
}

// =============================================================================
// セクション4: 運用方針テキスト分析
// =============================================================================
function renderPolicy(d) {
    const reports = d.reports_text || [];
    if (!reports.length) return;

    const updateView = () => {
        const idx = AppState.policyMonthIdx;
        const report = reports[idx] || {};
        const month = report.month || '--';

        document.getElementById('policy-month-display').textContent = month;

        // 方針テキスト
        const policyText = (report.sections || {}).future_policy || '（テキスト未抽出）';
        document.getElementById('policy-text').textContent = policyText;

        // キーワードクラウド
        const themeKw = report.theme_keywords || {};
        const cloudEl = document.getElementById('keyword-cloud');
        const allKw = [];
        for (const [theme, data] of Object.entries(themeKw)) {
            const count = data.count || 0;
            (data.found_keywords || []).forEach(kw => {
                allKw.push({ keyword: kw, count, theme });
            });
        }
        allKw.sort((a, b) => b.count - a.count);

        const maxCount = allKw.length ? allKw[0].count : 1;
        cloudEl.innerHTML = allKw.map(kw => {
            const ratio = kw.count / maxCount;
            const sizeClass = ratio > 0.7 ? 'large' : ratio > 0.4 ? 'medium' : 'small';
            const color = THEME_COLORS[kw.theme] || '#888';
            return `<span class="keyword-tag ${sizeClass}" style="background:${color}20;color:${color}">${kw.keyword}</span>`;
        }).join('');

        // 前月比キーワード変化
        const changesEl = document.getElementById('keyword-changes');
        if (idx > 0) {
            const prev = reports[idx - 1];
            const prevKw = prev.theme_keywords || {};
            const changes = [];

            for (const [theme, data] of Object.entries(themeKw)) {
                const currCount = data.count || 0;
                const prevCount = (prevKw[theme] || {}).count || 0;
                const diff = currCount - prevCount;
                if (diff !== 0) {
                    changes.push({ theme, diff, currCount, prevCount });
                }
            }

            changes.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
            changesEl.innerHTML = changes.map(c => {
                const cls = c.diff > 0 ? 'keyword-increase' : 'keyword-decrease';
                const arrow = c.diff > 0 ? '▲' : '▼';
                return `<div class="${cls}" style="padding:4px 0;font-size:0.85rem;">
                    ${arrow} ${c.theme}: ${c.prevCount} → ${c.currCount} (${c.diff > 0 ? '+' : ''}${c.diff})
                </div>`;
            }).join('') || '<span style="color:#6b7280;font-size:0.85rem;">変化なし</span>';
        } else {
            changesEl.innerHTML = '<span style="color:#6b7280;font-size:0.85rem;">前月データなし</span>';
        }

        // 売買シグナル
        const signals = report.signals || {};
        const signalsEl = document.getElementById('signals-view');
        let sigHtml = '';

        if (signals.positive && signals.positive.length) {
            sigHtml += `<div class="signal-group signal-positive">
                <div class="signal-label">🟢 ポジティブ表現</div>
                <div class="signal-tags">${signals.positive.map(s =>
                `<span class="signal-tag">${s}</span>`).join('')}
                </div>
            </div>`;
        }
        if (signals.cautious && signals.cautious.length) {
            sigHtml += `<div class="signal-group signal-cautious">
                <div class="signal-label">🟡 慎重表現</div>
                <div class="signal-tags">${signals.cautious.map(s =>
                `<span class="signal-tag">${s}</span>`).join('')}
                </div>
            </div>`;
        }
        signalsEl.innerHTML = sigHtml || '<span style="color:#6b7280;font-size:0.85rem;">シグナルなし</span>';
    };

    // ナビゲーション
    document.getElementById('policy-prev').addEventListener('click', () => {
        if (AppState.policyMonthIdx > 0) {
            AppState.policyMonthIdx--;
            updateView();
        }
    });
    document.getElementById('policy-next').addEventListener('click', () => {
        if (AppState.policyMonthIdx < reports.length - 1) {
            AppState.policyMonthIdx++;
            updateView();
        }
    });

    updateView();
}

// =============================================================================
// セクション5: 候補銘柄予測
// =============================================================================
function renderCandidates(d) {
    const candidates = d.candidates || [];
    if (!candidates.length) return;

    const listEl = document.getElementById('candidates-list');
    const maxScore = candidates.length ? candidates[0].total_score : 1;

    // 非保有の候補のみ（新規組入予測）を先に、保有中を後に
    const newCandidates = candidates.filter(c => !c.is_current_holding);
    const displayList = newCandidates.slice(0, 15);

    listEl.innerHTML = displayList.map((c, i) => {
        const rank = i + 1;
        const rankClass = rank <= 3 ? 'top-3' : 'top-10';
        const confClass = `confidence-${c.confidence.toLowerCase()}`;
        const pct = ((c.total_score / Math.max(maxScore, 0.01)) * 100).toFixed(0);

        // スコア内訳
        const breakdown = c.score_breakdown || {};
        const breakdownLabels = {
            theme_match: 'テーマ一致',
            past_frequency: '過去採用',
            description_sim: '解説類似',
            sector_trend: '業種トレンド',
            signal_match: 'シグナル',
            cycle_tendency: '入替サイクル',
        };
        const breakdownColors = {
            theme_match: '#6366f1',
            past_frequency: '#8b5cf6',
            description_sim: '#06b6d4',
            sector_trend: '#10b981',
            signal_match: '#f59e0b',
            cycle_tendency: '#ec4899',
        };

        const breakdownHTML = Object.entries(breakdownLabels).map(([key, label]) => {
            const val = breakdown[key] || 0;
            const color = breakdownColors[key] || '#888';
            return `<div class="breakdown-item">
                <div class="breakdown-label">${label}</div>
                <div class="breakdown-bar-track">
                    <div class="breakdown-bar-fill" style="width:${(val * 100).toFixed(0)}%;background:${color}"></div>
                </div>
                <div class="breakdown-value">${(val * 100).toFixed(1)}%</div>
            </div>`;
        }).join('');

        const explanations = (c.explanations || []).map(e =>
            `<li>${e}</li>`
        ).join('');

        return `<div class="candidate-card" data-idx="${i}">
            <div class="candidate-header">
                <div class="candidate-rank ${rankClass}">${rank}</div>
                <div class="candidate-info">
                    <div class="candidate-name">${c.name}</div>
                    <div class="candidate-meta">${c.is_current_holding ? '現在組入中' : '新規候補'}</div>
                </div>
                <div class="candidate-score-bar">
                    <div class="score-track">
                        <div class="score-fill" style="width:${pct}%"></div>
                    </div>
                    <div class="score-value">${(c.total_score * 100).toFixed(0)}</div>
                </div>
                <div class="candidate-confidence ${confClass}">${c.confidence}</div>
            </div>
            <div class="candidate-detail">
                <h4 style="font-size:0.85rem;color:#9ca3af;margin-bottom:10px;">スコア内訳</h4>
                <div class="breakdown-grid">${breakdownHTML}</div>
                <h4 style="font-size:0.85rem;color:#9ca3af;margin-bottom:8px;">根拠</h4>
                <ul class="explanations-list">${explanations}</ul>
            </div>
        </div>`;
    }).join('');

    // カード展開
    listEl.querySelectorAll('.candidate-card').forEach(card => {
        card.addEventListener('click', () => {
            card.classList.toggle('expanded');
        });
    });

    // CSVエクスポート
    document.getElementById('btn-export-candidates').addEventListener('click', () => {
        exportCandidatesCSV(displayList);
    });
}

function exportCandidatesCSV(candidates) {
    const BOM = '\uFEFF';
    const header = 'ランク,銘柄名,総合スコア,信頼度,テーマ一致,過去採用,解説類似,業種トレンド,シグナル,入替サイクル,根拠\n';
    const rows = candidates.map((c, i) => {
        const bd = c.score_breakdown || {};
        const expl = (c.explanations || []).join('; ');
        return `${i + 1},"${c.name}",${c.total_score},${c.confidence},${bd.theme_match || 0},${bd.past_frequency || 0},${bd.description_sim || 0},${bd.sector_trend || 0},${bd.signal_match || 0},${bd.cycle_tendency || 0},"${expl}"`;
    }).join('\n');

    const blob = new Blob([BOM + header + rows], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `候補銘柄_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}



// =============================================================================
// セクション7: データ品質
// =============================================================================
function renderQuality(d) {
    const q = d.quality || {};

    // サマリー
    const summaryEl = document.getElementById('quality-summary');
    const total = q.total_reports || 0;
    const success = q.successful_extractions || 0;
    const withHoldings = q.reports_with_holdings || 0;
    const rate = total ? ((success / total) * 100).toFixed(0) : 0;

    summaryEl.innerHTML = `
        <div class="quality-stat">
            <div class="quality-stat-label">全レポート数</div>
            <div class="quality-stat-value">${total}</div>
        </div>
        <div class="quality-stat">
            <div class="quality-stat-label">抽出成功率</div>
            <div class="quality-stat-value ${rate >= 80 ? 'good' : 'warn'}">${rate}%</div>
        </div>
        <div class="quality-stat">
            <div class="quality-stat-label">銘柄取得済み</div>
            <div class="quality-stat-value ${withHoldings >= total * 0.8 ? 'good' : 'warn'}">${withHoldings}/${total}</div>
        </div>
    `;

    // テーブル
    const tbody = document.getElementById('quality-tbody');
    const perReport = q.per_report || [];
    tbody.innerHTML = perReport.map(r => {
        const statusClass = r.success ? 'status-ok' : 'status-error';
        const statusText = r.success ? '✓ OK' : '✗ エラー';
        const extracted = (r.extracted_fields || []).join(', ') || '-';
        const missing = (r.missing_fields || []).join(', ') || '-';
        const issues = (r.issues || []).join(', ') || '-';

        return `<tr>
            <td>${r.month || '-'}</td>
            <td class="${statusClass}">${statusText}</td>
            <td style="font-size:0.78rem">${extracted}</td>
            <td style="font-size:0.78rem;${missing !== '-' ? 'color:#f59e0b' : ''}">${missing}</td>
            <td style="font-size:0.78rem;${issues !== '-' ? 'color:#ef4444' : ''}">${issues}</td>
        </tr>`;
    }).join('');
}

// =============================================================================
// ユーティリティ
// =============================================================================
function monthDiff(m1, m2) {
    const [y1, mo1] = m1.split('-').map(Number);
    const [y2, mo2] = m2.split('-').map(Number);
    return (y2 - y1) * 12 + (mo2 - mo1);
}

// =============================================================================
// アプリ起動
// =============================================================================
document.addEventListener('DOMContentLoaded', init);
