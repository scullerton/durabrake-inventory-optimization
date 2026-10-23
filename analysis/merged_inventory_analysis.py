#!/usr/bin/env python3
"""
DuraBrake Merged Inventory Optimization Analysis
Combines best practices from both methodologies:
- 15% Cost of Capital
- Newsvendor model with critical ratio
- ABC/XYZ classification with differentiated lead times
- Customer tiering for strategic accounts
- EVS-based disposition triggers
- DC-level analysis with relocation flagging
"""

import pandas as pd
import numpy as np
from datetime import datetime
from scipy import stats
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================================
# CONFIGURATION
# ============================================================================

COST_OF_CAPITAL = 0.15  # 15% annual (aligned with Financial Summary)
PHYSICAL_CARRY_PER_PART_MONTH = 0.75  # $0.75/part/month
SCRAP_RECOVERY_RATE = 0.10  # 10% salvage value

# Lead times by ABC class
LEAD_TIME_A = 2.5  # months
LEAD_TIME_BC = 3.5  # months

# Customer tiering
TOP_TIER_CUSTOMERS = ['Oshkosh Defense', 'Oshkosh', 'Volvo', 'Cassens Transport', 'Cassens',
                      'Volvo Group NA', 'Rush Enterprises']
TOP_TIER_MULTIPLIER = 1.5
TOP_TIER_CONCENTRATION_THRESHOLD = 0.30  # 30% of revenue from top-tier = strategic

# ABC/XYZ thresholds
ABC_A_REVENUE_CUTOFF = 0.80  # Top 80% of cumulative revenue
ABC_B_REVENUE_CUTOFF = 0.95  # Next 15%

# EVS thresholds for disposition
EVS_SCRAP_THRESHOLD = -0.25  # Below -25% EVS = scrap candidate
EVS_LIQUIDATE_THRESHOLD = -0.15  # -25% to -15% = liquidate consideration
EVS_REVIEW_THRESHOLD = 0.0  # -15% to 0% = review
MIN_SCRAP_WRITEDOWN = 500  # Minimum $ to flag for scrap

print("="*95)
print("DURABRAKE MERGED INVENTORY OPTIMIZATION ANALYSIS")
print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d')}")
print("="*95)

# ============================================================================
# LOAD DATA
# ============================================================================

inventory = pd.read_csv(os.path.join(base_dir, 'data/inventory.csv'))
backlog = pd.read_csv(os.path.join(base_dir, 'data/backlog.csv'))
velocity = pd.read_csv(os.path.join(base_dir, 'data/velocity.csv'))

velocity['month'] = pd.to_datetime(velocity['month'])
max_month = velocity['month'].max()

# Analysis periods
l3m_start = max_month - pd.DateOffset(months=2)
l12m_start = max_month - pd.DateOffset(months=11)

print(f"\nData: {len(inventory)} inventory rows, {len(velocity)} velocity records")
print(f"Analysis period: {l12m_start.strftime('%Y-%m')} to {max_month.strftime('%Y-%m')}")

# ============================================================================
# DC-LEVEL VELOCITY AGGREGATION
# ============================================================================

vel_l3m = velocity[velocity['month'] >= l3m_start]
vel_l12m = velocity[velocity['month'] >= l12m_start]

# Aggregate by SKU×DC for L3M
l3m_dc = vel_l3m.groupby(['sku', 'dc']).agg({
    'fulfilled_units': 'sum',
    'revenue': 'sum',
    'gp_dollars': 'sum',
    'customer': lambda x: list(x.unique())
}).reset_index()
l3m_dc.columns = ['sku', 'dc', 'l3m_units', 'l3m_revenue', 'l3m_gp', 'l3m_customers']

