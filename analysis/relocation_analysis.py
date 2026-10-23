#!/usr/bin/env python3
"""
DuraBrake Relocation vs Scrap Analysis
Evaluates transfer economics for stranded inventory
"""

import pandas as pd
import numpy as np
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================================
# TRANSFER COST ASSUMPTIONS
# ============================================================================

# Estimated transfer costs (freight + handling)
TRANSFER_COST_PER_LB = 0.35  # $/lb for LTL freight
AVG_WEIGHT_PER_UNIT = 15  # lbs (brake components avg)
HANDLING_COST_PER_UNIT = 2.00  # receiving, put-away

# Minimum value threshold to justify transfer
MIN_VALUE_FOR_TRANSFER = 500  # Don't transfer if value < $500
MIN_MARGIN_AFTER_TRANSFER = 0.10  # Need 10%+ margin after transfer cost

# Scrap recovery
SCRAP_RECOVERY_RATE = 0.10

print("="*100)
print("RELOCATION vs SCRAP ANALYSIS")
print("="*100)

# Load the merged analysis
analysis = pd.read_csv(os.path.join(base_dir, 'analysis/merged_disposition_full.csv'))

# Load velocity data to find best destination DC
velocity = pd.read_csv(os.path.join(base_dir, 'data/velocity.csv'))
velocity['month'] = pd.to_datetime(velocity['month'])
max_month = velocity['month'].max()
l12m_start = max_month - pd.DateOffset(months=11)
vel_l12m = velocity[velocity['month'] >= l12m_start]

# Get L12M sales by SKU×DC
dc_velocity = vel_l12m.groupby(['sku', 'dc']).agg({
    'fulfilled_units': 'sum',
    'revenue': 'sum',
    'gp_dollars': 'sum'
}).reset_index()
dc_velocity.columns = ['sku', 'dc', 'dest_l12m_units', 'dest_l12m_revenue', 'dest_l12m_gp']

# ============================================================================
# IDENTIFY RELOCATION CANDIDATES
# ============================================================================

relocate = analysis[analysis['disposition'] == 'RELOCATE'].copy()

print(f"\nRelocation candidates: {len(relocate)} SKU×DC rows, ${relocate['on_hand_value'].sum():,.0f} total value")

# ============================================================================
# FIND BEST DESTINATION FOR EACH
# ============================================================================

def find_best_destination(row, dc_velocity):
    """Find the DC with highest velocity for this SKU (excluding current DC)"""
    sku = row['sku']
    current_dc = row['dc']

    # Get all DCs selling this SKU
    sku_dcs = dc_velocity[dc_velocity['sku'] == sku].copy()
    sku_dcs = sku_dcs[sku_dcs['dc'] != current_dc]  # Exclude current

    if len(sku_dcs) == 0:
        return None, 0, 0, 0

    # Find highest velocity DC
    best = sku_dcs.loc[sku_dcs['dest_l12m_units'].idxmax()]
    return best['dc'], best['dest_l12m_units'], best['dest_l12m_revenue'], best['dest_l12m_gp']

# Apply to each relocation candidate
results = []
for idx, row in relocate.iterrows():
    dest_dc, dest_units, dest_rev, dest_gp = find_best_destination(row, dc_velocity)

    # Transfer cost calculation
    units = row['on_hand_qty']
    transfer_cost = units * (AVG_WEIGHT_PER_UNIT * TRANSFER_COST_PER_LB + HANDLING_COST_PER_UNIT)

    # Economics
    inventory_value = row['on_hand_value']
    scrap_recovery = inventory_value * SCRAP_RECOVERY_RATE

    # Expected margin at destination (use destination's realized margin)
    if dest_units and dest_units > 0:
        dest_margin_pct = dest_gp / dest_rev if dest_rev > 0 else 0.40
        dest_monthly_rate = dest_units / 12
        months_to_sell = units / dest_monthly_rate if dest_monthly_rate > 0 else 999
        expected_gp = units * (dest_rev / dest_units) * dest_margin_pct if dest_units > 0 else 0
        net_benefit = expected_gp - transfer_cost - scrap_recovery  # vs scrapping
    else:
        dest_margin_pct = 0
        months_to_sell = 999
        expected_gp = 0
        net_benefit = -transfer_cost  # No benefit, just cost

    # Recommendation
    if inventory_value < MIN_VALUE_FOR_TRANSFER:
        recommendation = 'SCRAP_LOW_VALUE'
        reason = f'Value ${inventory_value:.0f} < ${MIN_VALUE_FOR_TRANSFER} threshold'
    elif dest_dc is None:
        recommendation = 'SCRAP_NO_DEST'
        reason = 'No other DC selling this SKU'
    elif months_to_sell > 24:
        recommendation = 'SCRAP_SLOW_DEST'
        reason = f'{months_to_sell:.0f} months to sell at destination'
    elif transfer_cost > expected_gp * 0.5:
        recommendation = 'SCRAP_HIGH_XFER'
        reason = f'Transfer cost ${transfer_cost:.0f} > 50% of expected GP ${expected_gp:.0f}'
    elif net_benefit < 0:
        recommendation = 'SCRAP_NEG_NPV'
        reason = f'Net benefit ${net_benefit:.0f} < $0 vs scrap'
    else:
        recommendation = 'RELOCATE'
        reason = f'Net benefit ${net_benefit:.0f} over scrap'

    results.append({
        'sku': row['sku'],
        'from_dc': row['dc'],
        'to_dc': dest_dc if dest_dc else 'N/A',
        'units': int(units),
        'inventory_value': inventory_value,
        'transfer_cost': transfer_cost,
        'scrap_recovery': scrap_recovery,
        'dest_l12m_units': int(dest_units) if dest_units else 0,
        'dest_margin_pct': dest_margin_pct,
        'months_to_sell': months_to_sell,
        'expected_gp': expected_gp,
        'net_benefit_vs_scrap': net_benefit,
        'recommendation': recommendation,
        'reason': reason,
        'unit_cost': row['unit_cost_landed'],
        'network_l12m_units': row['network_l12m_units']
    })

