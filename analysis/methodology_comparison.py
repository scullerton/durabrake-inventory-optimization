#!/usr/bin/env python3
"""
Methodology Comparison: Claude Analysis vs Financial Summary/Ops Action List
Reconciles findings and identifies gaps between approaches
"""

import pandas as pd
import numpy as np
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("="*90)
print("METHODOLOGY COMPARISON: CLAUDE ANALYSIS vs FINANCIAL SUMMARY")
print("="*90)

# Load both analyses
claude_analysis = pd.read_csv(os.path.join(base_dir, 'analysis/inventory_disposition_full.csv'))

# Load ops action list
ops_actions = pd.read_excel('/root/.claude/uploads/12fb829f-9032-5f16-b8a8-8523a2edc9dd/1c465f45-ops_action_list.xlsx',
                            sheet_name='Action List')

# Load financial summary scrap detail
fin_summary = pd.read_excel('/root/.claude/uploads/12fb829f-9032-5f16-b8a8-8523a2edc9dd/63385cc6-financial_summary.xlsx',
                           sheet_name='Scrap detail', skiprows=3)
fin_summary.columns = ['sku', 'dc', 'category', 'abc', '12mo_units', 'backlog', 'on_hand',
                       'unit_cost', 'cost_basis', 'write_down', 'recovery', 'op_mos', 'vendor', 'cost_source']
fin_scrap = fin_summary[(fin_summary['sku'] != 'TOTAL') & (fin_summary['sku'].notna())].copy()
for col in ['on_hand', 'unit_cost', 'cost_basis', 'write_down', 'recovery']:
    fin_scrap[col] = pd.to_numeric(fin_scrap[col], errors='coerce').fillna(0)

print("\n" + "-"*90)
print("KEY METHODOLOGY DIFFERENCES")
print("-"*90)

comparison = """
┌─────────────────────────────┬───────────────────────────────┬───────────────────────────────┐
│ Parameter                   │ Claude Analysis               │ Financial Summary / Ops       │
├─────────────────────────────┼───────────────────────────────┼───────────────────────────────┤
│ Cost of Capital             │ 30% annual                    │ 15% annual                    │
│ Lead Time (A-class)         │ 4 months (uniform)            │ 2.5 months                    │
│ Lead Time (BC-class)        │ 4 months (uniform)            │ 3.5 months                    │
│ Target Stock Model          │ Simple coverage (LT + safety) │ Newsvendor with critical ratio│
│ Safety Buffer               │ 2 months fixed                │ z(CR) × σ × √LT (dynamic)     │
│ Customer Tiering            │ Not used                      │ 1.5× multiplier for top-tier  │
│ ABC/XYZ Classification      │ Not used                      │ Used for lead time & priority │
│ Scrap Trigger               │ EVS < -0.30 or no demand      │ STRICT: 0 L12M sales + 0 backlog│
│ Analysis Level              │ SKU (network-wide)            │ SKU × DC (location-specific)  │
└─────────────────────────────┴───────────────────────────────┴───────────────────────────────┘
"""
print(comparison)

print("\n" + "-"*90)
print("SCRAP CANDIDATES COMPARISON")
print("-"*90)

# Claude liquidation candidates
claude_liquidate = claude_analysis[claude_analysis['action'] == 'LIQUIDATE'].copy()

# Financial summary scrap candidates (SKU level)
fin_scrap_skus = set(fin_scrap['sku'].dropna().unique())
claude_liquidate_skus = set(claude_liquidate['sku'].unique())

overlap = fin_scrap_skus & claude_liquidate_skus
only_fin = fin_scrap_skus - claude_liquidate_skus
only_claude = claude_liquidate_skus - fin_scrap_skus

