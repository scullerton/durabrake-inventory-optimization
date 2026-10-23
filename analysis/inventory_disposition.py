#!/usr/bin/env python3
"""
DuraBrake Slow Moving Inventory Disposition Analysis
Recreates the Excel workbook methodology with EVS, trend analysis, and action classifications
"""

import pandas as pd
import numpy as np
from datetime import datetime

# Configuration - matches Excel assumptions
COST_OF_CAPITAL = 0.30  # 30% annual
PHYSICAL_CARRY_PER_PART_MONTH = 0.75  # $0.75/part/month
SCRAP_RECOVERY_RATE = 0.10  # 10% of cost recovered on liquidation
REORDER_LEAD_TIME_MONTHS = 4
SAFETY_BUFFER_MONTHS = 2
TARGET_COVERAGE_MONTHS = REORDER_LEAD_TIME_MONTHS + SAFETY_BUFFER_MONTHS  # 6 months

print("="*90)
print("DURABRAKE SLOW MOVING INVENTORY DISPOSITION ANALYSIS")
print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d')}")
print("="*90)

# --- Load Data ---
import os
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
inventory = pd.read_csv(os.path.join(base_dir, 'data/inventory.csv'))
backlog = pd.read_csv(os.path.join(base_dir, 'data/backlog.csv'))
velocity = pd.read_csv(os.path.join(base_dir, 'data/velocity.csv'))

# Parse month column
velocity['month'] = pd.to_datetime(velocity['month'])

# --- Determine Analysis Period ---
max_month = velocity['month'].max()
min_month = velocity['month'].min()
print(f"\nVelocity data range: {min_month.strftime('%Y-%m')} to {max_month.strftime('%Y-%m')}")

# L3M = last 3 complete months, L12M = last 12 months
l3m_start = max_month - pd.DateOffset(months=2)  # Current month + 2 prior
l12m_start = max_month - pd.DateOffset(months=11)  # Current month + 11 prior

print(f"L3M period: {l3m_start.strftime('%Y-%m')} to {max_month.strftime('%Y-%m')}")
print(f"L12M period: {l12m_start.strftime('%Y-%m')} to {max_month.strftime('%Y-%m')}")

# --- Calculate SKU-Level Velocity Metrics ---

# Filter for L3M and L12M periods
vel_l3m = velocity[velocity['month'] >= l3m_start]
vel_l12m = velocity[velocity['month'] >= l12m_start]

# Aggregate by SKU for L3M
l3m_agg = vel_l3m.groupby('sku').agg({
    'fulfilled_units': 'sum',
    'revenue': 'sum',
    'gp_dollars': 'sum'
}).reset_index()
l3m_agg.columns = ['sku', 'l3m_units', 'l3m_revenue', 'l3m_gp']

# Aggregate by SKU for L12M (TTM)
l12m_agg = vel_l12m.groupby('sku').agg({
    'fulfilled_units': 'sum',
    'revenue': 'sum',
    'gp_dollars': 'sum'
}).reset_index()
l12m_agg.columns = ['sku', 'l12m_units', 'l12m_revenue', 'l12m_gp']

# Count active months for each SKU in L12M
months_active = vel_l12m.groupby('sku')['month'].nunique().reset_index()
months_active.columns = ['sku', 'months_with_sales']

# --- Aggregate Inventory Network-Wide ---
inv_agg = inventory.groupby('sku').agg({
    'on_hand_qty': 'sum',
    'on_water_qty': 'sum',
    'on_order_qty': 'sum',
    'in_transit_qty': 'sum',
    'velocity_3mo_units': 'sum',
    'velocity_12mo_units': 'sum',
    'unit_cost_landed': 'first',
    'item_class': 'first',
    'vendor': 'first'
}).reset_index()

# --- Aggregate Backlog ---
backlog_agg = backlog.groupby('sku').agg({
    'committed_units': 'sum',
    'days_until_due': 'min'
}).reset_index()
backlog_agg.columns = ['sku', 'backlog_units', 'most_urgent_days']

# --- Merge All Data ---
analysis = inv_agg.merge(l3m_agg, on='sku', how='left')
analysis = analysis.merge(l12m_agg, on='sku', how='left')
analysis = analysis.merge(months_active, on='sku', how='left')
analysis = analysis.merge(backlog_agg, on='sku', how='left')

# Fill NaN values
for col in ['l3m_units', 'l3m_revenue', 'l3m_gp', 'l12m_units', 'l12m_revenue', 'l12m_gp']:
    analysis[col] = analysis[col].fillna(0)
