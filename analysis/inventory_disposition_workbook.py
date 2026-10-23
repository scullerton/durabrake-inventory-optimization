#!/usr/bin/env python3
"""
DuraBrake Inventory Disposition Workbook
Generates Excel output with full analysis, stats, and rationale
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("Generating Excel workbook...")

# Load all analysis data
merged = pd.read_csv(os.path.join(base_dir, 'analysis/merged_disposition_full.csv'))
stranded = pd.read_csv(os.path.join(base_dir, 'analysis/stranded_inventory_review.csv'))
dead = pd.read_csv(os.path.join(base_dir, 'analysis/dead_stock_final.csv'))

# Load raw data for additional context
inventory = pd.read_csv(os.path.join(base_dir, 'data/inventory.csv'))
velocity = pd.read_csv(os.path.join(base_dir, 'data/velocity.csv'))

# ============================================================================
# SHEET 1: EXECUTIVE SUMMARY
# ============================================================================

summary_data = {
    'Metric': [
        'Analysis Date',
        'Data As-Of',
        '',
        'INVENTORY POSITION',
        'Total SKU×DC Rows',
        'Total On-Hand Units',
        'Total On-Hand Value',
        'Total Excess Value',
        '',
        'DISPOSITION BREAKDOWN',
        'HOLD (healthy)',
        'EXPEDITE (understocked)',
        'REVIEW (borderline)',
        'STOP_REORDER (run out)',
        'LIQUIDATE (markdown)',
        'RELOCATE (stranded)',
        'SCRAP (dead)',
        '',
        'STRANDED INVENTORY DETAIL',
        'Stranded in Canada (Vancouver)',
        'Stranded in US (domestic)',
        'Total Stranded Value',
        '',
        'DEAD STOCK',
        'Items with zero network sales',
        'Dead stock value',
        '',
        'KEY ASSUMPTIONS',
        'Cost of Capital',
        'Lead Time (A-class)',
        'Lead Time (BC-class)',
        'Scrap Recovery Rate',
        'EVS Scrap Threshold',
    ],
    'Value': [
        datetime.now().strftime('%Y-%m-%d'),
        '2026-10-22',
        '',
        '',
        len(merged),
        int(merged['on_hand_qty'].sum()),
        f"${merged['on_hand_value'].sum():,.0f}",
        f"${merged['excess_value'].sum():,.0f}",
        '',
        '',
        f"{len(merged[merged['disposition']=='HOLD'])} items, ${merged[merged['disposition']=='HOLD']['on_hand_value'].sum():,.0f}",
        f"{len(merged[merged['disposition']=='EXPEDITE'])} items, ${merged[merged['disposition']=='EXPEDITE']['on_hand_value'].sum():,.0f}",
        f"{len(merged[merged['disposition']=='REVIEW'])} items, ${merged[merged['disposition']=='REVIEW']['on_hand_value'].sum():,.0f}",
        f"{len(merged[merged['disposition']=='STOP_REORDER'])} items, ${merged[merged['disposition']=='STOP_REORDER']['on_hand_value'].sum():,.0f}",
        f"{len(merged[merged['disposition']=='LIQUIDATE'])} items, ${merged[merged['disposition']=='LIQUIDATE']['on_hand_value'].sum():,.0f}",
        f"{len(merged[merged['disposition']=='RELOCATE'])} items, ${merged[merged['disposition']=='RELOCATE']['on_hand_value'].sum():,.0f}",
        f"{len(merged[merged['disposition']=='SCRAP'])} items, ${merged[merged['disposition']=='SCRAP']['on_hand_value'].sum():,.0f}",
        '',
        '',
        f"{len(stranded[stranded['current_country']=='CA'])} items, ${stranded[stranded['current_country']=='CA']['value'].sum():,.0f}",
        f"{len(stranded[stranded['current_country']=='US'])} items, ${stranded[stranded['current_country']=='US']['value'].sum():,.0f}",
        f"${stranded['value'].sum():,.0f}",
        '',
        '',
        f"{len(dead)} items",
        f"${dead['on_hand_value'].sum():,.0f}",
        '',
        '',
        '15% annual',
        '2.5 months',
        '3.5 months',
        '10%',
        'EVS < -25%',
    ],
    'Notes': [
        '',
        'FMP inventory/velocity extract date',
        '',
        '',
        'Unique SKU×DC combinations with inventory',
        '',
        'At landed cost',
        'Beyond 6-month target coverage',
        '',
        '',
        'Positive EVS, healthy velocity',
        'Below target stock, needs replenishment',
        'Borderline EVS, investigate',
        'Negative EVS, let run out',
        'Very slow, consider markdown',
        'Zero DC sales but network demand exists',
        'Zero network sales, no backlog',
        '',
        '',
        'Transfer to US requires customs/duties eval',
        'Domestic freight only',
        '',
        '',
        '',
        'Clear scrap candidates',
        '',
        '',
        '',
        'Aligned with Financial Summary methodology',
        '',
        '',
        '',
        'AND zero network sales AND no backlog',
    ]
}

summary_df = pd.DataFrame(summary_data)

# ============================================================================
# SHEET 2: METHODOLOGY
# ============================================================================

methodology = {
    'Component': [
        'EVS (Economic Value per Stocked Dollar)',
        '',
        'Newsvendor Target Stock',
        '',
        'ABC Classification',
        '',
        'Disposition Logic',
        '',
        '',
        '',
        '',
        '',
        '',
        'Stranded vs Dead Logic',
        '',
    ],
    'Formula / Rule': [
        'EVS = (GM% × Turns) - (Carrying Cost / Inv Value) - Cost of Capital',
        '',
        'Target = max(LT Demand, Backlog) + Safety Stock',
        'Safety Stock = z(CR) × σ(demand) × √LT',
        'A = Top 80% cumulative revenue',
        'B = Next 15%, C = Bottom 5%',
        'HOLD: EVS > 0% or strong backlog',
        'EXPEDITE: On-hand < 50% of target and has demand',
        'REVIEW: EVS 0% to -15%, needs investigation',
        'STOP_REORDER: EVS -15% to -25%, decelerating',
        'LIQUIDATE: EVS < -15%, very slow (<0.5 turns)',
        'RELOCATE: Zero DC sales but positive network sales',
        'SCRAP: EVS < -25% AND zero network sales AND no backlog',
        'STRANDED: L12M DC sales = 0 but L12M Network sales > 0',
        'DEAD: L12M Network sales = 0 AND backlog = 0',
    ],
    'Rationale': [
        'Measures economic return per dollar invested in inventory',
        '',
        'Service-level driven stocking with demand variability',
        'Critical ratio = Cu/(Cu+Co) where Cu=underage, Co=overage cost',
        'Focus resources on highest-revenue SKUs',
        '',
        'Generating positive economic return',
        'Risk of stockout on active SKU',
        'May recover with demand changes',
        'Minimize future investment',
        'Recover value through markdown',
        'Inventory is in wrong location, not truly dead',
        'No demand signal anywhere in network',
        'Evaluate transfer vs scrap based on costs',
        'Clear scrap candidates',
    ]
}

methodology_df = pd.DataFrame(methodology)

# ============================================================================
# SHEET 3: FULL DISPOSITION DETAIL
# ============================================================================

disposition_detail = merged[[
    'sku', 'dc', 'disposition', 'abc_class', 'trend', 'is_strategic',
    'on_hand_qty', 'on_water_qty', 'on_order_qty', 'backlog_units',
    'l3m_units', 'l12m_units', 'network_l12m_units',
    'turns', 'gm_pct', 'evs',
    'target_stock', 'excess_qty',
    'unit_cost_landed', 'on_hand_value', 'excess_value'
]].copy()

disposition_detail = disposition_detail.sort_values(['disposition', 'on_hand_value'], ascending=[True, False])

# Add rationale column
def get_rationale(row):
    disp = row['disposition']
    evs = row['evs'] if pd.notna(row['evs']) else -999

    if disp == 'HOLD':
        if evs > 0.10:
            return f"Strong EVS ({evs*100:.0f}%), generating positive return"
        elif row['backlog_units'] > 0:
            return f"Has backlog ({int(row['backlog_units'])} units committed)"
        else:
            return "Healthy inventory position"
    elif disp == 'EXPEDITE':
        return f"On-hand ({int(row['on_hand_qty'])}) below target ({int(row['target_stock'])})"
    elif disp == 'REVIEW':
        return f"Borderline EVS ({evs*100:.0f}%), needs investigation"
    elif disp == 'STOP_REORDER':
        return f"Negative EVS ({evs*100:.0f}%), {row['trend']} trend - let run out"
    elif disp == 'LIQUIDATE':
        return f"Very slow ({row['turns']:.2f} turns), EVS {evs*100:.0f}% - markdown"
    elif disp == 'RELOCATE':
        return f"Zero DC sales but {int(row['network_l12m_units'])} network L12M - evaluate transfer"
    elif disp == 'SCRAP':
        return "Zero network sales, zero backlog - scrap candidate"
    else:
        return ""

disposition_detail['rationale'] = disposition_detail.apply(get_rationale, axis=1)

# ============================================================================
# SHEET 4: STRANDED INVENTORY (for transfer eval)
# ============================================================================

stranded_detail = stranded.copy()
stranded_detail['cross_border'] = stranded_detail['current_country'].apply(
    lambda x: 'Yes - duties/customs apply' if x == 'CA' else 'No - domestic'
)

# Add rationale
def get_stranded_rationale(row):
    if row['dest_1_mos'] and row['dest_1_mos'] < 999:
        if row['dest_1_mos'] < 6:
            urgency = "Quick sell"
        elif row['dest_1_mos'] < 12:
            urgency = "Moderate"
        else:
            urgency = "Slow sell"
        return f"{urgency} at {row['dest_1_dc']} ({row['dest_1_mos']:.1f} mo). Network L12M: {int(row['network_l12m_units'])} units"
    else:
        return "Limited destination options"

stranded_detail['transfer_rationale'] = stranded_detail.apply(get_stranded_rationale, axis=1)

# ============================================================================
# SHEET 5: DEAD STOCK (clear scrap)
# ============================================================================

dead_detail = dead.copy()
dead_detail['scrap_rationale'] = 'Zero L12M sales network-wide, zero backlog - recommend scrap'
dead_detail['write_down_90pct'] = dead_detail['on_hand_value'] * 0.90
dead_detail['recovery_10pct'] = dead_detail['on_hand_value'] * 0.10

# ============================================================================
# SHEET 6: ABC SUMMARY
# ============================================================================

abc_summary = merged[merged['on_hand_qty'] > 0].groupby('abc_class').agg({
    'sku': 'nunique',
    'on_hand_qty': 'sum',
    'on_hand_value': 'sum',
    'l12m_units': 'sum',
    'excess_value': 'sum'
}).reset_index()
abc_summary.columns = ['ABC_Class', 'Unique_SKUs', 'On_Hand_Units', 'On_Hand_Value', 'L12M_Units', 'Excess_Value']
abc_summary['Lead_Time_Mo'] = abc_summary['ABC_Class'].map({'A': 2.5, 'B': 3.5, 'C': 3.5})

# ============================================================================
# SHEET 7: DISPOSITION PIVOT
# ============================================================================

disp_pivot = merged[merged['on_hand_qty'] > 0].groupby('disposition').agg({
    'sku': 'count',
    'on_hand_qty': 'sum',
    'on_hand_value': 'sum',
    'excess_value': 'sum',
    'l12m_units': 'sum'
}).reset_index()
disp_pivot.columns = ['Disposition', 'SKU_DC_Rows', 'On_Hand_Units', 'On_Hand_Value', 'Excess_Value', 'L12M_Units']
disp_pivot = disp_pivot.sort_values('On_Hand_Value', ascending=False)

# ============================================================================
# WRITE EXCEL
# ============================================================================

output_path = os.path.join(base_dir, 'analysis/DuraBrake_Inventory_Disposition.xlsx')

with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    summary_df.to_excel(writer, sheet_name='Executive Summary', index=False)
    methodology_df.to_excel(writer, sheet_name='Methodology', index=False)
    disposition_detail.to_excel(writer, sheet_name='Full Disposition', index=False)
    stranded_detail.to_excel(writer, sheet_name='Stranded - Transfer Eval', index=False)
    dead_detail.to_excel(writer, sheet_name='Dead Stock - Scrap', index=False)
    abc_summary.to_excel(writer, sheet_name='ABC Summary', index=False)
    disp_pivot.to_excel(writer, sheet_name='Disposition Pivot', index=False)

print(f"\nWorkbook saved to: {output_path}")
print(f"""
Sheets included:
  1. Executive Summary - Key metrics and assumptions
  2. Methodology - Formulas and decision logic
  3. Full Disposition - All {len(disposition_detail)} SKU×DC rows with rationale
  4. Stranded - Transfer Eval - {len(stranded_detail)} items for transfer discussion
  5. Dead Stock - Scrap - {len(dead_detail)} items with zero network sales
  6. ABC Summary - Classification breakdown
  7. Disposition Pivot - Summary by action
""")