# Aggregate by SKU×DC for L12M
l12m_dc = vel_l12m.groupby(['sku', 'dc']).agg({
    'fulfilled_units': 'sum',
    'revenue': 'sum',
    'gp_dollars': 'sum',
    'customer': lambda x: list(x.unique())
}).reset_index()
l12m_dc.columns = ['sku', 'dc', 'l12m_units', 'l12m_revenue', 'l12m_gp', 'l12m_customers']

# Monthly demand stats for newsvendor (by SKU×DC)
monthly_demand = vel_l12m.groupby(['sku', 'dc', 'month'])['fulfilled_units'].sum().reset_index()
demand_stats = monthly_demand.groupby(['sku', 'dc']).agg({
    'fulfilled_units': ['mean', 'std', 'count']
}).reset_index()
demand_stats.columns = ['sku', 'dc', 'mean_monthly_demand', 'std_monthly_demand', 'months_with_sales']
demand_stats['std_monthly_demand'] = demand_stats['std_monthly_demand'].fillna(0)
demand_stats['cv'] = np.where(
    demand_stats['mean_monthly_demand'] > 0,
    demand_stats['std_monthly_demand'] / demand_stats['mean_monthly_demand'],
    0
)

# Network-level aggregation (for relocation logic)
l12m_network = vel_l12m.groupby('sku').agg({
    'fulfilled_units': 'sum',
    'revenue': 'sum',
    'gp_dollars': 'sum'
}).reset_index()
l12m_network.columns = ['sku', 'network_l12m_units', 'network_l12m_revenue', 'network_l12m_gp']

# ============================================================================
# CUSTOMER TIERING
# ============================================================================

# Identify top-tier customer concentration by SKU
def check_top_tier(customers_list):
    """Check if any top-tier customer in list"""
    if not isinstance(customers_list, list):
        return False
    for cust in customers_list:
        for top in TOP_TIER_CUSTOMERS:
            if top.lower() in str(cust).lower():
                return True
    return False

# Calculate top-tier revenue share by SKU
top_tier_rev = vel_l12m.copy()
top_tier_rev['is_top_tier'] = top_tier_rev['customer'].apply(
    lambda x: any(t.lower() in str(x).lower() for t in TOP_TIER_CUSTOMERS)
)
top_tier_share = top_tier_rev.groupby('sku').apply(
    lambda x: x[x['is_top_tier']]['revenue'].sum() / x['revenue'].sum() if x['revenue'].sum() > 0 else 0
).reset_index()
top_tier_share.columns = ['sku', 'top_tier_share']

# ============================================================================
# ABC CLASSIFICATION (by revenue)
# ============================================================================

sku_revenue = l12m_network.sort_values('network_l12m_revenue', ascending=False).copy()
sku_revenue['cum_revenue'] = sku_revenue['network_l12m_revenue'].cumsum()
total_revenue = sku_revenue['network_l12m_revenue'].sum()
sku_revenue['cum_pct'] = sku_revenue['cum_revenue'] / total_revenue

def assign_abc(cum_pct):
    if cum_pct <= ABC_A_REVENUE_CUTOFF:
        return 'A'
    elif cum_pct <= ABC_B_REVENUE_CUTOFF:
        return 'B'
    else:
        return 'C'

sku_revenue['abc_class'] = sku_revenue['cum_pct'].apply(assign_abc)
abc_lookup = sku_revenue[['sku', 'abc_class']].copy()

# ============================================================================
# MERGE ALL DATA AT SKU×DC LEVEL
# ============================================================================

# Start with inventory (already at SKU×DC level)
analysis = inventory.copy()
analysis = analysis.rename(columns={'dc': 'dc_raw'})

# Standardize DC names
dc_mapping = {
    'Sacramento, CA': 'Sacramento, CA',
    'Edison, NJ': 'Edison, NJ',
    'Tacoma, WA': 'Tacoma, WA',
    'Vancouver, BC': 'Vancouver, BC',
    'Container (Canada)': 'Container (Canada)',
    'Container (US)': 'Container (US)',
    'Houston, TX': 'Houston, TX'
}
analysis['dc'] = analysis['dc_raw'].map(lambda x: dc_mapping.get(x, x))

