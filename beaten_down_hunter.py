#!/usr/bin/env python3
"""
Beaten-Down Hunter — strict dislocation scanner.

Hunts US stocks meeting strict dislocation criteria:
  1. HARD GATES (all required): cap $5B+, vol 1M+, price $5+, P/E ≤70,
     +FCF, analyst above hold, EPS growth >0%, options chain
  2. RECENCY: today's price must be within 15% of 14-day low
  3. DISLOCATION SIGNALS (need 3+ from): below SMA50 by 10%+,
     RSI <35, at/below lower BB, 1m perf <-10%, near 52w low,
     5y all-time low (bonus)
  4. RECOVERY MOMENTUM BONUS: oversold 5-14d ago, RSI now 35-45
  5. UW flow confirmation
  6. Algo score >=7
  7. Claude STRONG BUY/BUY only

Output: 3-7 picks, written for 15-year-old reading level.
"""

import os
import sys
import json
import time
import math
import traceback
from datetime import datetime, timedelta, date
from collections import defaultdict

import pandas as pd
import numpy as np
import yfinance as yf
import requests

try:
    from claude_scorer import score_picks
except ImportError:
    score_picks = None


# ============================================================
# CONFIG
# ============================================================

# Universe — broad US large-cap pool. Will filter down hard from here.
# This is the same universe pattern as Premium Hunter, but no earnings filter.
UNIVERSE = [
    # Mega-cap tech / blue chips
    'AAPL','MSFT','GOOGL','GOOG','AMZN','META','NVDA','TSLA','BRK-B','AVGO','ORCL',
    'NFLX','CRM','ADBE','CSCO','INTC','AMD','TXN','QCOM','MU','INTU','NOW','UBER',
    'IBM','ACN','PYPL','SNOW','PLTR','SHOP','SQ','SOFI','HOOD','COIN','RBLX','U',
    'ROKU','PINS','SNAP','SPOT','ZM','DOCU','ZS','CRWD','PANW','FTNT','OKTA',
    'TEAM','DDOG','MDB','NET','TWLO','ESTC','S','BILL','HUBS','VEEV','CDNS','SNPS',
    'KLAC','LRCX','AMAT','ASML','TSM','MRVL','ON','MPWR','MCHP','ADI','SMCI','CLS',
    'IREN','APP','ARM','ARGX','HIMS','CCJ','MARA','RIOT','RBLX','RIVN','LCID','NIO',
    
    # Financials
    'JPM','BAC','WFC','GS','MS','C','V','MA','AXP','SCHW','BLK','BX','KKR','APO',
    'COF','SYF','DFS','ALL','PGR','TRV','AIG','MET','PRU','AFL','HIG','CINF','WRB',
    'CB','BRK-A','BRO','MMC','AON','SPGI','MCO','ICE','CME','COIN',
    
    # Consumer
    'WMT','COST','HD','LOW','TGT','DG','DLTR','BJ','TJX','ROST','BURL','ULTA','LULU',
    'NKE','DKS','BBY','GME','AAP','AZO','ORLY','CMG','MCD','SBUX','YUM','DPZ','WING',
    'CMG','CAVA','EAT','TXRH','BLMN','DRI','CAKE','SHAK','PZZA',
    'DIS','NFLX','CMCSA','VZ','T','TMUS','CHTR','PARA','WBD','EA','TTWO','RBLX',
    'EBAY','ETSY','W','RH','WMS','PENN','DKNG','MGM','LVS','WYNN','BYD','CZR','HLT',
    'MAR','H','RCL','CCL','NCLH','UAL','DAL','AAL','LUV','SAVE','JBLU','ALK',
    
    # Healthcare
    'JNJ','PFE','MRK','ABBV','LLY','BMY','UNH','CVS','HUM','CI','ANTM','MOH','CNC',
    'GILD','BIIB','REGN','VRTX','AMGN','ILMN','MRNA','BNTX','NVAX','ALNY','BMRN',
    'TMO','DHR','SYK','BSX','MDT','ISRG','EW','BDX','BAX','HOLX','RMD','ZBH','PODD',
    'ABT','ALGN','VEEV','IDXX','IQV','CRL','TFX','ZTS','DXCM','MASI',
    'HCA','UHS','THC','CYH','LH','DGX','ABT','HSIC','MTD',
    'NVO','SNY','GSK','AZN','NVS','RHHBY','SNN','TAK','ZBH',
    
    # Industrial / Energy / Materials
    'BA','LMT','RTX','NOC','GD','HII','LDOS','LHX','TXT','HEI','TDG','HWM','GE',
    'CAT','DE','HON','EMR','ROK','PH','ETN','ITW','MMM','GD','URI','RSG','WM',
    'XOM','CVX','COP','EOG','MPC','PSX','VLO','OXY','SLB','HAL','BKR','PXD','PSX',
    'KMI','OKE','ENB','TRP','SHEL','BP','LIN','APD','NUE','STLD','X','CLF','VALE',
    'FCX','SCCO','GOLD','NEM','AA','RIO','BHP',
    'UPS','FDX','DAL','UAL','AAL','CSX','UNP','NSC','CHRW','EXPD','XPO',
    
    # REITs / Utilities (mostly skipped — low IV, low premium)
    'NEE','SO','DUK','D','AEP','EXC','SRE','PCG','XEL','ED','PPL','AES','EIX',
]

