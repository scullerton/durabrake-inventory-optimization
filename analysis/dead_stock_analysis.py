#!/usr/bin/env python3
"""
DuraBrake Dead/Slow Stock Analysis
Identifies inventory scrap candidates based on velocity, turns, and backlog coverage
"""

import pandas as pd
import numpy as np
from datetime import datetime

# Load data
inventory = pd.read_csv('../data/466783f7-fmp_inventory_20261022.csv')
backlog = pd.read_csv('../data/9d6f277b-fmp_backlog_20261022.csv')
velocity = pd.read_csv('../data/40c51672-fmp_velocity_20261022.csv')

# Rename files for clarity
inventory.to_csv('../data/inventory.csv', index=False)
backlog.to_csv('../data/backlog.csv', index=False)
velocity.to_csv('../data/velocity.csv', index=False)

print("="*80)
print("DURABRAKE DEAD/SLOW STOCK ANALYSIS")
print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d')}")
print("="*80)

# --- Data Preparation ---

# Aggregate backlog by SKU (network-wide committed units)
backlog_by_sku = backlog.groupby('sku').agg({
    'committed_units': 'sum',
    'days_until_due': 'min'  # most urgent order
}).reset_index()
backlog_by_sku.columns = ['sku', 'total_committed', 'most_urgent_days']

# Aggregate inventory by SKU (network-wide)
inventory_agg = inventory.groupby('sku').agg({
    'on_hand_qty': 'sum',
    'on_water_qty': 'sum',
    'on_order_qty': 'sum',
    'in_transit_qty': 'sum',
    'velocity_3mo_units': 'sum',
    'velocity_12mo_units': 'sum',
    'unit_cost_landed': 'first',  # use first non-null cost
    'item_class': 'first',
    'vendor': 'first'
}).reset_index()

# Merge with backlog
analysis = inventory_agg.merge(backlog_by_sku, on='sku', how='left')
analysis['total_committed'] = analysis['total_committed'].fillna(0)
analysis['most_urgent_days'] = analysis['most_urgent_days'].fillna(999)

# --- Calculate Key Metrics ---

# Total inventory position
analysis['total_inventory'] = (
    analysis['on_hand_qty'] +
    analysis['on_water_qty'] +
    analysis['on_order_qty']
)

# Available inventory (on-hand minus committed)
analysis['available_qty'] = analysis['on_hand_qty'] - analysis['total_committed']
analysis['available_qty'] = analysis['available_qty'].clip(lower=0)

# Annualized demand (use 12mo velocity, fallback to 3mo * 4)
analysis['annual_demand'] = analysis['velocity_12mo_units']
mask_no_12mo = analysis['annual_demand'] == 0
analysis.loc[mask_no_12mo, 'annual_demand'] = analysis.loc[mask_no_12mo, 'velocity_3mo_units'] * 4

# Inventory turns (on-hand / annual demand)
analysis['turns'] = np.where(
    analysis['on_hand_qty'] > 0,
    analysis['annual_demand'] / analysis['on_hand_qty'],
    np.nan
)

# Weeks of supply (on-hand / weekly demand)
analysis['weekly_demand'] = analysis['annual_demand'] / 52
analysis['weeks_of_supply'] = np.where(
    analysis['weekly_demand'] > 0,
    analysis['on_hand_qty'] / analysis['weekly_demand'],
    np.inf
)

# Excess inventory (on-hand beyond 52 weeks of supply)
analysis['target_stock'] = analysis['weekly_demand'] * 52  # 1 year supply
analysis['excess_qty'] = (analysis['on_hand_qty'] - analysis['target_stock']).clip(lower=0)

# Inventory value
analysis['on_hand_value'] = analysis['on_hand_qty'] * analysis['unit_cost_landed']
analysis['excess_value'] = analysis['excess_qty'] * analysis['unit_cost_landed']

# --- Classify Dead/Slow Stock ---

