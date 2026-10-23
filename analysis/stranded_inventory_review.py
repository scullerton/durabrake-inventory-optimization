#!/usr/bin/env python3
"""
DuraBrake Stranded Inventory Review
Lists inventory that's not selling at its current DC for manual evaluation
No automated recommendations - presents data for discussion
"""

import pandas as pd
import numpy as np
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("="*100)
print("STRANDED INVENTORY REVIEW")
print("Items with zero sales at current DC - evaluate for transfer or scrap")
print("="*100)

# Load the merged analysis
analysis = pd.read_csv(os.path.join(base_dir, 'analysis/merged_disposition_full.csv'))

# Load velocity data for destination options
velocity = pd.read_csv(os.path.join(base_dir, 'data/velocity.csv'))
velocity['month'] = pd.to_datetime(velocity['month'])
max_month = velocity['month'].max()
l12m_start = max_month - pd.DateOffset(months=11)
vel_l12m = velocity[velocity['month'] >= l12m_start]

# Get L12M sales by SKU×DC
dc_velocity = vel_l12m.groupby(['sku', 'dc']).agg({
    'fulfilled_units': 'sum',
    'revenue': 'sum'
}).reset_index()

# ============================================================================
# STRANDED INVENTORY: Zero DC sales but has network sales
# ============================================================================

stranded = analysis[(analysis['disposition'] == 'RELOCATE') |
                    ((analysis['l12m_units'] == 0) &
                     (analysis['network_l12m_units'] > 0) &
                     (analysis['on_hand_qty'] > 0))].copy()

stranded = stranded.sort_values('on_hand_value', ascending=False)

print(f"\nTotal stranded items: {len(stranded)} SKU×DC combinations")
print(f"Total value: ${stranded['on_hand_value'].sum():,.0f}")

# ============================================================================
# BUILD REVIEW TABLE WITH DESTINATION OPTIONS
# ============================================================================

review_data = []

for idx, row in stranded.iterrows():
    sku = row['sku']
    current_dc = row['dc']

    # Find all DCs where this SKU is selling
    sku_sales = dc_velocity[dc_velocity['sku'] == sku].copy()
    sku_sales = sku_sales[sku_sales['dc'] != current_dc]
    sku_sales = sku_sales.sort_values('fulfilled_units', ascending=False)

    # Get top 3 destination options
    destinations = []
    for _, dest in sku_sales.head(3).iterrows():
        monthly_rate = dest['fulfilled_units'] / 12
        months_to_sell = row['on_hand_qty'] / monthly_rate if monthly_rate > 0 else 999
        destinations.append({
            'dc': dest['dc'],
            'l12m_units': int(dest['fulfilled_units']),
            'months_to_sell': round(months_to_sell, 1)
        })

    # Determine if cross-border
    canada_dcs = ['Vancouver, BC', 'Container (Canada)']
    us_dcs = ['Sacramento, CA', 'Edison, NJ', 'Tacoma, WA', 'Houston, TX', 'Container (US)']

    current_country = 'CA' if current_dc in canada_dcs else 'US'

    review_data.append({
        'sku': sku,
        'current_dc': current_dc,
        'current_country': current_country,
        'units': int(row['on_hand_qty']),
        'value': row['on_hand_value'],
        'unit_cost': row['unit_cost_landed'],
        'network_l12m_units': int(row['network_l12m_units']),
        'evs': row['evs'],
        'dest_1_dc': destinations[0]['dc'] if len(destinations) > 0 else None,
        'dest_1_l12m': destinations[0]['l12m_units'] if len(destinations) > 0 else 0,
        'dest_1_mos': destinations[0]['months_to_sell'] if len(destinations) > 0 else None,
        'dest_2_dc': destinations[1]['dc'] if len(destinations) > 1 else None,
        'dest_2_l12m': destinations[1]['l12m_units'] if len(destinations) > 1 else 0,
        'dest_3_dc': destinations[2]['dc'] if len(destinations) > 2 else None,
        'dest_3_l12m': destinations[2]['l12m_units'] if len(destinations) > 2 else 0,
    })

review_df = pd.DataFrame(review_data)

# ============================================================================
# DEAD STOCK: Zero sales everywhere
# ============================================================================

dead = analysis[(analysis['disposition'] == 'SCRAP') |
                ((analysis['network_l12m_units'] == 0) &
                 (analysis['backlog_units'] == 0) &
                 (analysis['on_hand_qty'] > 0))].copy()

dead = dead.sort_values('on_hand_value', ascending=False)

# ============================================================================
# PRINT REPORTS
# ============================================================================

print("\n" + "="*100)
print("STRANDED AT VANCOUVER, BC (Canadian inventory)")
print("Transfer to US requires customs/duties consideration")
print("="*100)

van = review_df[review_df['current_dc'] == 'Vancouver, BC'].copy()
print(f"\n{len(van)} items, ${van['value'].sum():,.0f} value\n")

print(f"{'SKU':<12} {'Units':>6} {'Value':>10} {'Net L12M':>8} │ {'Best Dest':<18} {'L12M':>6} {'MosSell':>7} │ {'Alt Dest':<18}")
print("-"*110)
for _, row in van.iterrows():
    dest1 = f"{row['dest_1_dc']}" if row['dest_1_dc'] else "None"
    dest2 = f"{row['dest_2_dc']}" if row['dest_2_dc'] else ""
    mos = f"{row['dest_1_mos']:.1f}" if row['dest_1_mos'] and row['dest_1_mos'] < 999 else "N/A"
    print(f"{str(row['sku']):<12} {row['units']:>6} ${row['value']:>9,.0f} {row['network_l12m_units']:>8} │ {dest1:<18} {row['dest_1_l12m']:>6} {mos:>7} │ {dest2:<18}")