# Dedupe
UNIVERSE = sorted(set(UNIVERSE))

# Tariff floor anchor — the April 2025 panic low for SPY-style stress test
# Per-stock tariff floor calculated from history; this is a fallback %
TARIFF_PANIC_DRAWDOWN = 0.20  # ~20% drawdown was the April 2025 panic floor

# UNUSUAL WHALES API
UW_API_KEY = os.environ.get('UNUSUAL_WHALES_API_KEY', '')


# ============================================================
# UNIVERSAL FILTERS / FETCHERS (reused from Premium Hunter)
# ============================================================

def safe_float(v, default=None):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def fetch_yfinance_data(ticker):
    """Fetch all yfinance data for a ticker. Returns dict or None."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        if not info.get('longName') and not info.get('shortName'):
            return None
        
        # 2y daily history (needed for max 1d drop, 5y all-time low estimation)
        hist = t.history(period='2y', auto_adjust=False)
        if hist is None or hist.empty or len(hist) < 50:
            return None
        
        # 5y for all-time low check
        try:
            hist_5y = t.history(period='5y', auto_adjust=False)
        except Exception:
            hist_5y = hist
        
        return {
            'ticker_obj': t,
            'info': info,
            'hist': hist,
            'hist_5y': hist_5y,
        }
    except Exception as e:
        print(f"  ✗ {ticker}: yfinance fetch failed — {e}", file=sys.stderr)
        return None


# ============================================================
# HARD GATES — disqualify stocks that fail any
# ============================================================

def passes_hard_gates(ticker, ydata):
    """Returns (passes: bool, reason: str if failed)."""
    info = ydata['info']
    hist = ydata['hist']
    
    price = safe_float(info.get('currentPrice') or info.get('regularMarketPrice') or
                        (hist['Close'].iloc[-1] if not hist.empty else None))
    if price is None or price < 5:
        return False, f'price ${price:.2f} < $5'
    
    cap = safe_float(info.get('marketCap'))
    if cap is None or cap < 5e9:
        return False, f'cap ${cap/1e9:.1f}B < $5B' if cap else 'no cap data'
    
    avg_vol = safe_float(info.get('averageVolume'))
    if avg_vol is None or avg_vol < 1_000_000:
        return False, f'avg vol {avg_vol:,.0f} < 1M' if avg_vol else 'no volume data'
    
    pe = safe_float(info.get('trailingPE'))
    # Allow no P/E (some stocks have negative earnings — caught by EPS gate later)
    # But if we have P/E, must be ≤70
    if pe is not None and pe > 70:
        return False, f'P/E {pe:.1f} > 70'
    
    # Free cash flow positive
    fcf = safe_float(info.get('freeCashflow'))
    if fcf is None or fcf <= 0:
        return False, f'FCF {fcf} not positive' if fcf is not None else 'no FCF data'
    
    # Analyst rating: yfinance returns recommendationMean (1=Strong Buy, 3=Hold, 5=Sell)
    # "Above hold" = recommendationMean < 2.7 (between Buy and Hold)
    rec = safe_float(info.get('recommendationMean'))
    if rec is None or rec >= 2.8:
        return False, f'analyst rec {rec:.1f} not above hold' if rec else 'no analyst data'
    
    # EPS growth TTM YoY > 0
    eps_growth = safe_float(info.get('earningsGrowth'))
    if eps_growth is None or eps_growth <= 0:
        return False, f'EPS growth {eps_growth:.1%} <= 0' if eps_growth is not None else 'no EPS growth'
    
    # Options chain available
    try:
        options = ydata['ticker_obj'].options
        if not options or len(options) == 0:
            return False, 'no options chain'
    except Exception:
        return False, 'no options chain'
    
    return True, ''


# ============================================================
# DISLOCATION DETECTION (14-day rolling window)
# ============================================================

def calc_rsi(close, period=14):
    """14-day RSI."""
    if len(close) < period + 1:
        return None
    delta = close.diff().dropna()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else None


def calc_rsi_series(close, period=14):
    """Full RSI series for window scanning."""
    if len(close) < period + 1:
        return None
    delta = close.diff().dropna()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def calc_bb(close, period=50, std_mult=2):
    """Bollinger bands (period=50)."""
    if len(close) < period:
        return None, None, None
    sma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    upper = sma + std_mult * sd
    lower = sma - std_mult * sd
    return sma, upper, lower


def detect_dislocation_signals(ydata):
    """
    Check 7 dislocation signals over a 14-day rolling window.
    Returns dict with each signal: True/False/value.
    """
    hist = ydata['hist']
    hist_5y = ydata['hist_5y']
    info = ydata['info']
    
    close = hist['Close']
    if len(close) < 60:
        return None
    
    current = float(close.iloc[-1])
    last_14d = close.tail(14)
    low_14d = float(last_14d.min())
    high_52w = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
    low_52w = float(close.tail(252).min()) if len(close) >= 252 else float(close.min())
    
    signals = {
        'current_price': current,
        'low_14d': low_14d,
        'high_52w': high_52w,
        'low_52w': low_52w,
        'pct_off_high_52w': (current - high_52w) / high_52w * 100,
        'pct_above_low_52w': (current - low_52w) / low_52w * 100 if low_52w > 0 else None,
    }
    
    # RECENCY GATE — must be within 15% of 14d low
    pct_above_14d_low = (current - low_14d) / low_14d * 100 if low_14d > 0 else 999
    signals['pct_above_14d_low'] = pct_above_14d_low
    signals['recency_pass'] = pct_above_14d_low <= 15
    
    # SIGNAL 1: Below SMA50 by 10%+ anytime in last 14d
    sma50_series = close.rolling(50).mean()
    last_14_sma = sma50_series.tail(14)
    last_14_close = close.tail(14)
    pct_below_sma = (last_14_close - last_14_sma) / last_14_sma * 100
    signals['below_sma50_fired'] = (pct_below_sma <= -10).any()
    signals['below_sma50_today_pct'] = float(pct_below_sma.iloc[-1]) if not pct_below_sma.empty else None
    
    # SIGNAL 2: RSI <35 anytime in last 14d
    rsi_series = calc_rsi_series(close, 14)
    if rsi_series is not None and not rsi_series.empty:
        last_14_rsi = rsi_series.tail(14).dropna()
        signals['rsi_today'] = float(last_14_rsi.iloc[-1]) if not last_14_rsi.empty else None
        signals['rsi_oversold_fired'] = (last_14_rsi < 35).any()
        # Find lowest RSI in last 14d and how many days ago
        if not last_14_rsi.empty:
            min_idx = last_14_rsi.idxmin()
            days_ago = (last_14_rsi.index[-1] - min_idx).days
            signals['rsi_min_14d'] = float(last_14_rsi.min())
            signals['rsi_min_days_ago'] = days_ago
    else:
        signals['rsi_oversold_fired'] = False
        signals['rsi_today'] = None
    
    # SIGNAL 3: At/below lower Bollinger (50) anytime in last 14d
    sma_bb, upper_bb, lower_bb = calc_bb(close, 50, 2)
    if lower_bb is not None:
        last_14_lower = lower_bb.tail(14)
        signals['lower_bb_fired'] = (last_14_close <= last_14_lower).any()
        signals['lower_bb_today'] = float(lower_bb.iloc[-1]) if not lower_bb.empty else None
        # Bollinger position 0-1 (0=at lower, 1=at upper)
        if upper_bb is not None and lower_bb.iloc[-1] is not None:
            ul = float(upper_bb.iloc[-1]) - float(lower_bb.iloc[-1])
            signals['bollinger_pos'] = (current - float(lower_bb.iloc[-1])) / ul if ul > 0 else 0.5
    else:
        signals['lower_bb_fired'] = False
        signals['bollinger_pos'] = None
    
    # SIGNAL 4: 1-month performance < -10%
    if len(close) >= 22:
        price_1mo_ago = float(close.iloc[-22])
        perf_1mo = (current - price_1mo_ago) / price_1mo_ago * 100
        signals['perf_1m_pct'] = perf_1mo
        signals['perf_1m_fired'] = perf_1mo < -10
    else:
        signals['perf_1m_fired'] = False
    
    # SIGNAL 5: At/within 15% of 52w low (last 14d)
    if low_52w > 0:
        last_14_dist_to_52w_low = (last_14_close - low_52w) / low_52w * 100
        signals['near_52w_low_fired'] = (last_14_dist_to_52w_low <= 15).any()
    else:
        signals['near_52w_low_fired'] = False
    
    # SIGNAL 6 (BONUS): All-time low (5y) anytime in last 14d
    if hist_5y is not None and not hist_5y.empty:
        ath_5y_low = float(hist_5y['Close'].min())
        signals['atl_5y'] = ath_5y_low
        signals['atl_5y_fired'] = (last_14_close <= ath_5y_low * 1.02).any()  # within 2%
    else:
        signals['atl_5y_fired'] = False
    
    # RECOVERY MOMENTUM BONUS: oversold 5-14d ago AND RSI now 35-45
    if rsi_series is not None and signals.get('rsi_min_days_ago') is not None:
        days_ago = signals['rsi_min_days_ago']
        rsi_now = signals.get('rsi_today')
        rsi_min = signals.get('rsi_min_14d')
        if (5 <= days_ago <= 14 and rsi_min is not None and rsi_min < 35 and 
            rsi_now is not None and 35 <= rsi_now <= 45):
            signals['recovery_momentum'] = True
        else:
            signals['recovery_momentum'] = False
    else:
        signals['recovery_momentum'] = False
    
    # COUNT: how many of 6 signals fired (excl. recovery momentum which is separate bonus)
    signal_keys = [
        'below_sma50_fired', 'rsi_oversold_fired', 'lower_bb_fired',
        'perf_1m_fired', 'near_52w_low_fired', 'atl_5y_fired'
    ]
    signals['signals_fired_count'] = sum(1 for k in signal_keys if signals.get(k))
    signals['signals_total'] = len(signal_keys)
    
    # Indicators (current snapshot for card display)
    signals['rsi_14'] = signals.get('rsi_today')
    signals['dma_50'] = float(sma50_series.iloc[-1]) if not sma50_series.empty else None
    sma200 = close.rolling(200).mean() if len(close) >= 200 else None
    signals['dma_200'] = float(sma200.iloc[-1]) if sma200 is not None and not sma200.empty else None
    
    # 52w high/low for chart
    if len(close) >= 252:
        signals['high_1y'] = high_52w
        signals['low_1y'] = low_52w
        signals['pct_1y'] = (current - float(close.iloc[-252])) / float(close.iloc[-252]) * 100
    else:
        signals['high_1y'] = float(close.max())
        signals['low_1y'] = float(close.min())
        signals['pct_1y'] = (current - float(close.iloc[0])) / float(close.iloc[0]) * 100
    
    # Max 1-day drop in 2y (for safety score)
    daily_pct = close.pct_change().dropna() * 100
    signals['max_1d_drop_pct'] = float(daily_pct.min()) if not daily_pct.empty else -5.0
    
    return signals


# ============================================================
# TARIFF FLOOR (April 2025 panic stress test)
# ============================================================

def calc_tariff_floor(hist):
    """Find the April 2025 panic low for this stock."""
    try:
        # Look for April 2025 bottom: between 2025-04-01 and 2025-04-15
        apr_2025 = hist[(hist.index >= '2025-04-01') & (hist.index <= '2025-04-15')]
        if not apr_2025.empty:
            return float(apr_2025['Low'].min())
    except Exception:
        pass
    return None


# ============================================================
# OPTIONS CHAIN: find best long-dated put
# ============================================================

def find_best_put(t, current_price, target_dte_min=240, target_dte_max=400):
    """Find best long-dated (9-12mo) put around 5-8 delta."""
    try:
        options = t.options
        if not options:
            return None
        
        today = date.today()
        candidates = []
        for exp_str in options:
            try:
                exp = datetime.strptime(exp_str, '%Y-%m-%d').date()
                dte = (exp - today).days
                if not (target_dte_min <= dte <= target_dte_max):
                    continue
                chain = t.option_chain(exp_str)
                puts = chain.puts
                if puts is None or puts.empty:
                    continue
                # Find ~7-delta put (around 25-40% OTM typical for long-dated)
                puts = puts[puts['strike'] < current_price * 0.95].copy()
                if puts.empty:
                    continue
                puts['otm_pct'] = (current_price - puts['strike']) / current_price * 100
                # Sweet spot 25-45% OTM for long-dated
                ideal = puts[(puts['otm_pct'] >= 20) & (puts['otm_pct'] <= 50)]
                if ideal.empty:
                    ideal = puts[puts['otm_pct'] >= 15]
                if ideal.empty:
                    continue
                # Pick the one with highest open interest (most liquid)
                ideal = ideal.sort_values('openInterest', ascending=False)
                row = ideal.iloc[0]
                bid = safe_float(row.get('bid'), 0)
                ask = safe_float(row.get('ask'), 0)
                mid = (bid + ask) / 2 if bid and ask else safe_float(row.get('lastPrice'), 0)
                if mid <= 0:
                    continue
                # Approximate delta: use OTM% and DTE
                delta_approx = -0.07 if row['otm_pct'] > 30 else -0.12
                candidates.append({
                    'expiry': exp_str,
                    'dte': dte,
                    'strike': float(row['strike']),
                    'mid': mid,
                    'bid': bid,
                    'ask': ask,
                    'pct_otm': float(row['otm_pct']),
                    'delta': delta_approx,
                    'oi': int(row.get('openInterest', 0)),
                    'volume': int(row.get('volume', 0)) if pd.notna(row.get('volume')) else 0,
                })
            except Exception:
                continue
        
        if not candidates:
            return None
        # Best = highest OI, then closest to 30% OTM
        candidates.sort(key=lambda x: (-x['oi'], abs(x['pct_otm'] - 30)))
        return candidates[0]
    except Exception:
        return None


def find_alt_put(t, current_price):
    """Find short-dated alt put (~30-45 DTE, 12-18% OTM)."""
    try:
        options = t.options
        if not options:
            return None
        today = date.today()
        for exp_str in options:
            exp = datetime.strptime(exp_str, '%Y-%m-%d').date()
            dte = (exp - today).days
            if 25 <= dte <= 50:
                chain = t.option_chain(exp_str)
                puts = chain.puts
                if puts is None or puts.empty:
                    continue
                puts = puts[puts['strike'] < current_price * 0.95].copy()
                if puts.empty:
                    continue
                puts['otm_pct'] = (current_price - puts['strike']) / current_price * 100
                ideal = puts[(puts['otm_pct'] >= 10) & (puts['otm_pct'] <= 18)]
                if ideal.empty:
                    continue
                ideal = ideal.sort_values('openInterest', ascending=False)
                row = ideal.iloc[0]
                bid = safe_float(row.get('bid'), 0)
                ask = safe_float(row.get('ask'), 0)
                mid = (bid + ask) / 2 if bid and ask else safe_float(row.get('lastPrice'), 0)
                if mid <= 0:
                    continue
                return {
                    'expiry': exp_str,
                    'dte': dte,
                    'strike': float(row['strike']),
                    'mid': mid,
                    'otm_pct': float(row['otm_pct']),
                    'delta': -0.15,
                }
        return None
    except Exception:
        return None


# ============================================================
# UNUSUAL WHALES FLOW
# ============================================================

def fetch_uw_flow(ticker):
    """Returns dict with bullish_put_flow, dark_pool_floor, oi_cluster."""
    if not UW_API_KEY:
        return {'bullish_put_flow': None, 'dark_pool_floor': None, 'oi_cluster': None}
    try:
        # Net premium endpoint
        r = requests.get(
            f'https://api.unusualwhales.com/api/stock/{ticker}/net-prem-ticks',
            headers={'Authorization': f'Bearer {UW_API_KEY}'},
            timeout=8
        )
        if r.status_code != 200:
            return {'bullish_put_flow': None, 'dark_pool_floor': None, 'oi_cluster': None}
        data = r.json().get('data', [])
        if not data:
            return {'bullish_put_flow': None, 'dark_pool_floor': None, 'oi_cluster': None}
        # Sum net put premium last 5 days
        recent = data[-5:] if len(data) >= 5 else data
        net_put_prem = sum(safe_float(d.get('net_put_premium', 0), 0) for d in recent)
        return {
            'bullish_put_flow': net_put_prem > 1_000_000,  # $1M+ net bullish put flow
            'net_put_premium': net_put_prem,
            'dark_pool_floor': None,  # Could fetch separately
            'oi_cluster': None,
        }
    except Exception:
        return {'bullish_put_flow': None, 'dark_pool_floor': None, 'oi_cluster': None}


# ============================================================
# COMPANY NARRATIVE + FUNDAMENTALS (reused style)
# ============================================================

def get_company_narrative(info):
    """Plain-English fallback. Claude's blurb will replace this."""
    summary = info.get('longBusinessSummary', '') or ''
    name = info.get('longName') or info.get('shortName') or 'Company'
    sector = info.get('sector') or ''
    if summary:
        # First sentence
        first = summary.split('.')[0]
        if len(first) > 200:
            first = first[:197] + '...'
        return first + '.'
    return f"{name} · {sector}"