def classify_stock(row):
    """Classify stock health based on velocity and backlog"""
    has_demand = row['annual_demand'] > 0
    has_backlog = row['total_committed'] > 0
    has_inventory = row['on_hand_qty'] > 0

    if not has_inventory:
        return 'NO_STOCK'

    # Dead stock: no demand AND no backlog
    if not has_demand and not has_backlog:
        return 'DEAD'

    # Very slow: < 0.5 turns/year, no near-term backlog
    if row['turns'] < 0.5 and row['most_urgent_days'] > 90:
        return 'VERY_SLOW'

    # Slow: 0.5-1.0 turns/year
    if row['turns'] < 1.0:
        return 'SLOW'

    # Overstocked: > 52 weeks supply but has demand
    if row['weeks_of_supply'] > 52 and has_demand:
        return 'OVERSTOCKED'

    # Healthy
    if row['turns'] >= 2.0:
        return 'HEALTHY'

    return 'MODERATE'

analysis['stock_class'] = analysis.apply(classify_stock, axis=1)

# --- Generate Reports ---

print("\n" + "="*80)
print("INVENTORY HEALTH SUMMARY")
print("="*80)

summary = analysis.groupby('stock_class').agg({
    'sku': 'count',
    'on_hand_qty': 'sum',
    'on_hand_value': 'sum',
    'excess_value': 'sum'
}).round(0)
summary.columns = ['SKU_Count', 'Total_Units', 'Total_Value', 'Excess_Value']
summary = summary.sort_values('Total_Value', ascending=False)

print(f"\n{'Classification':<15} {'SKUs':>8} {'Units':>12} {'Value ($)':>15} {'Excess ($)':>15}")
print("-"*70)
for idx, row in summary.iterrows():
    print(f"{idx:<15} {int(row['SKU_Count']):>8} {int(row['Total_Units']):>12,} ${int(row['Total_Value']):>14,} ${int(row['Excess_Value']):>14,}")

total_value = analysis['on_hand_value'].sum()
total_excess = analysis['excess_value'].sum()
print("-"*70)
print(f"{'TOTAL':<15} {len(analysis):>8} {int(analysis['on_hand_qty'].sum()):>12,} ${int(total_value):>14,} ${int(total_excess):>14,}")

# --- Dead Stock Detail ---
print("\n" + "="*80)
print("DEAD STOCK - SCRAP CANDIDATES (No Sales, No Backlog)")
print("="*80)

dead_stock = analysis[analysis['stock_class'] == 'DEAD'].copy()
dead_stock = dead_stock.sort_values('on_hand_value', ascending=False)

print(f"\nTotal Dead Stock: {len(dead_stock)} SKUs, ${dead_stock['on_hand_value'].sum():,.0f} value")
print(f"\n{'SKU':<20} {'DC/Class':<25} {'On-Hand':>10} {'Unit Cost':>12} {'Value ($)':>12}")
print("-"*80)

for _, row in dead_stock.head(30).iterrows():
    item_class = str(row['item_class'])[:20] if pd.notna(row['item_class']) else 'N/A'
    print(f"{str(row['sku']):<20} {item_class:<25} {int(row['on_hand_qty']):>10,} ${row['unit_cost_landed']:>11,.2f} ${row['on_hand_value']:>11,.0f}")

if len(dead_stock) > 30:
    print(f"\n... and {len(dead_stock) - 30} more dead stock SKUs")

# --- Very Slow Stock Detail ---
print("\n" + "="*80)
print("VERY SLOW STOCK - REVIEW FOR MARKDOWN/SCRAP (<0.5 turns, no urgent backlog)")
print("="*80)

very_slow = analysis[analysis['stock_class'] == 'VERY_SLOW'].copy()
very_slow = very_slow.sort_values('excess_value', ascending=False)

print(f"\nTotal Very Slow: {len(very_slow)} SKUs, ${very_slow['on_hand_value'].sum():,.0f} value, ${very_slow['excess_value'].sum():,.0f} excess")
print(f"\n{'SKU':<18} {'On-Hand':>8} {'12mo Sales':>10} {'Turns':>7} {'WoS':>8} {'Excess $':>12} {'Committed':>10}")
print("-"*85)