# Merge velocity data
analysis = analysis.merge(l3m_dc, on=['sku', 'dc'], how='left')
analysis = analysis.merge(l12m_dc, on=['sku', 'dc'], how='left')
analysis = analysis.merge(demand_stats, on=['sku', 'dc'], how='left')
analysis = analysis.merge(l12m_network, on='sku', how='left')
analysis = analysis.merge(abc_lookup, on='sku', how='left')
analysis = analysis.merge(top_tier_share, on='sku', how='left')

# Merge backlog
backlog_agg = backlog.groupby(['sku', 'dc']).agg({
    'committed_units': 'sum',
    'days_until_due': 'min'
}).reset_index()
backlog_agg.columns = ['sku', 'dc', 'backlog_units', 'most_urgent_days']
analysis = analysis.merge(backlog_agg, on=['sku', 'dc'], how='left')

# Fill NaN
fill_cols = ['l3m_units', 'l3m_revenue', 'l3m_gp', 'l12m_units', 'l12m_revenue', 'l12m_gp',
             'mean_monthly_demand', 'std_monthly_demand', 'months_with_sales', 'cv',
             'network_l12m_units', 'network_l12m_revenue', 'network_l12m_gp',
             'backlog_units', 'top_tier_share']
for col in fill_cols:
    if col in analysis.columns:
        analysis[col] = analysis[col].fillna(0)

analysis['most_urgent_days'] = analysis['most_urgent_days'].fillna(999)
analysis['abc_class'] = analysis['abc_class'].fillna('C')

# ============================================================================
# NEWSVENDOR TARGET STOCK CALCULATION
# ============================================================================

# Lead time by ABC class
analysis['lead_time_mo'] = np.where(analysis['abc_class'] == 'A', LEAD_TIME_A, LEAD_TIME_BC)

# Unit GP and cost
analysis['unit_gp'] = np.where(
    analysis['l12m_units'] > 0,
    analysis['l12m_gp'] / analysis['l12m_units'],
    analysis['unit_cost_landed'] * 0.40  # Assume 40% margin if no sales
)
analysis['gm_pct'] = np.where(
    analysis['l12m_revenue'] > 0,
    analysis['l12m_gp'] / analysis['l12m_revenue'],
    0.40
)

# Is this SKU strategic (top-tier customer concentrated)?
analysis['is_strategic'] = (analysis['top_tier_share'] >= TOP_TIER_CONCENTRATION_THRESHOLD)

# Underage cost (Cu) = unit GP × multiplier
analysis['cu'] = analysis['unit_gp'] * np.where(analysis['is_strategic'], TOP_TIER_MULTIPLIER, 1.0)

# Overage cost (Co) = unit cost × CoC × lead time / 12
analysis['co'] = analysis['unit_cost_landed'] * COST_OF_CAPITAL * analysis['lead_time_mo'] / 12

# Critical ratio
analysis['critical_ratio'] = analysis['cu'] / (analysis['cu'] + analysis['co'])
analysis['critical_ratio'] = analysis['critical_ratio'].clip(0.5, 0.999)

# Service level (z-score)
analysis['z_score'] = analysis['critical_ratio'].apply(lambda cr: stats.norm.ppf(cr))

# Target stock = LT demand + safety stock
analysis['lt_demand'] = analysis['mean_monthly_demand'] * analysis['lead_time_mo']
analysis['safety_stock'] = analysis['z_score'] * analysis['std_monthly_demand'] * np.sqrt(analysis['lead_time_mo'])
analysis['safety_stock'] = analysis['safety_stock'].fillna(0).clip(lower=0)

# Target on-hand = max(LT demand, backlog within LT) + safety stock
analysis['target_stock'] = np.maximum(analysis['lt_demand'], analysis['backlog_units']) + analysis['safety_stock']