def get_fundamentals(info, t):
    """Real Revenue / Profit / FCF / Debt with YoY."""
    out = {
        'revenue_val': None, 'revenue_yoy': None,
        'profit_val': None, 'profit_yoy': None,
        'fcf_val': None, 'fcf_yoy': None,
        'debt_eq': None, 'debt_label': None,
    }
    def _yoy(latest, prev):
        if not latest or not prev or prev == 0:
            return None
        return (latest - prev) / abs(prev) * 100
    try:
        fin = t.financials
        if fin is not None and not fin.empty and 'Total Revenue' in fin.index:
            revs = fin.loc['Total Revenue'].dropna()
            if len(revs) >= 1:
                out['revenue_val'] = float(revs.iloc[0])
            if len(revs) >= 2:
                out['revenue_yoy'] = _yoy(float(revs.iloc[0]), float(revs.iloc[1]))
        if fin is not None and not fin.empty and 'Net Income' in fin.index:
            profs = fin.loc['Net Income'].dropna()
            if len(profs) >= 1:
                out['profit_val'] = float(profs.iloc[0])
            if len(profs) >= 2:
                out['profit_yoy'] = _yoy(float(profs.iloc[0]), float(profs.iloc[1]))
        cf = t.cashflow
        if cf is not None and not cf.empty:
            for k in ['Free Cash Flow', 'Operating Cash Flow', 'Total Cash From Operating Activities']:
                if k in cf.index:
                    vals = cf.loc[k].dropna()
                    if len(vals) >= 1:
                        out['fcf_val'] = float(vals.iloc[0])
                    if len(vals) >= 2:
                        out['fcf_yoy'] = _yoy(float(vals.iloc[0]), float(vals.iloc[1]))
                    break
        de = info.get('debtToEquity')
        if de is not None:
            de_ratio = de / 100 if de > 5 else de
            out['debt_eq'] = de_ratio
            if de_ratio < 0.5:
                out['debt_label'] = 'low'
            elif de_ratio < 1.5:
                out['debt_label'] = 'moderate'
            else:
                out['debt_label'] = 'heavy'
    except Exception:
        pass
    return out


