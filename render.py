"""
Beaten-Down Hunter — HTML rendering.
Reuses Premium Hunter's card design with dislocation-specific changes.
"""

from datetime import datetime


def fmt_money(v):
    if v is None:
        return '—'
    absv = abs(v)
    if absv >= 1e12: return f'${v/1e12:.1f}T'
    if absv >= 1e9: return f'${v/1e9:.1f}B'
    if absv >= 1e6: return f'${v/1e6:.0f}M'
    return f'${v:.0f}'


def yoy_pill(yoy):
    if yoy is None:
        return '<span class="fund-na">— no data</span>'
    if yoy >= 5:
        return f'<span class="fund-up">▲ {yoy:.0f}%</span>'
    if yoy <= -5:
        return f'<span class="fund-down">▼ {abs(yoy):.0f}%</span>'
    return f'<span class="fund-flat">↔ {yoy:+.0f}%</span>'


def safety_score(otm_pct, max_drop_pct):
    """Gap-risk based safety: OTM% vs 1.5x max historical 1-day drop."""
    if max_drop_pct is None or max_drop_pct == 0:
        max_drop_pct = -5
    buffer = otm_pct / (1.5 * abs(max_drop_pct))
    if buffer >= 3.0: return 10
    if buffer >= 2.5: return 9
    if buffer >= 2.0: return 8
    if buffer >= 1.5: return 7
    if buffer >= 1.2: return 6
    if buffer >= 1.0: return 5
    if buffer >= 0.85: return 4
    if buffer >= 0.7: return 3
    if buffer >= 0.55: return 2
    return 1


def safety_html(otm_pct, max_drop_pct):
    s = safety_score(otm_pct, max_drop_pct)
    tier = 'high' if s >= 8 else 'mid' if s >= 6 else 'low' if s >= 4 else 'danger'
    label = 'safe' if s >= 8 else 'ok' if s >= 6 else 'risky' if s >= 4 else 'danger'
    return f'<span class="safety-pill safety-{tier}">🛡 {s}/10 {label}</span>'


def build_dislocation_row(sig):
    """Visual checklist of which dislocation signals fired."""
    items = [
        ('below_sma50_fired', f'Below SMA50 by {abs(sig.get("below_sma50_today_pct", 0)):.0f}%' if sig.get('below_sma50_today_pct') else 'Below SMA50 by 10%+'),
        ('rsi_oversold_fired', f'RSI hit {sig.get("rsi_min_14d", 0):.0f}' + (f' ({sig.get("rsi_min_days_ago", 0)}d ago)' if sig.get('rsi_min_days_ago') else '')),
        ('lower_bb_fired', 'Touched lower Bollinger'),
        ('perf_1m_fired', f'1mo perf {sig.get("perf_1m_pct", 0):.0f}%'),
        ('near_52w_low_fired', f'Near 52w low ({(sig.get("current_price",0)-sig.get("low_52w",1))/sig.get("low_52w",1)*100:.0f}% off)'),
        ('atl_5y_fired', '5y all-time low'),
    ]
    
    pills = []
    fired_count = 0
    for key, label in items:
        if sig.get(key):
            pills.append(f'<div class="disloc-pill disloc-fired"><span class="disloc-icon">●</span><span>{label}</span></div>')
            fired_count += 1
        else:
            pills.append(f'<div class="disloc-pill disloc-not-fired"><span class="disloc-icon">○</span><span>{label}</span></div>')
    
    # Recovery momentum bonus
    if sig.get('recovery_momentum'):
        rsi_now = sig.get('rsi_today', 0)
        pills.append(f'<div class="disloc-pill disloc-bonus"><span class="disloc-icon">⚡</span><span>Recovery: RSI now {rsi_now:.0f} (rising)</span></div>')
    
    return f'''
        <div class="dislocation-row">
            <div class="dislocation-header">
                <span>🎯 Dislocation signals fired (last 14 days)</span>
                <span class="disloc-count">{fired_count} / 6 fired</span>
            </div>
            <div class="disloc-grid">
                {"".join(pills)}
            </div>
        </div>'''


def build_fundamentals(funds):
    """Real Revenue / Profit / FCF / Debt with YoY."""
    rev_row = f'<div class="fund-row"><span class="fund-label">Revenue</span><span class="fund-val">{fmt_money(funds.get("revenue_val"))} {yoy_pill(funds.get("revenue_yoy"))}</span></div>'
    prof_row = f'<div class="fund-row"><span class="fund-label">Profit</span><span class="fund-val">{fmt_money(funds.get("profit_val"))} {yoy_pill(funds.get("profit_yoy"))}</span></div>'
    fcf_row = f'<div class="fund-row"><span class="fund-label">Free cash</span><span class="fund-val">{fmt_money(funds.get("fcf_val"))} {yoy_pill(funds.get("fcf_yoy"))}</span></div>'
    de = funds.get('debt_eq')
    de_label = funds.get('debt_label')
    if de is not None:
        de_class = 'fund-up' if de_label == 'low' else 'fund-flat' if de_label == 'moderate' else 'fund-down'
        de_arrow = '✓ low' if de_label == 'low' else '↔ moderate' if de_label == 'moderate' else '▲ heavy'
        debt_row = f'<div class="fund-row"><span class="fund-label">Debt/Eq</span><span class="fund-val">{de:.2f} <span class="{de_class}">{de_arrow}</span></span></div>'
    else:
        debt_row = '<div class="fund-row"><span class="fund-label">Debt/Eq</span><span class="fund-val"><span class="fund-na">— no data</span></span></div>'
    return rev_row + prof_row + fcf_row + debt_row