relo_analysis = pd.DataFrame(results)

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "="*100)
print("RECOMMENDATION SUMMARY")
print("="*100)

rec_summary = relo_analysis.groupby('recommendation').agg({
    'sku': 'count',
    'inventory_value': 'sum',
    'transfer_cost': 'sum',
    'net_benefit_vs_scrap': 'sum'
}).round(0)
rec_summary.columns = ['Rows', 'Inv_Value', 'Transfer_Cost', 'Net_Benefit']

print(f"\n{'Recommendation':<20} {'Rows':>6} {'Inv Value':>12} {'Xfer Cost':>12} {'Net Benefit':>12}")
print("-"*70)
for idx, row in rec_summary.iterrows():
    print(f"{idx:<20} {int(row['Rows']):>6} ${int(row['Inv_Value']):>11,} ${int(row['Transfer_Cost']):>11,} ${int(row['Net_Benefit']):>11,}")

# ============================================================================
# RELOCATE RECOMMENDATIONS (worth transferring)
# ============================================================================

print("\n" + "="*100)
print("RECOMMENDED TRANSFERS (positive net benefit vs scrap)")
print("="*100)

transfers = relo_analysis[relo_analysis['recommendation'] == 'RELOCATE'].copy()
transfers = transfers.sort_values('net_benefit_vs_scrap', ascending=False)

if len(transfers) > 0:
    print(f"\nTotal: {len(transfers)} transfers, ${transfers['inventory_value'].sum():,.0f} value")
    print(f"Transfer cost: ${transfers['transfer_cost'].sum():,.0f}")
    print(f"Net benefit vs scrap: ${transfers['net_benefit_vs_scrap'].sum():,.0f}")

    print(f"\n{'SKU':<12} {'From':<18} {'To':<18} {'Units':>6} {'Value':>10} {'XferCost':>10} {'NetBenefit':>10} {'MoToSell':>8}")
    print("-"*105)
    for _, row in transfers.iterrows():
        print(f"{str(row['sku']):<12} {str(row['from_dc']):<18} {str(row['to_dc']):<18} {row['units']:>6} ${row['inventory_value']:>9,.0f} ${row['transfer_cost']:>9,.0f} ${row['net_benefit_vs_scrap']:>9,.0f} {row['months_to_sell']:>8.1f}")
else:
    print("\nNo transfers recommended - all candidates better off scrapped")

# ============================================================================
# SCRAP RECOMMENDATIONS (not worth transferring)
# ============================================================================

print("\n" + "="*100)
print("RECOMMENDED SCRAP (transfer not economical)")
print("="*100)

scrap = relo_analysis[relo_analysis['recommendation'] != 'RELOCATE'].copy()
scrap = scrap.sort_values('inventory_value', ascending=False)

print(f"\nTotal: {len(scrap)} items, ${scrap['inventory_value'].sum():,.0f} value")
print(f"Scrap recovery (10%): ${scrap['scrap_recovery'].sum():,.0f}")
print(f"Net write-down: ${(scrap['inventory_value'].sum() - scrap['scrap_recovery'].sum()):,.0f}")