print(f"""
Scrap/Liquidation Comparison:
┌────────────────────────────────┬──────────┬────────────────┐
│ Source                         │ SKUs     │ Value          │
├────────────────────────────────┼──────────┼────────────────┤
│ Financial Summary (strict)     │ {len(fin_scrap_skus):>6}   │ ${fin_scrap['cost_basis'].sum():>12,.0f} │
│ Claude Analysis (EVS-based)    │ {len(claude_liquidate_skus):>6}   │ ${claude_liquidate['on_hand_value'].sum():>12,.0f} │
├────────────────────────────────┼──────────┼────────────────┤
│ OVERLAP (both flagged)         │ {len(overlap):>6}   │ --             │
│ Only in Financial Summary      │ {len(only_fin):>6}   │ --             │
│ Only in Claude Analysis        │ {len(only_claude):>6}   │ --             │
└────────────────────────────────┴──────────┴────────────────┘
""")

print("\nSKUs in Financial Summary but NOT in Claude (likely due to DC-level aggregation):")
for sku in sorted(only_fin)[:15]:
    row = fin_scrap[fin_scrap['sku'] == sku].iloc[0]
    print(f"  {sku}: {row['on_hand']:.0f} units @ ${row['unit_cost']:.2f} at {row['dc']}")

print("\nSKUs in Claude Analysis but NOT in Financial Summary (likely due to stricter zero-sales trigger):")
for sku in sorted(only_claude)[:15]:
    row = claude_liquidate[claude_liquidate['sku'] == sku].iloc[0]
    print(f"  {sku}: {row['on_hand_qty']:.0f} units, L12M: {row['l12m_units']:.0f}, turns: {row['turns']:.2f}")

print("\n" + "-"*90)
print("OPS ACTION LIST DISTRIBUTION")
print("-"*90)

action_summary = ops_actions.groupby('Action').agg({
    'SKU': 'count',
    'On hand': 'sum',
    'Excess $': lambda x: x.sum(),
    'Scrap write-down $': lambda x: x.sum()
}).round(0)
action_summary.columns = ['Rows', 'On-Hand Units', 'Excess $', 'Scrap Write-Down $']

print("\nOps Actions by Priority:")
print(f"{'Action':<20} {'Rows':>6} {'Units':>10} {'Excess $':>14} {'Write-Down $':>14}")
print("-"*70)
for idx, row in action_summary.iterrows():
    print(f"{idx:<20} {int(row['Rows']):>6} {int(row['On-Hand Units']):>10,} ${int(row['Excess $']):>13,} ${int(row['Scrap Write-Down $']):>13,}")

print("\n" + "-"*90)
print("RECONCILIATION: IMPACT OF 15% vs 30% COST OF CAPITAL")
print("-"*90)

# Recalculate with 15% CoC
COC_15 = 0.15
COC_30 = 0.30
CARRY_COST = 0.75 * 12  # annual per unit

claude_analysis['evs_15pct'] = np.where(
    claude_analysis['on_hand_value'] > 0,
    (claude_analysis['gm_pct'] * claude_analysis['turns']) -
    ((claude_analysis['on_hand_qty'] * CARRY_COST) / claude_analysis['on_hand_value']) -
    COC_15,
    np.nan
)

# Count action changes
positive_evs_30 = (claude_analysis['evs'] > 0).sum()
positive_evs_15 = (claude_analysis['evs_15pct'] > 0).sum()

liquidate_at_30 = len(claude_analysis[claude_analysis['action'] == 'LIQUIDATE'])
liquidate_at_15 = len(claude_analysis[(claude_analysis['evs_15pct'] < -0.15) | (claude_analysis['l12m_units'] == 0)])