for _, row in very_slow.head(25).iterrows():
    turns_str = f"{row['turns']:.2f}" if pd.notna(row['turns']) else "N/A"
    wos_str = f"{row['weeks_of_supply']:.0f}" if row['weeks_of_supply'] != np.inf else "INF"
    print(f"{str(row['sku']):<18} {int(row['on_hand_qty']):>8,} {int(row['velocity_12mo_units']):>10,} {turns_str:>7} {wos_str:>8} ${row['excess_value']:>11,.0f} {int(row['total_committed']):>10,}")

if len(very_slow) > 25:
    print(f"\n... and {len(very_slow) - 25} more very slow SKUs")

# --- Overstocked Items ---
print("\n" + "="*80)
print("OVERSTOCKED - HAS DEMAND BUT >52 WEEKS SUPPLY")
print("="*80)

overstocked = analysis[analysis['stock_class'] == 'OVERSTOCKED'].copy()
overstocked = overstocked.sort_values('excess_value', ascending=False)

print(f"\nTotal Overstocked: {len(overstocked)} SKUs, ${overstocked['excess_value'].sum():,.0f} excess inventory value")
print(f"\n{'SKU':<18} {'On-Hand':>8} {'12mo Sales':>10} {'Turns':>7} {'WoS':>8} {'Excess Qty':>10} {'Excess $':>12}")
print("-"*85)

for _, row in overstocked.head(20).iterrows():
    turns_str = f"{row['turns']:.2f}" if pd.notna(row['turns']) else "N/A"
    wos_str = f"{row['weeks_of_supply']:.0f}" if row['weeks_of_supply'] != np.inf else "INF"
    print(f"{str(row['sku']):<18} {int(row['on_hand_qty']):>8,} {int(row['velocity_12mo_units']):>10,} {turns_str:>7} {wos_str:>8} {int(row['excess_qty']):>10,} ${row['excess_value']:>11,.0f}")

if len(overstocked) > 20:
    print(f"\n... and {len(overstocked) - 20} more overstocked SKUs")

# --- Save detailed output ---
output_cols = [
    'sku', 'item_class', 'vendor', 'stock_class',
    'on_hand_qty', 'on_water_qty', 'on_order_qty', 'total_committed',
    'velocity_3mo_units', 'velocity_12mo_units', 'annual_demand',
    'turns', 'weeks_of_supply', 'most_urgent_days',
    'unit_cost_landed', 'on_hand_value', 'excess_qty', 'excess_value'
]

analysis[output_cols].to_csv('../analysis/dead_slow_stock_report.csv', index=False)

# Scrap candidates export
scrap_candidates = analysis[analysis['stock_class'].isin(['DEAD', 'VERY_SLOW'])].copy()
scrap_candidates = scrap_candidates.sort_values('on_hand_value', ascending=False)
scrap_candidates[output_cols].to_csv('../analysis/scrap_candidates.csv', index=False)

print("\n" + "="*80)
print("SUMMARY & RECOMMENDATIONS")
print("="*80)

dead_value = dead_stock['on_hand_value'].sum()
very_slow_value = very_slow['on_hand_value'].sum()
very_slow_excess = very_slow['excess_value'].sum()
overstocked_excess = overstocked['excess_value'].sum()

print(f"""
SCRAP CANDIDATES:
  - Dead Stock: {len(dead_stock)} SKUs, ${dead_value:,.0f} (100% scrap candidate)
  - Very Slow:  {len(very_slow)} SKUs, ${very_slow_excess:,.0f} excess beyond 1-year supply

WORKING CAPITAL OPPORTUNITY:
  - Total excess inventory: ${dead_value + very_slow_excess + overstocked_excess:,.0f}
  - Scrap candidate value:  ${dead_value + very_slow_excess:,.0f}

NEXT STEPS:
  1. Review dead stock list - confirm no pending demand or substitution
  2. Check very slow items for customer-specific or seasonal patterns
  3. Consider markdown/liquidation before full scrap write-off
  4. Update purchasing policies to prevent future dead stock

Reports saved to:
  - analysis/dead_slow_stock_report.csv (full analysis)
  - analysis/scrap_candidates.csv (dead + very slow only)
""")

print("="*80)