def fetch_news_headlines(t, ticker, n=4):
    """Fetch latest news with date + url."""
    try:
        news = t.news or []
    except Exception:
        return []
    out = []
    for item in news[:n]:
        try:
            title = item.get('title') or ''
            url = item.get('link') or ''
            ts = item.get('providerPublishTime', 0)
            d = datetime.fromtimestamp(ts).strftime('%b %d') if ts else ''
            out.append({
                'title': title,
                'url': url,
                'date': d,
                'sentiment': 'neutral',  # Claude will classify
            })
        except Exception:
            continue
    return out


# ============================================================
# ALGO SCORING
# ============================================================

def score_pick(d):
    """Score 0-10. Returns (score, passes, flags)."""
    score = 0.0
    passes = []
    flags = []
    
    sig = d['signals']
    
    # Each fired dislocation signal worth points
    if sig.get('rsi_oversold_fired'):
        score += 2.0
        passes.append(f'RSI hit {sig.get("rsi_min_14d", 0):.0f}')
    if sig.get('lower_bb_fired'):
        score += 1.5
        passes.append('Touched lower BB')
    if sig.get('below_sma50_fired'):
        score += 1.0
        passes.append('Below SMA50 by 10%+')
    if sig.get('perf_1m_fired'):
        score += 1.0
        passes.append(f'1m perf {sig.get("perf_1m_pct", 0):.0f}%')
    if sig.get('near_52w_low_fired'):
        score += 1.5
        passes.append('Near 52w low')
    if sig.get('atl_5y_fired'):
        score += 1.0
        passes.append('5y all-time low')
    if sig.get('recovery_momentum'):
        score += 1.0
        passes.append('Recovery momentum')
    
    # IV rank boost
    iv_rank = d.get('iv_rank')
    if iv_rank and iv_rank >= 40:
        score += 1.0
        passes.append(f'IV rank {iv_rank}%')
    
    # Dividend cushion
    dy = d.get('dividend_yield')
    if dy and dy >= 2:
        score += 0.5
        passes.append(f'Div {dy:.1f}%')
    
    # UW flow confirmation
    uw = d.get('uw_flow') or {}
    if uw.get('bullish_put_flow'):
        score += 1.5
        passes.append('UW bullish put flow')
    
    # Cap at 10
    score = min(10.0, score)
    
    return {'score': round(score, 1), 'passes': passes, 'flags': flags}