print("\n" + "="*100)
print("STRANDED AT CONTAINER (CANADA)")
print("="*100)

can_cont = review_df[review_df['current_dc'] == 'Container (Canada)'].copy()
if len(can_cont) > 0:
    print(f"\n{len(can_cont)} items, ${can_cont['value'].sum():,.0f} value\n")
    for _, row in can_cont.iterrows():
        dest1 = f"{row['dest_1_dc']}" if row['dest_1_dc'] else "None"
        mos = f"{row['dest_1_mos']:.1f}" if row['dest_1_mos'] and row['dest_1_mos'] < 999 else "N/A"
        print(f"{str(row['sku']):<12} {row['units']:>6} ${row['value']:>9,.0f} {row['network_l12m_units']:>8} │ {dest1:<18} {row['dest_1_l12m']:>6} {mos:>7}")
else:
    print("\nNo items")

print("\n" + "="*100)
print("STRANDED AT US DCs (domestic transfer only)")
print("="*100)

us_stranded = review_df[review_df['current_country'] == 'US'].copy()
print(f"\n{len(us_stranded)} items, ${us_stranded['value'].sum():,.0f} value\n")

print(f"{'SKU':<12} {'Current DC':<18} {'Units':>6} {'Value':>10} │ {'Best Dest':<18} {'L12M':>6} {'MosSell':>7}")
print("-"*95)
for _, row in us_stranded.iterrows():
    dest1 = f"{row['dest_1_dc']}" if row['dest_1_dc'] else "None"
    mos = f"{row['dest_1_mos']:.1f}" if row['dest_1_mos'] and row['dest_1_mos'] < 999 else "N/A"
    print(f"{str(row['sku']):<12} {str(row['current_dc']):<18} {row['units']:>6} ${row['value']:>9,.0f} │ {dest1:<18} {row['dest_1_l12m']:>6} {mos:>7}")

print("\n" + "="*100)
print("DEAD STOCK (Zero sales everywhere - clear scrap candidates)")
print("="*100)

print(f"\n{len(dead)} items, ${dead['on_hand_value'].sum():,.0f} value\n")

print(f"{'SKU':<12} {'DC':<18} {'Units':>6} {'Value':>10} {'Unit Cost':>10} {'EVS':>8}")
print("-"*75)
for _, row in dead.iterrows():
    evs_str = f"{row['evs']*100:.0f}%" if pd.notna(row['evs']) else "N/A"
    print(f"{str(row['sku']):<12} {str(row['dc']):<18} {int(row['on_hand_qty']):>6} ${row['on_hand_value']:>9,.0f} ${row['unit_cost_landed']:>9,.2f} {evs_str:>8}")

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "="*100)
print("SUMMARY FOR REVIEW")
print("="*100)

print(f"""
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ Category                              │ Items    │ Value          │ Consideration       │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ Stranded in Canada (Vancouver/Cont)   │ {len(van) + len(can_cont):>6}   │ ${(van['value'].sum() + can_cont['value'].sum()):>13,.0f} │ Cross-border costs  │
│ Stranded in US (domestic transfer)    │ {len(us_stranded):>6}   │ ${us_stranded['value'].sum():>13,.0f} │ Freight only        │
│ Dead stock (no sales anywhere)        │ {len(dead):>6}   │ ${dead['on_hand_value'].sum():>13,.0f} │ Scrap               │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ TOTAL                                 │ {len(review_df) + len(dead):>6}   │ ${review_df['value'].sum() + dead['on_hand_value'].sum():>13,.0f} │                     │
└─────────────────────────────────────────────────────────────────────────────────────────┘

CROSS-BORDER CONSIDERATIONS (Canada → US):
  • Customs duties (varies by HTS code - brake components typically 0-2.5%)
  • Customs brokerage fees (~$50-150 per shipment)
  • GST/HST implications on goods leaving Canada
  • USMCA preferential treatment if goods qualify

DOMESTIC TRANSFER CONSIDERATIONS:
  • LTL freight (varies by lane, weight, class)
  • Receiving/put-away labor at destination
  • Potential backhaul opportunities

QUESTIONS FOR EACH ITEM:
  1. What's the realistic transfer cost for this specific lane?
  2. Is the destination DC actually short on this SKU?
  3. Any customer commitments that make this urgent?
  4. Scrap recovery value vs transfer cost break-even?
""")

# ============================================================================
# SAVE OUTPUT
# ============================================================================

review_df.to_csv(os.path.join(base_dir, 'analysis/stranded_inventory_review.csv'), index=False)

dead_output = dead[['sku', 'dc', 'on_hand_qty', 'on_hand_value', 'unit_cost_landed', 'evs', 'backlog_units']].copy()
dead_output.to_csv(os.path.join(base_dir, 'analysis/dead_stock_final.csv'), index=False)

print(f"""
FILES GENERATED:
  • analysis/stranded_inventory_review.csv (all stranded items with destination options)
  • analysis/dead_stock_final.csv (zero-sales items for scrap)
""")

print("="*100)