analysis['months_with_sales'] = analysis['months_with_sales'].fillna(0)
analysis['backlog_units'] = analysis['backlog_units'].fillna(0)
analysis['most_urgent_days'] = analysis['most_urgent_days'].fillna(999)

# --- Calculate Key Metrics ---

# Inventory value
analysis['on_hand_value'] = analysis['on_hand_qty'] * analysis['unit_cost_landed']
analysis['total_position'] = analysis['on_hand_qty'] + analysis['on_water_qty'] + analysis['on_order_qty']
analysis['total_position_value'] = analysis['total_position'] * analysis['unit_cost_landed']

# COGS (use cost for units sold)
analysis['l12m_cogs'] = analysis['l12m_units'] * analysis['unit_cost_landed']
analysis['l3m_cogs'] = analysis['l3m_units'] * analysis['unit_cost_landed']

# Inventory turns = TTM COGS / Average Inventory
# Without historical snapshots, use current on-hand as proxy
analysis['turns'] = np.where(
    analysis['on_hand_value'] > 0,
    analysis['l12m_cogs'] / analysis['on_hand_value'],
    0
)

# Gross margin %
analysis['gm_pct'] = np.where(
    analysis['l12m_revenue'] > 0,
    analysis['l12m_gp'] / analysis['l12m_revenue'],
    0
)

# Physical carrying cost (annual) = $0.75 * 12 * avg units
analysis['annual_carry_cost'] = analysis['on_hand_qty'] * PHYSICAL_CARRY_PER_PART_MONTH * 12

# EVS = GM% × Turns − (Physical Carry / Avg Inv) − Cost of Capital
analysis['evs'] = np.where(
    analysis['on_hand_value'] > 0,
    (analysis['gm_pct'] * analysis['turns']) -
    (analysis['annual_carry_cost'] / analysis['on_hand_value']) -
    COST_OF_CAPITAL,
    np.nan
)

# --- Trend Analysis ---
# L3M annualized vs L12M
analysis['l3m_annualized_units'] = analysis['l3m_units'] * 4
analysis['l12m_monthly_rate'] = analysis['l12m_units'] / 12
analysis['l3m_monthly_rate'] = analysis['l3m_units'] / 3

# Trend: Compare L3M run rate to L12M run rate
def calculate_trend(row):
    l12m_rate = row['l12m_monthly_rate']
    l3m_rate = row['l3m_monthly_rate']

    # No history = NEW item
    if l12m_rate == 0 and l3m_rate == 0:
        return 'NO_SALES'
    if row['months_with_sales'] <= 3 and l3m_rate > 0:
        return 'NEW'
    if l12m_rate == 0:
        return 'NEW'

    ratio = l3m_rate / l12m_rate

    if ratio >= 1.25:
        return 'ACCELERATING'
    elif ratio <= 0.75:
        return 'DECELERATING'
    else:
        return 'STABLE'

analysis['trend'] = analysis.apply(calculate_trend, axis=1)

# Weeks of supply
analysis['weekly_demand'] = analysis['l12m_units'] / 52
analysis['weeks_of_supply'] = np.where(
    analysis['weekly_demand'] > 0,
    analysis['on_hand_qty'] / analysis['weekly_demand'],
    np.inf
)

# Months of supply (using L3M run rate for forward-looking)
analysis['months_of_supply_l3m'] = np.where(
    analysis['l3m_monthly_rate'] > 0,
    analysis['on_hand_qty'] / analysis['l3m_monthly_rate'],
    np.inf
)

# --- Action Classification ---
def classify_action(row):
    """
    Classify inventory action based on EVS and trend
    KEEP: EVS > 0 or healthy demand trend
    MARGINAL: EVS slightly negative, some demand
    REVIEW: Declining but potentially recovering
    LIQUIDATE: EVS deeply negative, no/declining demand
    """
    evs = row['evs'] if pd.notna(row['evs']) else -999
    trend = row['trend']
    turns = row['turns']
    has_backlog = row['backlog_units'] > 0
    has_demand = row['l12m_units'] > 0

    # No inventory
    if row['on_hand_qty'] == 0:
        return 'NO_STOCK'

    # Strong performers
    if evs > 0.10:
        return 'KEEP'

    # Has backlog - don't liquidate
    if has_backlog and row['most_urgent_days'] < 60:
        return 'KEEP'

    # Accelerating trend - give benefit of doubt
    if trend == 'ACCELERATING' and has_demand:
        return 'KEEP' if evs > -0.10 else 'REVIEW'

    # New items - review
    if trend == 'NEW':
        return 'REVIEW'

    # EVS break-even to slightly negative
    if -0.10 <= evs <= 0.10:
        if trend == 'STABLE':
            return 'MARGINAL'
        elif trend == 'DECELERATING':
            return 'REVIEW'
        else:
            return 'MARGINAL'

    # EVS moderately negative
    if -0.30 <= evs < -0.10:
        if has_demand and trend != 'NO_SALES':
            return 'REVIEW'
        else:
            return 'LIQUIDATE'

    # EVS deeply negative or no sales
    if evs < -0.30 or trend == 'NO_SALES':
        if has_backlog:
            return 'REVIEW'
        return 'LIQUIDATE'

    return 'REVIEW'