# Available stock = on-hand - committed backlog
analysis['available_stock'] = (analysis['on_hand_qty'] - analysis['backlog_units']).clip(lower=0)

# Excess units
analysis['excess_qty'] = (analysis['available_stock'] - analysis['target_stock']).clip(lower=0)

# ============================================================================
# EVS CALCULATION (15% CoC)
# ============================================================================

analysis['on_hand_value'] = analysis['on_hand_qty'] * analysis['unit_cost_landed']
analysis['excess_value'] = analysis['excess_qty'] * analysis['unit_cost_landed']

# Annual COGS at this DC
analysis['l12m_cogs'] = analysis['l12m_units'] * analysis['unit_cost_landed']

# Turns = COGS / On-hand value
analysis['turns'] = np.where(
    analysis['on_hand_value'] > 0,
    analysis['l12m_cogs'] / analysis['on_hand_value'],
    0
)

# Annual carrying cost
analysis['annual_carry_cost'] = analysis['on_hand_qty'] * PHYSICAL_CARRY_PER_PART_MONTH * 12

# EVS = GM% × Turns - (Carry / Inv) - CoC
analysis['evs'] = np.where(
    analysis['on_hand_value'] > 0,
    (analysis['gm_pct'] * analysis['turns']) -
    (analysis['annual_carry_cost'] / analysis['on_hand_value']) -
    COST_OF_CAPITAL,
    np.nan
)

# ============================================================================
# TREND ANALYSIS
# ============================================================================

analysis['l3m_monthly_rate'] = analysis['l3m_units'] / 3
analysis['l12m_monthly_rate'] = analysis['l12m_units'] / 12

def calculate_trend(row):
    l12m = row['l12m_monthly_rate']
    l3m = row['l3m_monthly_rate']

    if l12m == 0 and l3m == 0:
        return 'NO_SALES'
    if row['months_with_sales'] <= 3 and l3m > 0:
        return 'NEW'
    if l12m == 0:
        return 'NEW'

    ratio = l3m / l12m if l12m > 0 else 0
    if ratio >= 1.25:
        return 'ACCELERATING'
    elif ratio <= 0.75:
        return 'DECELERATING'
    return 'STABLE'

analysis['trend'] = analysis.apply(calculate_trend, axis=1)

# ============================================================================
# DISPOSITION CLASSIFICATION WITH RELOCATION LOGIC
# ============================================================================

def classify_disposition(row):
    """
    Classify inventory disposition with relocation consideration:
    - SCRAP: Dead everywhere (EVS << 0, no network sales, no backlog)
    - RELOCATE: Dead at this DC but healthy network-wide
    - LIQUIDATE: Very slow, consider markdown
    - STOP_REORDER: Don't replenish, let run out
    - REVIEW: Borderline, needs investigation
    - HOLD: Maintain current levels
    - EXPEDITE: Understocked, needs replenishment
    - BACKLOG_ALERT: Can't fill committed orders
    """
    evs = row['evs'] if pd.notna(row['evs']) else -999
    has_backlog = row['backlog_units'] > 0
    has_dc_sales = row['l12m_units'] > 0
    has_network_sales = row['network_l12m_units'] > 0
    on_hand = row['on_hand_qty']
    write_down = row['on_hand_value'] * 0.90  # 90% write-down

    if on_hand == 0:
        return 'NO_STOCK'

    # Backlog alert - can't fill orders
    if has_backlog and row['available_stock'] < 0:
        return 'BACKLOG_ALERT'

    # Check for relocation opportunity: dead at DC but alive network-wide
    if not has_dc_sales and has_network_sales and not has_backlog:
        if evs < EVS_REVIEW_THRESHOLD:
            return 'RELOCATE'

    # Scrap: deeply negative EVS, no sales anywhere, no backlog, material value
    if evs < EVS_SCRAP_THRESHOLD and not has_network_sales and not has_backlog:
        if write_down >= MIN_SCRAP_WRITEDOWN:
            return 'SCRAP'
        return 'LIQUIDATE'  # Too small to scrap formally

    # Liquidate: negative EVS, minimal demand
    if evs < EVS_LIQUIDATE_THRESHOLD and not has_backlog:
        if row['turns'] < 0.5:
            return 'LIQUIDATE'
        return 'STOP_REORDER'

    # Review: borderline EVS or decelerating
    if evs < EVS_REVIEW_THRESHOLD:
        if row['trend'] == 'DECELERATING':
            return 'STOP_REORDER'
        return 'REVIEW'

    # Understocked - need to expedite
    if row['on_hand_qty'] < row['target_stock'] * 0.5 and has_dc_sales:
        return 'EXPEDITE'

    # Healthy
    return 'HOLD'