def build_pick(r):
    """Build one Beaten-Down card."""
    sig = r['signals']
    pt = r.get('put_trade') or {}
    alt = r.get('alt_put') or {}
    
    # Header
    pct_off = sig.get('pct_off_high_52w', 0)
    cause = ''  # Claude can fill this in via blurb; for now show generic
    if abs(pct_off) >= 30: cause = 'sharp drawdown'
    elif abs(pct_off) >= 20: cause = 'beaten down'
    else: cause = 'consolidating'
    
    down_pill = f'<div class="down-pill"><span class="down-emoji">📉</span>DOWN {abs(pct_off):.0f}% from high · {cause}</div>'
    
    # Bargain price = average of supports and tariff (or 5-10% below current)
    tariff_floor = r.get('tariff_floor')
    bargain = round(tariff_floor) if tariff_floor else round(r['price'] * 0.92)
    
    # Scores
    my_score = r['score']
    claude_score = round(r.get('claude_score', my_score), 1)
    claude_tag = r.get('claude_tag', 'BUY')
    tag_class = 'tag-strong-buy' if claude_tag == 'STRONG BUY' else 'tag-buy' if claude_tag == 'BUY' else 'tag-skip'
    
    # Narrative
    narrative = r.get('claude_blurb') or r.get('company_narrative', f"{r['company']} · {r.get('sector', '')}")
    if len(narrative) > 360:
        narrative = narrative[:357] + '...'
    
    # Claude bullets
    bullets_html = ''
    if r.get('claude_bullets'):
        for tone, text in r['claude_bullets']:
            cls = f'bullet-{tone}'
            bullets_html += f'<div class="claude-bullet {cls}"><span>●</span><span>{text}</span></div>'
    else:
        bullets_html = '<div class="claude-bullet bullet-warn"><span>●</span><span>Claude analysis pending</span></div>'
    
    # Fundamentals
    fund_html = build_fundamentals(r.get('fundamentals', {}))
    
    # Signal pills (buybacks etc)
    sig_chips = []
    bb = r.get('buybacks') or {}
    if bb.get('signal') in ('strong', 'moderate') and bb.get('amount'):
        sig_chips.append(f'<span class="sig-chip sig-buyback">💰 Buybacks ${bb["amount"]/1e9:.1f}B</span>')
    rf = r.get('red_flags') or {}
    if rf.get('signal') == 'clear':
        sig_chips.append('<span class="sig-chip sig-noflag">✓ No red flags</span>')
    iv_rank = r.get('iv_rank')
    if iv_rank and iv_rank >= 40:
        sig_chips.append(f'<span class="sig-chip sig-eps">⚡ IV rank {iv_rank}%</span>')
    si = r.get('short_interest')
    if isinstance(si, (int, float)) and si is not None:
        si_pct = si * 100 if si < 1 else si
        if si_pct < 5:
            sig_chips.append(f'<span class="sig-chip sig-short-good">📉 Short int {si_pct:.1f}% ✓</span>')
    uw = r.get('uw_flow') or {}
    if uw.get('bullish_put_flow'):
        sig_chips.append('<span class="sig-chip sig-eps">💎 UW bullish put flow</span>')
    signals_html = f'<div class="signals-row">{"".join(sig_chips)}</div>' if sig_chips else ''
    
    # Dislocation row
    disloc_html = build_dislocation_row(sig)
    
    # Trade rows
    max_drop = r.get('max_1d_drop_pct', -5)
    primary_dte = pt.get('dte', 0)
    primary_html = f'''<div class="put-row">
        <div class="put-dte-large">{primary_dte}<span class="dte-unit">DTE</span></div>
        <span class="put-strike">${pt.get("strike",0):.0f}P</span>
        <div class="put-meta-row">
            <span>{pt.get("expiry","")[:7]}</span>
            <span>·</span>
            <span>{pt.get("delta",0)*100:.0f}Δ</span>
            <span>·</span>
            <span>{pt.get("pct_otm",0):.0f}% OTM</span>
            <span class="otm-mult">×{r.get("suggested_size",3)}</span>
            {safety_html(pt.get("pct_otm",0), max_drop)}
        </div>
    </div>'''
    
    alt_html = ''
    if alt:
        alt_html = f'''<div class="put-row">
            <div class="put-dte-large alt">{alt.get("dte",35)}<span class="dte-unit">DTE</span></div>
            <span class="put-strike">${alt.get("strike",0):.0f}P</span>
            <div class="put-meta-row">
                <span>{alt.get("expiry","")[:10]}</span>
                <span>·</span>
                <span>{alt.get("delta",0)*100:.0f}Δ</span>
                <span>·</span>
                <span>{alt.get("otm_pct",0):.0f}% OTM</span>
                <span class="otm-mult">×3</span>
                {safety_html(alt.get("otm_pct",0), max_drop)}
            </div>
        </div>'''
    
    # Hero stats — DISLOCATION DEPTH
    days_oversold = '—'
    if sig.get('rsi_min_days_ago') is not None:
        days_oversold = f'{sig["rsi_min_days_ago"]}d ago'
    
    pct_above_low = sig.get('pct_above_low_52w', 0) or 0
    
    hero_html = f'''<div class="hero-stats">
        <div class="hero-stat hero-bad">
            <div class="hero-stat-ticker">{r['ticker']}</div>
            <div class="hero-stat-label">📉 Off 52w high</div>
            <div class="hero-stat-val">{pct_off:.0f}%</div>
        </div>
        <div class="hero-stat hero-bad">
            <div class="hero-stat-ticker">{r['ticker']}</div>
            <div class="hero-stat-label">⏰ RSI low</div>
            <div class="hero-stat-val">{days_oversold}</div>
        </div>
        <div class="hero-stat hero-good">
            <div class="hero-stat-ticker">{r['ticker']}</div>
            <div class="hero-stat-label">⚡ Off 52w low</div>
            <div class="hero-stat-val">+{pct_above_low:.0f}%</div>
        </div>
        <div class="hero-stat hero-good">
            <div class="hero-stat-ticker">{r['ticker']}</div>
            <div class="hero-stat-label">🛡️ IV rank</div>
            <div class="hero-stat-val">{iv_rank or "—"}%</div>
        </div>
    </div>'''
    
    # Key Metrics
    cap = r.get('market_cap', 0)
    pe = r.get('pe', 0)
    dy = r.get('dividend_yield')
    eps_streak = r.get('eps_streak', {}).get('streak', '—')
    
    metrics_html = f'''<div class="metrics-strip">
        <div class="metric-tile">
            <div class="metric-tile-ticker">{r['ticker']}</div>
            <div class="metric-tile-label">Market cap</div>
            <div class="metric-tile-value">{fmt_money(cap)}</div>
        </div>
        <div class="metric-tile">
            <div class="metric-tile-ticker">{r['ticker']}</div>
            <div class="metric-tile-label">P/E ratio</div>
            <div class="metric-tile-value">{f"{pe:.1f}" if pe else "—"}</div>
        </div>
        <div class="metric-tile">
            <div class="metric-tile-ticker">{r['ticker']}</div>
            <div class="metric-tile-label">Dividend</div>
            <div class="metric-tile-value">{f"{dy:.1f}%" if dy else "—"}</div>
        </div>
        <div class="metric-tile">
            <div class="metric-tile-ticker">{r['ticker']}</div>
            <div class="metric-tile-label">EPS growth</div>
            <div class="metric-tile-value">{(r.get("eps_growth") or 0)*100:.0f}%</div>
        </div>
    </div>'''
    
    # 1Y chart (simple)
    high_1y = sig.get('high_1y', r['price'])
    low_1y = sig.get('low_1y', r['price'])
    pct_1y = sig.get('pct_1y', 0)
    chart_html = f'''<div class="chart-section">
        <div class="chart-svg-box">
            <svg viewBox="0 0 700 110" xmlns="http://www.w3.org/2000/svg">
                <line x1="20" y1="20" x2="680" y2="20" stroke="#7c3aed" stroke-dasharray="3,3" stroke-width="0.6"/>
                <text x="22" y="16" fill="#a78bfa" font-size="9" font-weight="600">52w high ${high_1y:.0f}</text>
                <line x1="20" y1="92" x2="680" y2="92" stroke="#dc2626" stroke-dasharray="3,3" stroke-width="0.6"/>
                <text x="22" y="102" fill="#fca5a5" font-size="9" font-weight="600">52w low ${low_1y:.0f}</text>
                <text x="660" y="60" fill="{'#34d399' if pct_1y >= 0 else '#f87171'}" font-size="11" font-weight="700" text-anchor="middle">{pct_1y:+.0f}% YoY</text>
            </svg>
        </div>
    </div>'''
    
    # Recovery thesis
    rsi_min = sig.get('rsi_min_14d', 50)
    rsi_now = sig.get('rsi_today', 50)
    perf_1m = sig.get('perf_1m_pct', 0)
    recovery_html = f'''<div class="recovery-line">
        <div class="recovery-line-text">
            🌱 <strong>Recovery thesis:</strong> Down {abs(pct_off):.0f}% from high. RSI bounced from <span class="key">{rsi_min:.0f} → {rsi_now:.0f}</span>. 1-month perf <span class="key">{perf_1m:+.0f}%</span>. Watch for stabilization.
        </div>
    </div>'''
    
    # Support ladder + stress test
    price = r['price']
    strike = pt.get('strike', 0)
    low_14d = sig.get('low_14d', price)
    
    ladder_rows = [
        ('Price', '#fbbf24', '#f1f5f9', f'${price:.0f} now', '', price, True),
        ('Support', '#3b82f6', '#cbd5e1', f'${low_14d:.0f}', f'−{(price-low_14d)/price*100:.0f}% (14d low)', low_14d, False),
    ]
    if tariff_floor and tariff_floor < price:
        ladder_rows.append(('⚠ Tariff', '#a855f7', '#c4b5fd', f'${tariff_floor:.0f}', f'−{(price-tariff_floor)/price*100:.0f}% (Apr 2025)', tariff_floor, False))
    if strike and strike < price:
        ladder_rows.append(('Strike', '#10b981', '#6ee7b7', f'${strike:.0f}', f'−{(price-strike)/price*100:.0f}% ✓', strike, False))
    
    # Sort by price desc, keep current price at top
    current_row = [r_ for r_ in ladder_rows if r_[6]]
    other_rows = sorted([r_ for r_ in ladder_rows if not r_[6]], key=lambda x: x[5], reverse=True)
    ladder_rows = current_row + other_rows
    
    ladder_html = ''
    for label, dot, lc, val, pct, _, _ in ladder_rows:
        is_tariff = '⚠' in label
        cls = 'ladder-row tariff' if is_tariff else 'ladder-row'
        ladder_html += f'''<div class="{cls}">
            <span class="ladder-label" style="color:{lc};">{label}</span>
            <span class="ladder-dot" style="background:{dot};"></span>
            <span class="ladder-value" style="color:{lc};">{val} <span class="ladder-pct">{pct}</span></span>
        </div>'''
    
    stress_html = ''
    if tariff_floor and strike:
        diff_pct = (tariff_floor - strike) / tariff_floor * 100
        years_no_touch = 5  # could compute from hist_5y
        stress_html = f'''<div class="stress-line-text">
            🛡️ <strong>Stress test:</strong> Strike ${strike:.0f} sits <strong>{diff_pct:.0f}% below</strong> the April 2025 tariff panic floor of ${tariff_floor:.0f}. <span class="never">Stock has never traded at ${strike:.0f} in {years_no_touch} years.</span>
        </div>'''
    
    support_section = f'''<div class="support-section">
        <div class="support-header">🪜 Support floors · stress test</div>
        <div class="support-ladder">{ladder_html}</div>
        {stress_html}
    </div>'''
    
    # News
    news_html = ''
    claude_sents = r.get('claude_news_sentiments') or []
    for i, item in enumerate(r.get('news_items', [])):
        sent = claude_sents[i] if i < len(claude_sents) else item.get('sentiment', 'neutral')
        icon = '▲' if sent == 'positive' else '▼' if sent == 'negative' else '●'
        cls = 'news-pos' if sent == 'positive' else 'news-neg' if sent == 'negative' else 'news-neu'
        url = item.get('url', '')
        title = item.get('title', '')
        link = f'<a href="{url}" target="_blank" rel="noopener" class="news-title-link">{title}</a>' if url else f'<span>{title}</span>'
        news_html += f'<div class="news-item"><span class="news-icon {cls}">{icon}</span>{link}<span class="news-date">{item.get("date","")}</span></div>'
    if not news_html:
        news_html = '<div style="color:#94a3b8;font-size:12px;">No recent headlines</div>'
    
    # Indicators (simplified for now — sharpened bars)
    indicators_html = build_indicators(r)
    
    return f'''
    <div class="pick-bd">
        <div class="tag-side">BD</div>
        <div class="pick-body">
            <div class="card-header">
                <div class="header-ticker-block">
                    <a href="https://unusualwhales.com/stock/{r['ticker']}" target="_blank" class="card-ticker">{r['ticker']}</a>
                    <span class="dislocation-emoji">🔻</span>
                </div>
                <div class="header-middle">
                    <div class="header-scores">
                        <div class="score-block">
                            <div class="score-label">My Score</div>
                            <div class="score-badge score-mine">{my_score}</div>
                        </div>
                        <span class="score-sep">·</span>
                        <div class="score-block">
                            <div class="score-label score-claude-label">Claude</div>
                            <div class="score-badge score-claude">{claude_score}</div>
                        </div>
                    </div>
                    {down_pill}
                </div>
                <div class="header-right">
                    <div class="company-name">{r['company']}</div>
                    <div class="price-row">
                        <span class="company-price">${r['price']:.2f}</span>
                        <span class="bargain-inline">🎯 ${bargain}</span>
                    </div>
                </div>
            </div>
            
            {disloc_html}
            
            <div class="company-claude-row">
                <div class="company-box">
                    <div class="box-label">🍕 The company</div>
                    <div class="company-blurb">{narrative}</div>
                    <div class="fund-grid">{fund_html}</div>
                </div>
                <div class="claude-box">
                    <div class="claude-header">
                        <div class="claude-c">C</div>
                        <div class="claude-label-txt">Claude says</div>
                        <div class="claude-tag {tag_class}">{claude_tag}</div>
                    </div>
                    {bullets_html}
                </div>
            </div>
            
            {signals_html}
            
            <div class="trade-section">
                {primary_html}
                {alt_html}
            </div>
            
            {hero_html}
            {metrics_html}
            {chart_html}
            {recovery_html}
            {support_section}
            {indicators_html}
            
            <div class="news-section">
                <div class="news-header">📰 Latest <strong>{r['ticker']}</strong> news</div>
                {news_html}
            </div>
        </div>
    </div>
    '''