analysis['action'] = analysis.apply(classify_action, axis=1)

# --- Stocking Optimization (Target Inventory) ---
# Target = Lead time demand + Safety buffer
analysis['monthly_demand'] = analysis['l12m_units'] / 12
analysis['target_stock'] = analysis['monthly_demand'] * TARGET_COVERAGE_MONTHS
analysis['excess_qty'] = (analysis['on_hand_qty'] - analysis['target_stock']).clip(lower=0)
analysis['excess_value'] = analysis['excess_qty'] * analysis['unit_cost_landed']

# Liquidation proceeds estimate (10% recovery)
analysis['floor_proceeds'] = np.where(
    analysis['action'] == 'LIQUIDATE',
    analysis['on_hand_value'] * SCRAP_RECOVERY_RATE,
    0
)

# --- Generate Reports ---

print("\n" + "="*90)
print("INVENTORY HEALTH SUMMARY BY ACTION")
print("="*90)

summary = analysis.groupby('action').agg({
    'sku': 'count',
    'on_hand_qty': 'sum',
    'on_hand_value': 'sum',
    'l12m_revenue': 'sum',
    'l12m_gp': 'sum',
    'excess_value': 'sum',
    'floor_proceeds': 'sum'
}).round(0)
summary.columns = ['SKUs', 'Units', 'Inv_Value', 'L12M_Rev', 'L12M_GP', 'Excess_Value', 'Floor_Proceeds']
summary = summary.sort_values('Inv_Value', ascending=False)

print(f"\n{'Action':<12} {'SKUs':>6} {'Units':>10} {'Inv Value':>14} {'L12M Revenue':>14} {'L12M GP':>12} {'Excess Val':>12}")
print("-"*90)
for idx, row in summary.iterrows():
    print(f"{idx:<12} {int(row['SKUs']):>6} {int(row['Units']):>10,} ${int(row['Inv_Value']):>13,} ${int(row['L12M_Rev']):>13,} ${int(row['L12M_GP']):>11,} ${int(row['Excess_Value']):>11,}")

print("-"*90)
total_inv = analysis['on_hand_value'].sum()
total_excess = analysis['excess_value'].sum()
print(f"{'TOTAL':<12} {len(analysis):>6} {int(analysis['on_hand_qty'].sum()):>10,} ${int(total_inv):>13,} ${int(analysis['l12m_revenue'].sum()):>13,} ${int(analysis['l12m_gp'].sum()):>11,} ${int(total_excess):>11,}")

# --- EVS Distribution ---
print("\n" + "="*90)
print("EVS DISTRIBUTION (Economic Value per Stocked Dollar)")
print("="*90)

evs_bins = [(-np.inf, -0.50), (-0.50, -0.30), (-0.30, -0.10), (-0.10, 0), (0, 0.10), (0.10, 0.30), (0.30, np.inf)]
evs_labels = ['<-50%', '-50% to -30%', '-30% to -10%', '-10% to 0%', '0% to 10%', '10% to 30%', '>30%']

print(f"\n{'EVS Range':<15} {'SKUs':>6} {'Inv Value':>14} {'% of Total':>10}")
print("-"*50)

valid_evs = analysis[analysis['evs'].notna() & (analysis['on_hand_qty'] > 0)]
for (low, high), label in zip(evs_bins, evs_labels):
    mask = (valid_evs['evs'] > low) & (valid_evs['evs'] <= high)
    subset = valid_evs[mask]
    count = len(subset)
    value = subset['on_hand_value'].sum()
    pct = value / total_inv * 100 if total_inv > 0 else 0
    print(f"{label:<15} {count:>6} ${int(value):>13,} {pct:>9.1f}%")

# --- Trend Analysis ---
print("\n" + "="*90)
print("TREND ANALYSIS (L3M vs L12M Run Rate)")
print("="*90)

trend_summary = analysis[analysis['on_hand_qty'] > 0].groupby('trend').agg({
    'sku': 'count',
    'on_hand_value': 'sum',
    'l12m_revenue': 'sum'
}).round(0)
trend_summary.columns = ['SKUs', 'Inv_Value', 'L12M_Revenue']
trend_summary = trend_summary.sort_values('Inv_Value', ascending=False)