print(f"""
EVS Impact of Different Cost of Capital:
┌────────────────────────────────┬──────────┬──────────┐
│ Metric                         │ 30% CoC  │ 15% CoC  │
├────────────────────────────────┼──────────┼──────────┤
│ SKUs with positive EVS         │ {positive_evs_30:>6}   │ {positive_evs_15:>6}   │
│ SKUs with EVS > 10%            │ {(claude_analysis['evs'] > 0.10).sum():>6}   │ {(claude_analysis['evs_15pct'] > 0.10).sum():>6}   │
│ SKUs with EVS < -30%           │ {(claude_analysis['evs'] < -0.30).sum():>6}   │ {(claude_analysis['evs_15pct'] < -0.30).sum():>6}   │
└────────────────────────────────┴──────────┴──────────┘

With 15% CoC, {positive_evs_15 - positive_evs_30} more SKUs become EVS-positive.
""")

print("\n" + "-"*90)
print("RECOMMENDATIONS: ALIGNING THE ANALYSES")
print("-"*90)

print("""
1. ADOPT 15% COST OF CAPITAL
   - More consistent with industry norms for distributors
   - Aligns with financial summary methodology
   - Reduces false-positive liquidation recommendations

2. USE STRICTER SCRAP TRIGGER (Financial Summary Approach)
   - Zero L12M sales + Zero backlog + Write-down ≥ $500
   - More defensible for financial reporting
   - Currently: 26-30 SKUs totaling ~$109K (vs 87 SKUs at $119K)

3. ADOPT SKU×DC LEVEL ANALYSIS
   - Location-specific actions enable targeted disposition
   - Same SKU may be healthy at one DC, dead at another
   - Ops Action List has 303 rows vs 231 SKUs

4. INCORPORATE CUSTOMER TIERING
   - 1.5× multiplier for strategic customers (Oshkosh, Volvo, Cassens)
   - Raises service level for key accounts
   - Reduces excess flagging for strategic inventory

5. ADD ACTION PRIORITIZATION
   - backlog_alert → expedite → reorder_now → stop_reordering → liquidate → scrap → hold
   - More actionable than simple KEEP/REVIEW/LIQUIDATE

AGREED SCRAP LIST (30 SKUs, ~$98K write-down, ~$11K recovery):
""")

# Print agreed scrap candidates
print(f"\n{'SKU':<12} {'DC':<18} {'Units':>8} {'Write-Down':>12}")
print("-"*55)
for _, row in fin_scrap.head(30).iterrows():
    if pd.notna(row['sku']) and row['sku'] != 'TOTAL':
        print(f"{str(row['sku']):<12} {str(row['dc']):<18} {int(row['on_hand']):>8} ${row['write_down']:>11,.0f}")

# Save reconciliation
reconciliation_cols = ['sku', 'on_hand_qty', 'l12m_units', 'turns', 'evs', 'evs_15pct', 'action', 'on_hand_value']
claude_analysis[reconciliation_cols].to_csv(os.path.join(base_dir, 'analysis/evs_comparison.csv'), index=False)

print("\n" + "="*90)
print("EXECUTIVE SUMMARY")
print("="*90)

print(f"""
FINAL RECONCILED POSITION:

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ Metric                                  │ Financial Summary    │ Claude Analysis       │
├─────────────────────────────────────────┼──────────────────────┼───────────────────────┤
│ Total Inventory Asset (OH + OW)         │ $1,903,381           │ $914,821 (OH only)    │
│ Excess Inventory Flagged                │ $305,507             │ $280,822              │
│ Scrap Candidate Value                   │ $108,920             │ $118,661              │
│ Recommended Write-Down                  │ $98,028 (90%)        │ $106,795 (90%)        │
│ Expected Recovery                       │ $10,892 (10%)        │ $11,866 (10%)         │
│ Backlog Alert SKUs                      │ 9                    │ Not tracked           │
└─────────────────────────────────────────┴──────────────────────┴───────────────────────┘

RECOMMENDED ACTION:
• Use Financial Summary's strict scrap list (30 SKU×DC rows, $98K write-down)
• Adopt 15% CoC for ongoing EVS monitoring
• Implement Ops Action List prioritization for operational execution
• Conduct DC-level analysis for excess reduction beyond scrap

SAVED: analysis/evs_comparison.csv (EVS at both 15% and 30% CoC)
""")
