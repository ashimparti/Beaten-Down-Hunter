"""
Claude scorer for Beaten-Down Hunter.
Different prompt — focused on WHY beaten down + recovery thesis.
"""

import os
import json
import time
import sys

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

MODEL = "claude-opus-4-7"

SYSTEM_PROMPT = """You are giving Ash a research-note brief on a stock that has been
BEATEN DOWN and now meets dislocation criteria. Ash is a sophisticated options
trader running long-dated put-selling from Dubai on a $2.4M portfolio.

The stocks you're scoring have ALREADY passed hard quality gates (cap $5B+,
positive FCF, analyst above hold, EPS growth >0%) AND already have multiple
dislocation signals firing (RSI <35, below SMA50, near 52w low, etc).

CRITICAL — WRITING LEVEL:
Write at a 15-year-old reading level. NO finance jargon.
- "multi-year compression" → "stock been falling for years"
- "valuation re-rating" → "investors paying more for the stock"
- "secular tailwind" → "long-term boost"
- "moat" → "competitive edge"
- ALL Greek letters, "delta", "DTE", "OTM" — banned
- "fortress balance sheet" → "tons of cash, low debt"

What Ash WANTS:

1. A 2-3 sentence "what this company actually does" — explain like to a kid.
   NO yfinance boilerplate. Real products, segments, what makes them money.

2. 3-4 catalyst bullets focused on:
   - WHY is this stock beaten down right now? (specific reason, not generic)
   - What could turn it around? (catalysts, products, deals)
   - Real risks an outsider might miss
   - Use plain language

Return ONLY valid JSON, no preamble:
{
  "score": <float 0-10>,
  "tag": "STRONG BUY" | "BUY" | "SKIP",
  "blurb": "<2-3 sentences plain English>",
  "bullets": [
    {"tone": "good" | "warn" | "bad", "text": "<plain English, max 30 words>"}
  ],
  "news_sentiments": ["positive" | "negative" | "neutral", ...]
}

For "news_sentiments": one entry per headline I show you, IN ORDER.
Classify each headline's IMPACT on the stock.

SCORING (different from Premium Hunter — context is "is this dislocation real?"):
- STRONG BUY (8+): clear catalyst for recovery, fundamentals intact, dislocation looks technical not fundamental
- BUY (6-7.9): mixed but more positive than negative
- SKIP (<6): structural problem, dislocation reflects real damage, recovery uncertain

GOOD blurb examples:
- CRM: "Biggest cloud software company for sales teams — 150,000 companies use it to manage customers. Now pushing AI agents (Agentforce) to compete with Microsoft."
- BIIB: "Drug company best known for MS treatments. Their Alzheimer's drug Leqembi is just starting to ramp up sales — could be a game-changer if adoption picks up."
- HCA: "Biggest hospital chain in the US — over 180 facilities. Earnings dropped because winter storms kept patients home and ACA insurance changes shifted their payer mix."

GOOD bullet examples:
- "Stock down 35% on AI fears — but the actual numbers show free cash up 30% and profit up 50%. Wall Street is overreacting."
- "Just bought Informatica for $8B — gives them more customer data to feed their AI agents."
- "Microsoft Copilot stealing some smaller customers — but Salesforce still has 150K+ enterprise locked-in."
- "Bought back $9.5B in shares last year — management putting money where mouth is."
"""