print(f"\n{'Trend':<15} {'SKUs':>6} {'Inv Value':>14} {'L12M Revenue':>14}")
print("-"*55)
for idx, row in trend_summary.iterrows():
    print(f"{idx:<15} {int(row['SKUs']):>6} ${int(row['Inv_Value']):>13,} ${int(row['L12M_Revenue']):>13,}")

# --- LIQUIDATE Cohort Detail ---
print("\n" + "="*90)
print("LIQUIDATION CANDIDATES - DETAILED ANALYSIS")
print("="*90)

liquidate = analysis[analysis['action'] == 'LIQUIDATE'].copy()
liquidate = liquidate.sort_values('on_hand_value', ascending=False)

liquidate_value = liquidate['on_hand_value'].sum()
liquidate_floor = liquidate['floor_proceeds'].sum()
write_off = liquidate_value - liquidate_floor

print(f"\nTotal Liquidation Candidates: {len(liquidate)} SKUs")
print(f"  Inventory Value:  ${liquidate_value:>12,.0f}")
print(f"  Floor Proceeds:   ${liquidate_floor:>12,.0f} ({SCRAP_RECOVERY_RATE*100:.0f}% recovery)")
print(f"  Net Write-Off:    ${write_off:>12,.0f}")

print(f"\n{'SKU':<15} {'Class':<12} {'On-Hand':>8} {'L12M Units':>10} {'Turns':>7} {'EVS':>8} {'Value':>12} {'Floor $':>10}")
print("-"*95)

for _, row in liquidate.head(25).iterrows():
    item_class = str(row['item_class'])[:11] if pd.notna(row['item_class']) else 'N/A'
    turns_str = f"{row['turns']:.2f}" if row['turns'] > 0 else "0.00"
    evs_str = f"{row['evs']*100:.0f}%" if pd.notna(row['evs']) else "N/A"
    print(f"{str(row['sku']):<15} {item_class:<12} {int(row['on_hand_qty']):>8,} {int(row['l12m_units']):>10,} {turns_str:>7} {evs_str:>8} ${row['on_hand_value']:>11,.0f} ${row['floor_proceeds']:>9,.0f}")

if len(liquidate) > 25:
    print(f"\n... and {len(liquidate) - 25} more liquidation candidates")

# --- REVIEW Cohort ---
print("\n" + "="*90)
print("REVIEW ITEMS - NEEDS FURTHER ANALYSIS")
print("="*90)

review = analysis[analysis['action'] == 'REVIEW'].copy()
review = review.sort_values('on_hand_value', ascending=False)

print(f"\nTotal Review Items: {len(review)} SKUs, ${review['on_hand_value'].sum():,.0f} value")
print(f"\n{'SKU':<15} {'Trend':<12} {'On-Hand':>8} {'L12M Units':>10} {'Turns':>7} {'EVS':>8} {'Backlog':>8} {'Value':>12}")
print("-"*95)

for _, row in review.head(20).iterrows():
    turns_str = f"{row['turns']:.2f}" if row['turns'] > 0 else "0.00"
    evs_str = f"{row['evs']*100:.0f}%" if pd.notna(row['evs']) else "N/A"
    print(f"{str(row['sku']):<15} {row['trend']:<12} {int(row['on_hand_qty']):>8,} {int(row['l12m_units']):>10,} {turns_str:>7} {evs_str:>8} {int(row['backlog_units']):>8,} ${row['on_hand_value']:>11,.0f}")

if len(review) > 20:
    print(f"\n... and {len(review) - 20} more items to review")

# --- Stocking Optimization Summary ---
print("\n" + "="*90)
print("STOCKING OPTIMIZATION - EXCESS INVENTORY ANALYSIS")
print("="*90)

excess_skus = analysis[(analysis['excess_qty'] > 0) & (analysis['action'] != 'LIQUIDATE')].copy()
excess_skus = excess_skus.sort_values('excess_value', ascending=False)

print(f"\nTarget Coverage: {TARGET_COVERAGE_MONTHS} months (Lead Time: {REORDER_LEAD_TIME_MONTHS}mo + Safety: {SAFETY_BUFFER_MONTHS}mo)")
print(f"SKUs with Excess (beyond target): {len(excess_skus)}")
print(f"Total Excess Value: ${excess_skus['excess_value'].sum():,.0f}")

print(f"\n{'SKU':<15} {'On-Hand':>8} {'L12M Units':>10} {'Mo Demand':>10} {'Target':>8} {'Excess':>8} {'Excess $':>12}")
print("-"*85)