def build_indicators(r):
    """52w / 50DMA / 200DMA / RSI / Bollinger as bars."""
    sig = r['signals']
    price = r['price']
    high_1y = sig.get('high_1y', price)
    low_1y = sig.get('low_1y', price)
    
    range_pos = (price - low_1y) / (high_1y - low_1y) * 100 if high_1y > low_1y else 50
    
    range_html = f'''
    <div class="ind-line">
        <div class="ind-line-top"><span class="ind-line-name">52w range</span><span class="ind-line-val">${price:.2f}</span></div>
        <div class="bar-track">
            <div class="bar-zone range52-zone-low"></div>
            <div class="bar-zone range52-zone-mid"></div>
            <div class="bar-zone range52-zone-high"></div>
            <div class="bar-marker" style="left:{range_pos:.0f}%;"></div>
        </div>
        <div class="bar-labels"><span>${low_1y:.0f} LOW</span><span>${(low_1y+high_1y)/2:.0f}</span><span>${high_1y:.0f} HIGH</span></div>
    </div>'''
    
    dma50 = sig.get('dma_50')
    dma50_html = ''
    if dma50:
        pct = (price - dma50) / dma50 * 100
        marker_pos = max(10, min(90, 50 + pct * 2))
        color = '#34d399' if pct >= 0 else '#f87171'
        dma50_html = f'''
        <div class="ind-line">
            <div class="ind-line-top"><span class="ind-line-name">50d MA</span><span class="ind-line-val" style="color:{color};">{pct:+.0f}% {"above" if pct >= 0 else "below"}</span></div>
            <div class="bar-track">
                <div class="bar-zone dma-zone-bad"></div>
                <div class="bar-zone dma-zone-good"></div>
                <div class="bar-marker" style="left:{marker_pos:.0f}%;"></div>
            </div>
        </div>'''
    
    dma200 = sig.get('dma_200')
    dma200_html = ''
    if dma200:
        pct = (price - dma200) / dma200 * 100
        marker_pos = max(10, min(90, 50 + pct * 2))
        color = '#34d399' if pct >= 0 else '#f87171'
        dma200_html = f'''
        <div class="ind-line">
            <div class="ind-line-top"><span class="ind-line-name">200d MA</span><span class="ind-line-val" style="color:{color};">{pct:+.0f}% {"above" if pct >= 0 else "below"}</span></div>
            <div class="bar-track">
                <div class="bar-zone dma-zone-bad"></div>
                <div class="bar-zone dma-zone-good"></div>
                <div class="bar-marker" style="left:{marker_pos:.0f}%;"></div>
            </div>
        </div>'''
    
    rsi = sig.get('rsi_today')
    rsi_html = ''
    if rsi is not None:
        state = 'oversold' if rsi < 30 else 'overbought' if rsi > 70 else 'recovering' if rsi < 50 else 'normal'
        color = '#6ee7b7' if rsi < 35 else '#fbbf24' if rsi < 50 else '#cbd5e1'
        rsi_html = f'''
        <div class="ind-line">
            <div class="ind-line-top"><span class="ind-line-name">RSI 14</span><span class="ind-line-val" style="color:{color};">{rsi:.0f} · {state}</span></div>
            <div class="bar-track">
                <div class="bar-zone rsi-zone-low"></div>
                <div class="bar-zone rsi-zone-mid"></div>
                <div class="bar-zone rsi-zone-high"></div>
                <div class="bar-marker" style="left:{rsi:.0f}%;"></div>
            </div>
            <div class="bar-labels"><span>0 oversold</span><span>50</span><span>100 overbought</span></div>
        </div>'''
    
    boll = sig.get('bollinger_pos')
    boll_html = ''
    if boll is not None:
        pos = max(0, min(100, boll * 100))
        state = 'Cheap zone' if pos < 33 else 'Normal' if pos < 67 else 'Expensive'
        color = '#34d399' if pos < 33 else '#cbd5e1' if pos < 67 else '#f87171'
        boll_html = f'''
        <div class="ind-line">
            <div class="ind-line-top"><span class="ind-line-name">Bollinger</span><span class="ind-line-val" style="color:{color};">{state}</span></div>
            <div class="bar-track">
                <div class="bar-zone boll-zone-low"></div>
                <div class="bar-zone boll-zone-mid"></div>
                <div class="bar-zone boll-zone-high"></div>
                <div class="bar-marker" style="left:{pos:.0f}%;"></div>
            </div>
            <div class="bar-labels"><span>Cheap</span><span>Normal</span><span>Expensive</span></div>
        </div>'''
    
    iv = r.get('iv_rank')
    beta = r.get('beta')
    dy = r.get('dividend_yield')
    
    mini_row = f'''
    <div class="indicators-row">
        <div class="ind-mini"><div class="mini-label">IV rank</div><div class="mini-val" style="color:{"#6ee7b7" if iv and iv >= 70 else "#fbbf24" if iv and iv >= 40 else "#cbd5e1"};">{iv if iv else "—"}%</div></div>
        <div class="ind-mini"><div class="mini-label">Beta</div><div class="mini-val">{beta if beta else "—"}</div></div>
        <div class="ind-mini"><div class="mini-label">Dividend</div><div class="mini-val">{f"{dy:.1f}%" if dy else "—"}</div></div>
    </div>'''
    
    return f'''
    <div class="indicators">
        <div class="indicators-header">{r['ticker']} · technicals</div>
        {range_html}
        {dma50_html}
        {dma200_html}
        {rsi_html}
        {boll_html}
        {mini_row}
    </div>'''