analysis['disposition'] = analysis.apply(classify_disposition, axis=1)

# Scrap financials
analysis['write_down'] = np.where(
    analysis['disposition'] == 'SCRAP',
    analysis['on_hand_value'] * (1 - SCRAP_RECOVERY_RATE),
    0
)
analysis['recovery'] = np.where(
    analysis['disposition'] == 'SCRAP',
    analysis['on_hand_value'] * SCRAP_RECOVERY_RATE,
    0
)

# ============================================================================
# REPORTS
# ============================================================================

print("\n" + "="*95)
print("DISPOSITION SUMMARY BY ACTION")
print("="*95)

summary = analysis[analysis['on_hand_qty'] > 0].groupby('disposition').agg({
    'sku': 'count',
    'on_hand_qty': 'sum',
    'on_hand_value': 'sum',
    'excess_value': 'sum',
    'write_down': 'sum',
    'recovery': 'sum'
}).round(0)
summary.columns = ['Rows', 'Units', 'Inv_Value', 'Excess_Value', 'Write_Down', 'Recovery']
summary = summary.sort_values('Inv_Value', ascending=False)

print(f"\n{'Disposition':<15} {'Rows':>6} {'Units':>10} {'Inv Value':>14} {'Excess':>12} {'Write-Down':>12}")
print("-"*75)
for idx, row in summary.iterrows():
    print(f"{idx:<15} {int(row['Rows']):>6} {int(row['Units']):>10,} ${int(row['Inv_Value']):>13,} ${int(row['Excess_Value']):>11,} ${int(row['Write_Down']):>11,}")
print("-"*75)
total = analysis[analysis['on_hand_qty'] > 0]
print(f"{'TOTAL':<15} {len(total):>6} {int(total['on_hand_qty'].sum()):>10,} ${int(total['on_hand_value'].sum()):>13,} ${int(total['excess_value'].sum()):>11,} ${int(total['write_down'].sum()):>11,}")

# ============================================================================
# SCRAP CANDIDATES
# ============================================================================

print("\n" + "="*95)
print("SCRAP CANDIDATES (EVS < -25%, no network sales, no backlog, write-down ≥ $500)")
print("="*95)

scrap = analysis[analysis['disposition'] == 'SCRAP'].copy()
scrap = scrap.sort_values('write_down', ascending=False)

print(f"\nTotal: {len(scrap)} SKU×DC rows, ${scrap['write_down'].sum():,.0f} write-down, ${scrap['recovery'].sum():,.0f} recovery")
print(f"\n{'SKU':<12} {'DC':<20} {'Units':>6} {'EVS':>8} {'Turns':>6} {'Value':>10} {'Write-Down':>12}")
print("-"*85)
for _, row in scrap.head(25).iterrows():
    evs_str = f"{row['evs']*100:.0f}%" if pd.notna(row['evs']) else "N/A"
    print(f"{str(row['sku']):<12} {str(row['dc']):<20} {int(row['on_hand_qty']):>6} {evs_str:>8} {row['turns']:>6.2f} ${row['on_hand_value']:>9,.0f} ${row['write_down']:>11,.0f}")