print(f"\n{'SKU':<12} {'DC':<18} {'Units':>6} {'Value':>10} {'Recovery':>10} {'Reason':<35}")
print("-"*105)
for _, row in scrap.iterrows():
    print(f"{str(row['sku']):<12} {str(row['from_dc']):<18} {row['units']:>6} ${row['inventory_value']:>9,.0f} ${row['scrap_recovery']:>9,.0f} {row['reason']:<35}")

# ============================================================================
# COMBINED WITH ORIGINAL SCRAP LIST
# ============================================================================

print("\n" + "="*100)
print("FINAL SCRAP LIST (original + non-transferable relocations)")
print("="*100)

# Original scrap candidates
original_scrap = analysis[analysis['disposition'] == 'SCRAP'].copy()

# Items we're now recommending to scrap (was RELOCATE)
new_scrap = scrap.copy()
new_scrap['write_down'] = new_scrap['inventory_value'] * 0.90
new_scrap['recovery'] = new_scrap['inventory_value'] * 0.10

total_scrap_value = original_scrap['on_hand_value'].sum() + new_scrap['inventory_value'].sum()
total_write_down = original_scrap['write_down'].sum() + new_scrap['write_down'].sum()
total_recovery = original_scrap['recovery'].sum() + new_scrap['recovery'].sum()

print(f"""
FINAL SCRAP POSITION:
┌─────────────────────────────────────┬──────────┬─────────────────┬─────────────────┐
│ Category                            │ Rows     │ Inventory Value │ Write-Down      │
├─────────────────────────────────────┼──────────┼─────────────────┼─────────────────┤
│ Original SCRAP (dead everywhere)    │ {len(original_scrap):>6}   │ ${original_scrap['on_hand_value'].sum():>14,.0f} │ ${original_scrap['write_down'].sum():>14,.0f} │
│ Non-transferable (was RELOCATE)     │ {len(new_scrap):>6}   │ ${new_scrap['inventory_value'].sum():>14,.0f} │ ${new_scrap['write_down'].sum():>14,.0f} │
├─────────────────────────────────────┼──────────┼─────────────────┼─────────────────┤
│ TOTAL SCRAP                         │ {len(original_scrap) + len(new_scrap):>6}   │ ${total_scrap_value:>14,.0f} │ ${total_write_down:>14,.0f} │
│ Expected Recovery (10%)             │          │                 │ ${total_recovery:>14,.0f} │
└─────────────────────────────────────┴──────────┴─────────────────┴─────────────────┘
""")

# ============================================================================
# SAVE OUTPUTS
# ============================================================================

relo_analysis.to_csv(os.path.join(base_dir, 'analysis/relocation_economics.csv'), index=False)

# Final action list
final_scrap_list = []

# Add original scrap
for _, row in original_scrap.iterrows():
    final_scrap_list.append({
        'sku': row['sku'],
        'dc': row['dc'],
        'units': row['on_hand_qty'],
        'value': row['on_hand_value'],
        'write_down': row['write_down'],
        'recovery': row['recovery'],
        'source': 'DEAD_STOCK',
        'reason': 'Zero network sales, EVS < -25%'
    })

# Add non-transferable
for _, row in new_scrap.iterrows():
    final_scrap_list.append({
        'sku': row['sku'],
        'dc': row['from_dc'],
        'units': row['units'],
        'value': row['inventory_value'],
        'write_down': row['write_down'],
        'recovery': row['recovery'],
        'source': 'NON_TRANSFERABLE',
        'reason': row['reason']
    })

final_scrap_df = pd.DataFrame(final_scrap_list)
final_scrap_df = final_scrap_df.sort_values('value', ascending=False)
final_scrap_df.to_csv(os.path.join(base_dir, 'analysis/final_scrap_list.csv'), index=False)

# Transfer list
if len(transfers) > 0:
    transfers.to_csv(os.path.join(base_dir, 'analysis/approved_transfers.csv'), index=False)

print(f"""
FILES GENERATED:
  • analysis/relocation_economics.csv (full transfer analysis)
  • analysis/final_scrap_list.csv (combined scrap list with reasons)
  • analysis/approved_transfers.csv (recommended transfers)

TRANSFER ASSUMPTIONS:
  • Freight: ${TRANSFER_COST_PER_LB}/lb LTL
  • Avg weight: {AVG_WEIGHT_PER_UNIT} lbs/unit
  • Handling: ${HANDLING_COST_PER_UNIT}/unit
  • Min value threshold: ${MIN_VALUE_FOR_TRANSFER}
  • Scrap recovery: {SCRAP_RECOVERY_RATE*100:.0f}%
""")

print("="*100)