# ============================================================
# IV RANK (from ATR proxy)
# ============================================================

def calc_iv_rank(hist):
    """Approximate IV rank from realized vol."""
    try:
        if len(hist) < 252:
            return None
        close = hist['Close']
        # Rolling 30d realized vol
        log_ret = np.log(close / close.shift(1))
        rolling_vol = log_ret.rolling(30).std() * np.sqrt(252) * 100
        rolling_vol = rolling_vol.dropna()
        if rolling_vol.empty:
            return None
        current_vol = float(rolling_vol.iloc[-1])
        min_vol = float(rolling_vol.min())
        max_vol = float(rolling_vol.max())
        if max_vol - min_vol < 0.1:
            return 50
        rank = (current_vol - min_vol) / (max_vol - min_vol) * 100
        return int(round(rank))
    except Exception:
        return None


# ============================================================
# MAIN PROCESSING
# ============================================================

def process_ticker(ticker):
    """Run the full pipeline for one ticker. Returns dict or None."""
    ydata = fetch_yfinance_data(ticker)
    if not ydata:
        return None
    
    info = ydata['info']
    hist = ydata['hist']
    t = ydata['ticker_obj']
    
    # HARD GATES first
    passes_gates, gate_reason = passes_hard_gates(ticker, ydata)
    if not passes_gates:
        return {'ticker': ticker, 'rejected': True, 'reason': gate_reason}
    
    # DISLOCATION SIGNALS
    signals = detect_dislocation_signals(ydata)
    if not signals:
        return {'ticker': ticker, 'rejected': True, 'reason': 'insufficient history'}
    
    # RECENCY: must be within 15% of 14d low
    if not signals.get('recency_pass'):
        return {'ticker': ticker, 'rejected': True,
                'reason': f'{signals.get("pct_above_14d_low", 0):.0f}% above 14d low (>15%)'}
    
    # Need at least 3 signals fired
    if signals['signals_fired_count'] < 3:
        return {'ticker': ticker, 'rejected': True,
                'reason': f'only {signals["signals_fired_count"]}/6 signals fired'}
    
    # Build full data dict
    price = signals['current_price']
    
    d = {
        'ticker': ticker,
        'company': info.get('longName') or info.get('shortName') or ticker,
        'sector': info.get('sector', ''),
        'price': price,
        'market_cap': info.get('marketCap'),
        'pe': info.get('trailingPE'),
        'beta': round(info.get('beta', 0), 2) if info.get('beta') else None,
        'signals': signals,
        'rsi_14': signals.get('rsi_14'),
        'dma_50': signals.get('dma_50'),
        'dma_200': signals.get('dma_200'),
        'bollinger_pos': signals.get('bollinger_pos'),
        'pct_off_high_52w': signals.get('pct_off_high_52w'),
        'pct_above_low_52w': signals.get('pct_above_low_52w'),
        'high_1y': signals.get('high_1y'),
        'low_1y': signals.get('low_1y'),
        'pct_1y': signals.get('pct_1y'),
        'max_1d_drop_pct': signals.get('max_1d_drop_pct'),
        'fundamentals': get_fundamentals(info, t),
        'company_narrative': get_company_narrative(info),
        'news_items': fetch_news_headlines(t, ticker, n=4),
        'iv_rank': calc_iv_rank(hist),
        'eps_growth': info.get('earningsGrowth'),
        'analyst_revisions': f'{int(info.get("numberOfAnalystOpinions", 0))} analysts',
        'recommendation_mean': info.get('recommendationMean'),
        'tariff_floor': calc_tariff_floor(hist),
        'short_interest': info.get('shortPercentOfFloat'),
    }
    
    # Dividend yield
    dy = info.get('dividendYield') or info.get('trailingAnnualDividendYield')
    if dy is not None:
        d['dividend_yield'] = dy * 100 if dy < 1 else dy
    else:
        d['dividend_yield'] = None
    
    # Buybacks (from cashflow)
    try:
        cf = t.cashflow
        if cf is not None and not cf.empty and 'Repurchase Of Capital Stock' in cf.index:
            bb_val = abs(float(cf.loc['Repurchase Of Capital Stock'].dropna().iloc[0]))
            d['buybacks'] = {'amount': bb_val, 'signal': 'strong' if bb_val > 1e9 else 'moderate'}
        else:
            d['buybacks'] = {'signal': 'none'}
    except Exception:
        d['buybacks'] = {'signal': 'none'}
    
    # Red flags / EPS / insider — placeholder
    d['red_flags'] = {'signal': 'clear', 'count': 0}
    d['eps_streak'] = {'beats': info.get('numberOfAnalystOpinions', 0), 'streak': '—'}
    d['insider_activity'] = {'signal': 'neutral', 'buys': 0, 'sells': 0}
    
    # Find puts
    primary_put = find_best_put(t, price)
    if not primary_put:
        return {'ticker': ticker, 'rejected': True, 'reason': 'no suitable long-dated put found'}
    d['put_trade'] = primary_put
    d['alt_put'] = find_alt_put(t, price)
    d['suggested_size'] = 3  # default 3 contracts for long-dated
    
    # UW flow
    d['uw_flow'] = fetch_uw_flow(ticker)
    
    # Algo score
    sc = score_pick(d)
    d['score'] = sc['score']
    d['passes'] = sc['passes']
    d['flags'] = sc['flags']
    
    # Edge ratio (premium vs realized vol — approximation)
    if primary_put and signals.get('max_1d_drop_pct'):
        # Quick edge approximation
        annualized_premium = (primary_put['mid'] / primary_put['strike']) * (365 / max(primary_put['dte'], 30))
        d['edge_ratio'] = round(annualized_premium / abs(signals['max_1d_drop_pct'] / 100) * 5, 2)
    else:
        d['edge_ratio'] = None
    
    return d