# ============================================================================
# RELOCATION CANDIDATES
# ============================================================================

print("\n" + "="*95)
print("RELOCATION CANDIDATES (Dead at DC but healthy network-wide)")
print("="*95)

relocate = analysis[analysis['disposition'] == 'RELOCATE'].copy()
relocate = relocate.sort_values('on_hand_value', ascending=False)

print(f"\nTotal: {len(relocate)} SKU×DC rows, ${relocate['on_hand_value'].sum():,.0f} stranded inventory")
print(f"\n{'SKU':<12} {'From DC':<18} {'Units':>6} {'DC L12M':>8} {'Network L12M':>12} {'Value':>10}")
print("-"*75)
for _, row in relocate.head(20).iterrows():
    print(f"{str(row['sku']):<12} {str(row['dc']):<18} {int(row['on_hand_qty']):>6} {int(row['l12m_units']):>8} {int(row['network_l12m_units']):>12} ${row['on_hand_value']:>9,.0f}")

# ============================================================================
# LIQUIDATE / STOP REORDER
# ============================================================================

print("\n" + "="*95)
print("LIQUIDATE / STOP REORDER (EVS -25% to -15%, slow movers)")
print("="*95)

liquidate = analysis[analysis['disposition'].isin(['LIQUIDATE', 'STOP_REORDER'])].copy()
liquidate = liquidate.sort_values('on_hand_value', ascending=False)

print(f"\nTotal: {len(liquidate)} SKU×DC rows, ${liquidate['on_hand_value'].sum():,.0f} value, ${liquidate['excess_value'].sum():,.0f} excess")
print(f"\n{'SKU':<12} {'DC':<18} {'Action':<14} {'Units':>6} {'EVS':>8} {'Turns':>6} {'Value':>10}")
print("-"*85)
for _, row in liquidate.head(20).iterrows():
    evs_str = f"{row['evs']*100:.0f}%" if pd.notna(row['evs']) else "N/A"
    print(f"{str(row['sku']):<12} {str(row['dc']):<18} {row['disposition']:<14} {int(row['on_hand_qty']):>6} {evs_str:>8} {row['turns']:>6.2f} ${row['on_hand_value']:>9,.0f}")

# ============================================================================
# ABC DISTRIBUTION
# ============================================================================

print("\n" + "="*95)
print("ABC CLASSIFICATION SUMMARY")
print("="*95)

abc_summary = analysis[analysis['on_hand_qty'] > 0].groupby('abc_class').agg({
    'sku': 'nunique',
    'on_hand_value': 'sum',
    'l12m_revenue': 'sum',
    'excess_value': 'sum'
}).round(0)

print(f"\n{'Class':<8} {'SKUs':>8} {'Inv Value':>14} {'L12M Revenue':>14} {'Excess':>12} {'Lead Time':>10}")
print("-"*70)
for cls in ['A', 'B', 'C']:
    if cls in abc_summary.index:
        row = abc_summary.loc[cls]
        lt = LEAD_TIME_A if cls == 'A' else LEAD_TIME_BC
        print(f"{cls:<8} {int(row['sku']):>8} ${int(row['on_hand_value']):>13,} ${int(row['l12m_revenue']):>13,} ${int(row['excess_value']):>11,} {lt:>9.1f} mo")

# ============================================================================
# STRATEGIC CUSTOMER IMPACT
# ============================================================================

print("\n" + "="*95)
print("STRATEGIC CUSTOMER INVENTORY (Top-tier: Oshkosh, Volvo, Cassens)")
print("="*95)

strategic = analysis[(analysis['is_strategic']) & (analysis['on_hand_qty'] > 0)]
print(f"\nStrategic SKUs (≥30% top-tier revenue): {strategic['sku'].nunique()} unique SKUs")
print(f"Inventory Value: ${strategic['on_hand_value'].sum():,.0f}")
print(f"These receive 1.5× service level multiplier in newsvendor calculation")