def _build_user_prompt(pick):
    pt = pick.get('put_trade') or {}
    sig = pick.get('signals') or {}
    
    news_titles = []
    for n in (pick.get('news_items') or [])[:4]:
        if isinstance(n, dict):
            t = n.get('title') or n.get('headline') or ''
        else:
            t = str(n)
        if t:
            news_titles.append(t)
    
    signals_fired = []
    if sig.get('below_sma50_fired'): signals_fired.append('Below SMA50 by 10%+')
    if sig.get('rsi_oversold_fired'): signals_fired.append(f'RSI hit {sig.get("rsi_min_14d", 0):.0f} (oversold)')
    if sig.get('lower_bb_fired'): signals_fired.append('Touched lower Bollinger Band')
    if sig.get('perf_1m_fired'): signals_fired.append(f'1mo perf {sig.get("perf_1m_pct", 0):.0f}%')
    if sig.get('near_52w_low_fired'): signals_fired.append('At/near 52w low')
    if sig.get('atl_5y_fired'): signals_fired.append('5y all-time low!')
    if sig.get('recovery_momentum'): signals_fired.append('RECOVERY: oversold recently, RSI now rising')
    
    return f"""Stock: {pick.get('ticker')} ({pick.get('company')})

Sector: {pick.get('sector')}
Market cap: ${(pick.get('market_cap') or 0)/1e9:.1f}B
Current price: ${pick.get('price', 0):.2f}
1y range: ${sig.get('low_1y', 0):.0f} - ${sig.get('high_1y', 0):.0f}
1y price action: {sig.get('pct_1y', 0):.0f}%

DISLOCATION SIGNALS FIRED (last 14 days):
{chr(10).join(f'  - {s}' for s in signals_fired) if signals_fired else '  (none)'}

% off 52w high: {sig.get('pct_off_high_52w', 0):.0f}%
% above 52w low: +{sig.get('pct_above_low_52w', 0):.0f}%
RSI now: {sig.get('rsi_today', 0):.0f}
1m performance: {sig.get('perf_1m_pct', 0):.0f}%

Fundamentals:
- EPS growth TTM: {(pick.get('eps_growth') or 0)*100:.0f}%
- P/E: {pick.get('pe', 'N/A')}
- Dividend yield: {pick.get('dividend_yield', 0):.1f}%

Recent news (classify each one's sentiment in your response):
{chr(10).join(f'  {i+1}. {t}' for i, t in enumerate(news_titles)) if news_titles else '  (none)'}

Now write the brief:
- "blurb": 2-3 sentences explaining what {pick.get('ticker')} actually does
- "bullets": 3-4 catalysts — WHY is it beaten down? What could turn it around?
- "news_sentiments": one tag per headline shown above, in order"""


def _fallback_result(pick):
    algo = pick.get('score', 0)
    return {
        'claude_score': algo,
        'claude_tag': 'STRONG BUY' if algo >= 8 else 'BUY' if algo >= 6 else 'SKIP',
        'claude_blurb': '',
        'claude_bullets': [('warn', 'Claude API unavailable - using algo score only')],
        'claude_news_sentiments': [],
    }


def _score_one(client, pick, retries=2):
    user_prompt = _build_user_prompt(pick)
    
    for attempt in range(retries + 1):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = resp.content[0].text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            
            return {
                'claude_score': float(data.get('score', pick.get('score', 0))),
                'claude_tag': data.get('tag', 'BUY'),
                'claude_blurb': data.get('blurb', '').strip(),
                'claude_bullets': [
                    (b.get('tone', 'warn'), b.get('text', ''))
                    for b in data.get('bullets', [])
                    if b.get('text')
                ][:4],
                'claude_news_sentiments': [
                    s for s in data.get('news_sentiments', [])
                    if s in ('positive', 'negative', 'neutral')
                ],
            }
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5 ** attempt)
                continue
            print(f"  x Claude API error for {pick.get('ticker')}: {e}",
                  file=sys.stderr, flush=True)
            return _fallback_result(pick)


def score_picks(picks):
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    
    if Anthropic is None:
        print("WARN: anthropic package not installed - skipping Claude", flush=True)
        for p in picks:
            p.update(_fallback_result(p))
        return picks
    
    if not api_key:
        print("WARN: ANTHROPIC_API_KEY not set - skipping Claude", flush=True)
        for p in picks:
            p.update(_fallback_result(p))
        return picks
    
    client = Anthropic(api_key=api_key)
    print(f"\nScoring {len(picks)} picks with Claude Opus 4.7 (dislocation mode)...", flush=True)
    
    for i, pick in enumerate(picks, 1):
        result = _score_one(client, pick)
        pick.update(result)
        print(f"  [{i}/{len(picks)}] {pick.get('ticker'):<6} "
              f"Claude: {result['claude_score']:.1f}  "
              f"Algo: {pick.get('score', 0):.1f}  "
              f"{result['claude_tag']}",
              flush=True)
    
    return picks