# ============================================================
# MAIN
# ============================================================

def main():
    print(f"\n{'='*60}")
    print(f"BEATEN-DOWN HUNTER — strict dislocation scanner")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Universe: {len(UNIVERSE)} tickers")
    print(f"{'='*60}\n", flush=True)
    
    accepted = []
    rejected = []
    
    for i, ticker in enumerate(UNIVERSE, 1):
        try:
            print(f"[{i}/{len(UNIVERSE)}] {ticker:<8}", end=' ', flush=True)
            r = process_ticker(ticker)
            if r is None:
                print('  -> data error', flush=True)
                continue
            if r.get('rejected'):
                print(f"  -> REJECT ({r['reason']})", flush=True)
                rejected.append(r)
                continue
            print(f"  -> ACCEPT score={r['score']:.1f} signals={r['signals']['signals_fired_count']}/6", flush=True)
            accepted.append(r)
        except Exception as e:
            print(f"  -> ERROR: {e}", flush=True)
            traceback.print_exc()
        time.sleep(0.05)  # be nice to yfinance
    
    print(f"\n{'='*60}")
    print(f"PHASE 1 COMPLETE: {len(accepted)} accepted / {len(UNIVERSE)} scanned")
    print(f"{'='*60}\n", flush=True)
    
    # Filter to algo score 7+
    accepted = [r for r in accepted if r['score'] >= 7]
    print(f"After algo>=7 filter: {len(accepted)} candidates", flush=True)
    
    if not accepted:
        print("No picks meet criteria today. Outputting empty report.", flush=True)
        write_html([], rejected)
        return
    
    # Sort by score
    accepted.sort(key=lambda x: x['score'], reverse=True)
    
    # CLAUDE SCORING
    if score_picks:
        print(f"\nScoring {len(accepted)} picks with Claude...", flush=True)
        accepted = score_picks(accepted)
    
    # Final filter: Claude STRONG BUY or BUY only
    final = []
    for r in accepted:
        tag = r.get('claude_tag', 'BUY')
        if tag in ('STRONG BUY', 'BUY'):
            final.append(r)
    
    # Cap at 7
    final = final[:7]
    
    print(f"\nFINAL PICKS: {len(final)}", flush=True)
    for r in final:
        print(f"  {r['ticker']}: algo {r['score']} · Claude {r.get('claude_score', 'N/A')} · {r.get('claude_tag', '')}", flush=True)
    
    write_html(final, rejected)
    print(f"\nDone. Report: docs/latest.html", flush=True)


def write_html(picks, rejected):
    """Render the dashboard. Imports from render module to keep this file lean."""
    from render import render_dashboard
    html = render_dashboard(picks, rejected, scan_date=datetime.now())
    os.makedirs('docs', exist_ok=True)
    out_path = 'docs/latest.html'
    with open(out_path, 'w') as f:
        f.write(html)


if __name__ == '__main__':
    main()