# ============================================================================
# SAVE OUTPUT
# ============================================================================

output_cols = [
    'sku', 'dc', 'abc_class', 'item_class', 'vendor',
    'disposition', 'trend', 'is_strategic',
    'on_hand_qty', 'on_water_qty', 'on_order_qty', 'backlog_units',
    'l3m_units', 'l12m_units', 'network_l12m_units',
    'mean_monthly_demand', 'std_monthly_demand', 'cv',
    'turns', 'gm_pct', 'evs',
    'lead_time_mo', 'critical_ratio', 'target_stock',
    'available_stock', 'excess_qty',
    'unit_cost_landed', 'on_hand_value', 'excess_value',
    'write_down', 'recovery'
]

analysis[output_cols].to_csv(os.path.join(base_dir, 'analysis/merged_disposition_full.csv'), index=False)

# Action-specific exports
scrap.to_csv(os.path.join(base_dir, 'analysis/action_scrap.csv'), index=False)
relocate.to_csv(os.path.join(base_dir, 'analysis/action_relocate.csv'), index=False)
liquidate.to_csv(os.path.join(base_dir, 'analysis/action_liquidate_stop.csv'), index=False)

# ============================================================================
# EXECUTIVE SUMMARY
# ============================================================================

print("\n" + "="*95)
print("EXECUTIVE SUMMARY")
print("="*95)

scrap_value = scrap['on_hand_value'].sum()
scrap_writedown = scrap['write_down'].sum()
scrap_recovery = scrap['recovery'].sum()
relocate_value = relocate['on_hand_value'].sum()
liquidate_value = liquidate['on_hand_value'].sum()
total_excess = analysis['excess_value'].sum()

print(f"""
MERGED ANALYSIS PARAMETERS:
  • Cost of Capital: {COST_OF_CAPITAL*100:.0f}% annual
  • Lead Time: {LEAD_TIME_A} mo (A-class) / {LEAD_TIME_BC} mo (BC-class)
  • Model: Newsvendor with critical ratio
  • Customer Tiering: {TOP_TIER_MULTIPLIER}× multiplier for strategic accounts
  • Scrap Trigger: EVS < {EVS_SCRAP_THRESHOLD*100:.0f}% AND no network sales AND no backlog

DISPOSITION ACTIONS:
┌───────────────────┬────────┬─────────────────┬─────────────────────────────────────────────┐
│ Action            │ Rows   │ Inventory Value │ Recommendation                              │
├───────────────────┼────────┼─────────────────┼─────────────────────────────────────────────┤
│ SCRAP             │ {len(scrap):>6} │ ${scrap_value:>14,.0f} │ Write off ({SCRAP_RECOVERY_RATE*100:.0f}% recovery = ${scrap_recovery:,.0f})          │
│ RELOCATE          │ {len(relocate):>6} │ ${relocate_value:>14,.0f} │ Transfer to higher-velocity DC              │
│ LIQUIDATE/STOP    │ {len(liquidate):>6} │ ${liquidate_value:>14,.0f} │ Markdown or let run out                     │
│ Total Excess      │     -- │ ${total_excess:>14,.0f} │ Working capital opportunity                 │
└───────────────────┴────────┴─────────────────┴─────────────────────────────────────────────┘

FINANCIAL IMPACT:
  • Scrap Write-Down: ${scrap_writedown:>12,.0f}
  • Expected Recovery: ${scrap_recovery:>12,.0f}
  • Relocation Value: ${relocate_value:>12,.0f} (avoid scrap via transfer)
  • Total W/C Opportunity: ${total_excess:>12,.0f}

FILES GENERATED:
  • analysis/merged_disposition_full.csv (complete DC-level analysis)
  • analysis/action_scrap.csv (scrap candidates)
  • analysis/action_relocate.csv (relocation opportunities)
  • analysis/action_liquidate_stop.csv (liquidation/stop-reorder)
""")

print("="*95)