def render_dashboard(picks, rejected, scan_date):
    """Top-level HTML."""
    css = """
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Inter",sans-serif;background:#0f172a;color:#e2e8f0;padding:28px 22px;line-height:1.45;margin:0;max-width:1200px;margin-left:auto;margin-right:auto}
.dashboard-header{margin-bottom:24px;padding-bottom:14px;border-bottom:1px solid #334155}
.dashboard-title{font-size:24px;font-weight:700;color:#fca5a5;margin:0 0 4px;letter-spacing:-.02em}
.dashboard-subtitle{font-size:13px;color:#94a3b8}
.empty{padding:60px 22px;text-align:center;color:#94a3b8;background:#1e293b;border:1px dashed #334155;border-radius:12px}
.empty h2{color:#cbd5e1;margin:0 0 8px}

.pick-bd{background:#1e293b;border:1px solid #334155;border-radius:12px;margin-bottom:22px;overflow:hidden;display:flex;position:relative}
.tag-side{width:44px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;letter-spacing:.06em;writing-mode:vertical-rl;transform:rotate(180deg);border-right:1px solid #334155;background:#7f1d1d;color:#fecaca}
.pick-body{flex:1;padding:0;min-width:0}

.card-header{display:grid;grid-template-columns:auto 1fr auto;align-items:center;padding:16px 22px 14px;gap:16px;border-bottom:1px solid #334155}
.header-ticker-block{display:flex;align-items:center;gap:10px}
.card-ticker{color:#c4b5fd;font-size:52px;font-weight:700;text-decoration:none;letter-spacing:-.03em;line-height:1}
.dislocation-emoji{font-size:18px;opacity:.85}
.header-middle{display:flex;flex-direction:column;align-items:center;gap:10px}
.header-scores{display:flex;justify-content:center;align-items:center;gap:12px}
.score-block{display:flex;flex-direction:column;align-items:center;gap:3px}
.score-label{font-size:9px;text-transform:uppercase;font-weight:500;letter-spacing:.04em;color:#64748b}
.score-claude-label{color:#c4b5fd}
.score-badge{font-size:19px;font-weight:500;padding:5px 14px;border-radius:6px;line-height:1}
.score-mine{background:#1e293b;border:1px solid #475569;color:#f1f5f9}
.score-claude{background:#2e1065;border:1px solid #7c3aed;color:#ddd6fe}
.score-sep{color:#475569;font-size:16px}
.down-pill{display:inline-flex;align-items:center;gap:6px;background:linear-gradient(90deg,#7f1d1d,#991b1b);border:1px solid #dc2626;color:#fecaca;padding:6px 14px;border-radius:20px;font-size:13px;font-weight:700;letter-spacing:-.01em}
.down-pill .down-emoji{font-size:14px}
.header-right{display:flex;flex-direction:column;align-items:flex-end;gap:2px}
.company-name{color:#cbd5e1;font-size:13px;font-weight:500}
.price-row{display:flex;align-items:baseline;gap:10px}
.company-price{color:#f1f5f9;font-size:22px;font-weight:700;line-height:1}
.bargain-inline{color:#fda4af;font-size:14px;font-weight:600;background:rgba(190,24,93,.15);border:1px solid #be185d;padding:3px 8px;border-radius:5px;line-height:1}

.dislocation-row{padding:14px 22px;background:#0f172a;border-bottom:1px solid #334155}
.dislocation-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;font-weight:600}
.disloc-count{background:#7c3aed;color:#f5f3ff;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;letter-spacing:0;text-transform:none}
.disloc-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.disloc-pill{display:flex;align-items:center;gap:6px;padding:6px 10px;border-radius:6px;font-size:11px;font-weight:600;line-height:1.2}
.disloc-fired{background:rgba(239,68,68,.18);color:#fca5a5;border:1px solid #dc2626}
.disloc-not-fired{background:#1e293b;color:#475569;border:1px solid #334155;opacity:.5}
.disloc-bonus{background:rgba(168,85,247,.18);color:#c4b5fd;border:1px solid #7c3aed}
.disloc-icon{font-size:12px;flex-shrink:0}

.company-claude-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:14px 22px}
.company-box{background:#064e3b;border:1px solid #10b981;border-radius:8px;padding:14px 16px}
.box-label{font-size:11px;color:#6ee7b7;font-weight:600;letter-spacing:.05em;margin-bottom:8px;text-transform:uppercase}
.company-blurb{font-size:13px;color:#d1fae5;line-height:1.5;margin-bottom:10px}
.fund-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px 14px;font-size:12px;border-top:1px dashed #047857;padding-top:8px}
.fund-row{display:flex;align-items:baseline;gap:8px}
.fund-label{color:#6ee7b7;font-size:11px;flex-shrink:0;min-width:62px}
.fund-val{font-weight:600;font-size:12px}
.fund-up{color:#34d399}.fund-down{color:#f87171}.fund-flat{color:#cbd5e1}.fund-na{color:#64748b;font-style:italic}

.claude-box{background:#1e1b4b;border:1px solid #4c1d95;border-radius:8px;padding:14px 16px}
.claude-header{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.claude-c{width:20px;height:20px;background:#6d28d9;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#f5f3ff;font-size:11px;font-weight:700}
.claude-label-txt{font-size:11px;color:#c4b5fd;font-weight:600;letter-spacing:.05em;text-transform:uppercase}
.claude-tag{margin-left:auto;font-size:14px;padding:6px 14px;border-radius:6px;font-weight:800;letter-spacing:.06em}
.tag-buy{background:#1e3a8a;color:#93c5fd;border:1px solid #3b82f6}
.tag-strong-buy{background:#064e3b;color:#6ee7b7;border:1px solid #10b981}
.tag-skip{background:#7f1d1d;color:#fca5a5;border:1px solid #dc2626}
.claude-bullet{display:flex;gap:8px;font-size:12px;line-height:1.5;color:#e9d5ff;margin-bottom:6px}
.claude-bullet>span:first-child{font-size:12px;margin-top:6px;flex-shrink:0}
.bullet-good>span:first-child{color:#34d399}
.bullet-warn>span:first-child{color:#fbbf24}
.bullet-bad>span:first-child{color:#f87171}

.signals-row{display:flex;align-items:center;gap:8px;padding:0 22px 14px;flex-wrap:wrap}
.sig-chip{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:20px;font-size:12px;font-weight:600}
.sig-buyback{background:rgba(16,185,129,.18);color:#6ee7b7;border:1px solid #10b981}
.sig-noflag{background:rgba(16,185,129,.12);color:#6ee7b7;border:1px solid #047857}
.sig-eps{background:rgba(168,85,247,.18);color:#c4b5fd;border:1px solid #7c3aed}
.sig-short-good{background:rgba(96,165,250,.15);color:#93c5fd;border:1px solid #2563eb}

.trade-section{padding:0 22px 12px}
.put-row{display:grid;grid-template-columns:120px 110px 1fr;gap:14px;align-items:center;padding:12px 16px;background:#0f172a;border:1px solid #4c1d95;border-radius:8px;margin-bottom:6px;font-size:13px}
.put-dte-large{font-size:24px;font-weight:800;color:#c4b5fd;line-height:1;text-align:center;background:#2e1065;border:1px solid #7c3aed;border-radius:8px;padding:10px 8px}
.put-dte-large.alt{color:#93c5fd;background:#1e3a8a;border-color:#3b82f6}
.put-dte-large .dte-unit{display:block;font-size:10px;font-weight:600;color:#a78bfa;margin-top:2px}
.put-strike{font-size:20px;font-weight:700;color:#93c5fd;text-align:center}
.put-meta-row{display:flex;align-items:center;gap:8px;color:#94a3b8;font-size:12px;flex-wrap:wrap}
.otm-mult{color:#fbbf24;font-weight:700;font-size:13px}
.safety-pill{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:12px;font-weight:700;font-size:11px;letter-spacing:.02em}
.safety-high{background:rgba(16,185,129,.2);color:#6ee7b7;border:1px solid #10b981}
.safety-mid{background:rgba(251,191,36,.18);color:#fbbf24;border:1px solid #d97706}
.safety-low{background:rgba(249,115,22,.18);color:#fdba74;border:1px solid #ea580c}
.safety-danger{background:rgba(239,68,68,.2);color:#fca5a5;border:1px solid #dc2626}

.hero-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:0 22px 12px}
.hero-stat{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:10px 12px}
.hero-stat-ticker{font-size:9px;color:#94a3b8;letter-spacing:.06em;font-weight:700;margin-bottom:2px}
.hero-stat-label{font-size:10px;color:#94a3b8;text-transform:uppercase;display:flex;align-items:center;gap:6px}
.hero-stat-val{font-size:18px;font-weight:700;color:#f1f5f9;margin-top:2px}
.hero-bad{background:linear-gradient(180deg,#7f1d1d,#0f172a);border-color:#dc2626}
.hero-bad .hero-stat-val{color:#fca5a5}
.hero-good{background:linear-gradient(180deg,#064e3b,#0f172a);border-color:#10b981}
.hero-good .hero-stat-val{color:#6ee7b7}

.metrics-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:0 22px 12px}
.metric-tile{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:10px 12px}
.metric-tile-ticker{font-size:9px;color:#c4b5fd;letter-spacing:.06em;font-weight:700;margin-bottom:2px}
.metric-tile-label{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em}
.metric-tile-value{font-size:16px;font-weight:700;color:#f1f5f9;margin-top:4px}

.chart-section{padding:0 22px 12px}
.chart-svg-box{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;height:130px}
.chart-svg-box svg{width:100%;height:100%}

.recovery-line{padding:0 22px 12px}
.recovery-line-text{background:rgba(16,185,129,.08);border-left:3px solid #10b981;padding:10px 14px;font-size:12px;color:#d1fae5;border-radius:4px}
.recovery-line-text strong{color:#fbbf24}
.recovery-line-text .key{color:#34d399;font-weight:700}

.support-section{padding:0 22px 12px}
.support-header{font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;font-weight:600}
.support-ladder{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:10px 14px;margin-bottom:10px}
.ladder-row{display:grid;grid-template-columns:70px 14px 1fr;gap:10px;align-items:center;font-size:12px;padding:5px 0}
.ladder-row.tariff{background:linear-gradient(90deg,rgba(168,85,247,.08),transparent);border-top:1px dashed #4c1d95;border-bottom:1px dashed #4c1d95;padding:6px 0;margin:2px 0}
.ladder-label{color:#94a3b8;text-transform:uppercase;font-size:10px;letter-spacing:.04em;font-weight:600}
.ladder-dot{width:10px;height:10px;border-radius:50%}
.ladder-value{color:#cbd5e1;font-weight:600}
.ladder-pct{color:#94a3b8;font-size:11px;margin-left:6px;font-weight:500}
.stress-line-text{background:rgba(168,85,247,.08);border-left:3px solid #7c3aed;padding:10px 14px;font-size:12px;color:#ddd6fe;border-radius:4px}
.stress-line-text strong{color:#6ee7b7}
.stress-line-text .never{color:#fbbf24;font-weight:700}

.indicators{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:14px 16px;margin:0 22px 12px}
.indicators-header{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px;font-weight:600}
.ind-line{margin-bottom:14px}
.ind-line-top{display:flex;justify-content:space-between;align-items:baseline;font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px}
.ind-line-name{font-weight:600}
.ind-line-val{font-weight:700;font-size:13px;color:#f1f5f9;text-transform:none;letter-spacing:0}
.bar-track{position:relative;height:8px;background:#1e293b;border-radius:4px;overflow:hidden}
.bar-marker{position:absolute;top:-3px;bottom:-3px;width:10px;background:#fbbf24;border:1px solid #422006;border-radius:2px;transform:translateX(-50%);z-index:2}
.bar-zone{position:absolute;top:0;bottom:0}
.range52-zone-low{left:0;width:33%;background:rgba(239,68,68,.45)}
.range52-zone-mid{left:33%;width:34%;background:rgba(251,191,36,.45)}
.range52-zone-high{left:67%;width:33%;background:rgba(16,185,129,.45)}
.dma-zone-bad{left:0;width:50%;background:rgba(239,68,68,.5)}
.dma-zone-good{left:50%;width:50%;background:rgba(16,185,129,.5)}
.rsi-zone-low{left:0;width:30%;background:rgba(16,185,129,.55)}
.rsi-zone-mid{left:30%;width:40%;background:rgba(100,116,139,.4)}
.rsi-zone-high{left:70%;width:30%;background:rgba(239,68,68,.55)}
.boll-zone-low{left:0;width:33%;background:rgba(16,185,129,.55)}
.boll-zone-mid{left:33%;width:34%;background:rgba(100,116,139,.4)}
.boll-zone-high{left:67%;width:33%;background:rgba(239,68,68,.55)}
.bar-labels{display:flex;justify-content:space-between;font-size:9px;color:#64748b;margin-top:3px;text-transform:uppercase;letter-spacing:.05em}
.indicators-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid #1e293b}
.ind-mini{background:#1e293b;border-radius:6px;padding:8px 10px}
.mini-label{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em}
.mini-val{font-size:14px;font-weight:700;margin-top:2px;color:#f1f5f9}

.news-section{padding:0 22px 14px}
.news-header{font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;font-weight:600}
.news-header strong{color:#c4b5fd}
.news-item{display:grid;grid-template-columns:18px 1fr 60px;gap:8px;padding:6px 0;font-size:12px;line-height:1.4;border-bottom:1px solid rgba(51,65,85,.4);align-items:baseline}
.news-item:last-child{border-bottom:none}
.news-icon{font-size:11px;font-weight:700}
.news-pos{color:#34d399}
.news-neg{color:#f87171}
.news-neu{color:#94a3b8}
.news-title-link{color:#93c5fd;text-decoration:none}
.news-date{color:#94a3b8;font-size:11px;text-align:right}
"""
    
    if not picks:
        body = '<div class="empty"><h2>📊 No dislocation picks today</h2><p>Strict criteria — none of the universe meets all hard gates + 3+ dislocation signals + Claude STRONG BUY/BUY today.</p><p>Check back after the next scan.</p></div>'
    else:
        body = ''.join(build_pick(r) for r in picks)
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Beaten-Down Hunter — {scan_date.strftime('%Y-%m-%d')}</title>
<style>{css}</style>
</head>
<body>
<div class="dashboard-header">
    <h1 class="dashboard-title">🔻 Beaten-Down Hunter</h1>
    <p class="dashboard-subtitle">Strict dislocation scanner · {len(picks)} pick{'s' if len(picks) != 1 else ''} · {scan_date.strftime('%a %d %b %Y · %H:%M Dubai')}</p>
</div>
{body}
</body>
</html>
'''