for _, row in excess_skus.head(20).iterrows():
    print(f"{str(row['sku']):<15} {int(row['on_hand_qty']):>8,} {int(row['l12m_units']):>10,} {row['monthly_demand']:>10,.1f} {row['target_stock']:>8,.0f} {int(row['excess_qty']):>8,} ${row['excess_value']:>11,.0f}")

# --- Save Detailed Reports ---
output_cols = [
    'sku', 'item_class', 'vendor', 'action', 'trend',
    'on_hand_qty', 'on_water_qty', 'on_order_qty', 'backlog_units',
    'l3m_units', 'l12m_units', 'months_with_sales',
    'l3m_monthly_rate', 'l12m_monthly_rate',
    'turns', 'gm_pct', 'evs',
    'weeks_of_supply', 'months_of_supply_l3m',
    'unit_cost_landed', 'on_hand_value',
    'target_stock', 'excess_qty', 'excess_value',
    'floor_proceeds',
    'l12m_revenue', 'l12m_gp', 'l12m_cogs'
]

analysis[output_cols].to_csv(os.path.join(base_dir, 'analysis/inventory_disposition_full.csv'), index=False)

# Liquidation candidates export
liquidate[output_cols].to_csv(os.path.join(base_dir, 'analysis/liquidation_candidates.csv'), index=False)

# Review items export
review[output_cols].to_csv(os.path.join(base_dir, 'analysis/review_items.csv'), index=False)

# --- Executive Summary ---
print("\n" + "="*90)
print("EXECUTIVE SUMMARY & RECOMMENDATIONS")
print("="*90)

keep_value = analysis[analysis['action'] == 'KEEP']['on_hand_value'].sum()
marginal_value = analysis[analysis['action'] == 'MARGINAL']['on_hand_value'].sum()
review_value = review['on_hand_value'].sum()

print(f"""
INVENTORY DISPOSITION SUMMARY:
┌─────────────────────────────────────────────────────────────────────────────┐
│ Category          │ SKUs    │ Inventory Value   │ % of Total │ Action      │
├─────────────────────────────────────────────────────────────────────────────┤
│ KEEP              │ {len(analysis[analysis['action']=='KEEP']):>6}  │ ${keep_value:>15,.0f} │ {keep_value/total_inv*100:>9.1f}% │ Maintain    │
│ MARGINAL          │ {len(analysis[analysis['action']=='MARGINAL']):>6}  │ ${marginal_value:>15,.0f} │ {marginal_value/total_inv*100:>9.1f}% │ Monitor     │
│ REVIEW            │ {len(review):>6}  │ ${review_value:>15,.0f} │ {review_value/total_inv*100:>9.1f}% │ Investigate │
│ LIQUIDATE         │ {len(liquidate):>6}  │ ${liquidate_value:>15,.0f} │ {liquidate_value/total_inv*100:>9.1f}% │ Scrap/Sell  │
└─────────────────────────────────────────────────────────────────────────────┘

WORKING CAPITAL OPPORTUNITY:
  • Liquidation Value:        ${liquidate_value:>12,.0f}
  • Expected Floor Proceeds:  ${liquidate_floor:>12,.0f} ({SCRAP_RECOVERY_RATE*100:.0f}% recovery)
  • Excess Stock (non-liq):   ${excess_skus['excess_value'].sum():>12,.0f}
  • Total W/C Opportunity:    ${liquidate_value + excess_skus['excess_value'].sum():>12,.0f}

KEY ASSUMPTIONS:
  • Cost of Capital: {COST_OF_CAPITAL*100:.0f}% annual
  • Physical Carry: ${PHYSICAL_CARRY_PER_PART_MONTH}/part/month
  • Scrap Recovery: {SCRAP_RECOVERY_RATE*100:.0f}% of landed cost
  • Target Coverage: {TARGET_COVERAGE_MONTHS} months (LT: {REORDER_LEAD_TIME_MONTHS}mo + Safety: {SAFETY_BUFFER_MONTHS}mo)

NEXT STEPS:
  1. Review LIQUIDATE list - confirm no pending POs or customer commitments
  2. Check REVIEW items for seasonal patterns or customer-specific demand
  3. Validate floor proceeds assumptions with scrap vendors
  4. Update purchasing policies to prevent future SLOB accumulation

REPORTS GENERATED:
  • analysis/inventory_disposition_full.csv (complete analysis)
  • analysis/liquidation_candidates.csv (LIQUIDATE cohort)
  • analysis/review_items.csv (REVIEW cohort)
""")

print("="*90)
