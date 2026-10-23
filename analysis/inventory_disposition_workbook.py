#!/usr/bin/env python3
"""
DuraBrake Inventory Disposition Workbook
Generates formatted Excel output with full analysis, stats, and rationale
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, NamedStyle
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.utils import get_column_letter

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("Generating formatted Excel workbook...")

# ============================================================================
# STYLE DEFINITIONS
# ============================================================================

# Colors
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
SECTION_FILL = PatternFill(start_color="D6DCE4", end_color="D6DCE4", fill_type="solid")
SECTION_FONT = Font(bold=True, size=11)
NORMAL_FONT = Font(size=10)
CURRENCY_FONT = Font(size=10)

# Borders
THIN_BORDER = Border(
    left=Side(style='thin', color='B4B4B4'),
    right=Side(style='thin', color='B4B4B4'),
    top=Side(style='thin', color='B4B4B4'),
    bottom=Side(style='thin', color='B4B4B4')
)

# Alignments
LEFT_ALIGN = Alignment(horizontal='left', vertical='center')
RIGHT_ALIGN = Alignment(horizontal='right', vertical='center')
CENTER_ALIGN = Alignment(horizontal='center', vertical='center')
WRAP_ALIGN = Alignment(horizontal='left', vertical='center', wrap_text=True)

def format_header_row(ws, row_num=1):
    """Apply header formatting to a row"""
    for cell in ws[row_num]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

def auto_column_width(ws, min_width=8, max_width=50):
    """Auto-size columns based on content"""
    for column_cells in ws.columns:
        length = max(len(str(cell.value or "")) for cell in column_cells)
        length = min(max(length + 2, min_width), max_width)
        ws.column_dimensions[get_column_letter(column_cells[0].column)].width = length

def apply_number_format(ws, col_letter, format_str, start_row=2):
    """Apply number format to a column"""
    for row in range(start_row, ws.max_row + 1):
        cell = ws[f"{col_letter}{row}"]
        cell.number_format = format_str
        cell.alignment = RIGHT_ALIGN

def set_column_width(ws, col_letter, width):
    """Set specific column width"""
    ws.column_dimensions[col_letter].width = width

# ============================================================================
# LOAD DATA
# ============================================================================

merged = pd.read_csv(os.path.join(base_dir, 'analysis/merged_disposition_full.csv'))
stranded = pd.read_csv(os.path.join(base_dir, 'analysis/stranded_inventory_review.csv'))
dead = pd.read_csv(os.path.join(base_dir, 'analysis/dead_stock_final.csv'))

# ============================================================================
# CREATE WORKBOOK
# ============================================================================

wb = Workbook()

# ============================================================================
# SHEET 1: HOW TO USE (Plain English Explainer)
# ============================================================================

ws = wb.active
ws.title = "How to Use"

ws['A1'] = "DuraBrake Inventory Analysis - Quick Guide"
ws['A1'].font = Font(bold=True, size=16, color="1F4E79")
ws.merge_cells('A1:D1')

row = 3
ws[f'A{row}'] = "WHAT THIS WORKBOOK TELLS YOU"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = SECTION_FILL
ws.merge_cells(f'A{row}:D{row}')

explainer_text = [
    ("The Problem:", "We have money tied up in inventory that isn't selling, or is sitting in the wrong warehouse."),
    ("", "This analysis identifies which parts need attention and recommends what to do with them."),
    ("", ""),
    ("How We Figured This Out:", "We looked at every part at every warehouse and asked:"),
    ("", "  • Is it selling? (Last 12 months of sales data)"),
    ("", "  • Is it profitable when it does sell? (Gross margin)"),
    ("", "  • How fast does it turn over? (Inventory turns)"),
    ("", "  • Do we have customer orders waiting? (Backlog)"),
    ("", ""),
    ("The Key Metric - EVS:", "EVS stands for 'Economic Value per Stocked Dollar'"),
    ("", "It answers: 'For every dollar we have tied up in this part, are we making or losing money?'"),
    ("", "  • Positive EVS = Making money (good)"),
    ("", "  • Negative EVS = Losing money (bad - the cost of holding it exceeds the profit)"),
    ("", "  • Below -25% EVS with no sales = Candidate for scrap"),
]

for label, text in explainer_text:
    row += 1
    ws[f'A{row}'] = label
    ws[f'A{row}'].font = Font(bold=True) if label else NORMAL_FONT
    ws[f'B{row}'] = text
    ws[f'B{row}'].alignment = WRAP_ALIGN
    ws.merge_cells(f'B{row}:D{row}')

row += 2
ws[f'A{row}'] = "WHAT EACH TAB SHOWS"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = SECTION_FILL
ws.merge_cells(f'A{row}:D{row}')

tab_descriptions = [
    ("Action Items", "START HERE - Parts that need decisions, sorted by priority. This is your to-do list."),
    ("Executive Summary", "High-level numbers: total inventory, how much is excess, breakdown by category."),
    ("Methodology", "Technical details for those who want to understand the formulas."),
    ("Full Disposition", "Complete list of all 317 SKU×DC combinations with all the data. You can filter/sort."),
    ("Stranded - Transfer Eval", "Parts with zero sales at their current warehouse but sales elsewhere in the network. Consider moving these instead of scrapping."),
    ("Dead Stock - Scrap", "Parts with zero sales everywhere. These are scrap candidates."),
]

row += 1
ws[f'A{row}'] = "Tab Name"
ws[f'B{row}'] = "What It Contains"
ws[f'A{row}'].font = Font(bold=True)
ws[f'B{row}'].font = Font(bold=True)
for col in ['A', 'B']:
    ws[f'{col}{row}'].fill = HEADER_FILL
    ws[f'{col}{row}'].font = HEADER_FONT
    ws[f'{col}{row}'].border = THIN_BORDER

for tab, desc in tab_descriptions:
    row += 1
    ws[f'A{row}'] = tab
    ws[f'A{row}'].font = Font(bold=True)
    ws[f'B{row}'] = desc
    ws.merge_cells(f'B{row}:D{row}')
    for col in ['A', 'B']:
        ws[f'{col}{row}'].border = THIN_BORDER

row += 2
ws[f'A{row}'] = "WHAT THE DISPOSITIONS MEAN"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = SECTION_FILL
ws.merge_cells(f'A{row}:D{row}')

disposition_explanations = [
    ("HOLD", "Keep stocking as-is. Part is profitable and turning."),
    ("EXPEDITE", "Order more now. Stock is low relative to demand."),
    ("REVIEW", "Borderline - investigate. Might need pricing adjustment or demand is unclear."),
    ("STOP_REORDER", "Don't reorder when it runs out. Let existing stock sell through."),
    ("LIQUIDATE", "Mark down and sell. Too slow to justify holding at current price."),
    ("RELOCATE", "Consider transferring to another warehouse where it's selling."),
    ("SCRAP", "Write off. No demand anywhere in the network."),
]

row += 1
ws[f'A{row}'] = "Disposition"
ws[f'B{row}'] = "What It Means"
for col in ['A', 'B']:
    ws[f'{col}{row}'].fill = HEADER_FILL
    ws[f'{col}{row}'].font = HEADER_FONT
    ws[f'{col}{row}'].border = THIN_BORDER

for disp, meaning in disposition_explanations:
    row += 1
    ws[f'A{row}'] = disp
    ws[f'A{row}'].font = Font(bold=True)
    ws[f'B{row}'] = meaning
    ws.merge_cells(f'B{row}:D{row}')
    for col in ['A', 'B']:
        ws[f'{col}{row}'].border = THIN_BORDER

row += 2
ws[f'A{row}'] = "DATA QUALITY NOTE"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
ws.merge_cells(f'A{row}:D{row}')

row += 1
ws[f'A{row}'] = "⚠ Some items show $0 unit cost in FathoMaker. These are flagged as 'COST TBD' in the Action Items tab."
ws.merge_cells(f'A{row}:D{row}')
row += 1
ws[f'A{row}'] = "Before scrapping, verify cost basis in QuickBooks to calculate accurate write-down amounts."
ws.merge_cells(f'A{row}:D{row}')

set_column_width(ws, 'A', 20)
set_column_width(ws, 'B', 80)
set_column_width(ws, 'C', 15)
set_column_width(ws, 'D', 15)

# ============================================================================
# SHEET 2: ACTION ITEMS (Sorted by Priority)
# ============================================================================

ws = wb.create_sheet("Action Items")

ws['A1'] = "Action Items - Parts Requiring Decisions"
ws['A1'].font = Font(bold=True, size=14, color="1F4E79")
ws.merge_cells('A1:F1')

ws['A2'] = "Sorted by action priority. SCRAP and RELOCATE items need immediate attention."
ws['A2'].font = Font(italic=True, size=10, color="666666")
ws.merge_cells('A2:F2')

# Build action items from merged data - only items needing action
action_items = merged[merged['disposition'].isin(['SCRAP', 'RELOCATE', 'LIQUIDATE', 'STOP_REORDER', 'EXPEDITE'])].copy()

# Priority order
priority_map = {'SCRAP': 1, 'RELOCATE': 2, 'LIQUIDATE': 3, 'EXPEDITE': 4, 'STOP_REORDER': 5}
action_items['priority'] = action_items['disposition'].map(priority_map)
action_items = action_items.sort_values(['priority', 'on_hand_value'], ascending=[True, False])

# Add cost flag
action_items['cost_flag'] = action_items['unit_cost_landed'].apply(lambda x: 'COST TBD' if x == 0 else '')

# Add suggested action text
def get_action_text(row):
    disp = row['disposition']
    if disp == 'SCRAP':
        return 'Write off - zero demand network-wide'
    elif disp == 'RELOCATE':
        if row['network_l12m_units'] > 0:
            return f'Evaluate transfer - {int(row["network_l12m_units"])} units sold elsewhere'
        return 'Evaluate transfer options'
    elif disp == 'LIQUIDATE':
        return f'Markdown to move - {row["turns"]:.1f}x turns, EVS {row["evs"]*100:.0f}%'
    elif disp == 'EXPEDITE':
        return f'Reorder - below target ({int(row["on_hand_qty"])}/{int(row["target_stock"])})'
    elif disp == 'STOP_REORDER':
        return 'Let run out - do not reorder'
    return ''

action_items['suggested_action'] = action_items.apply(get_action_text, axis=1)

# Select columns for output
action_output = action_items[[
    'disposition', 'sku', 'dc', 'on_hand_qty', 'on_hand_value',
    'unit_cost_landed', 'cost_flag', 'l12m_units', 'network_l12m_units',
    'evs', 'suggested_action'
]].copy()

action_output.columns = [
    'Action', 'SKU', 'DC', 'Units', 'Value',
    'Unit Cost', 'Cost Flag', 'DC L12M', 'Network L12M',
    'EVS', 'Suggested Action'
]

# Write header row (row 4)
header_row = 4
for col_num, col_name in enumerate(action_output.columns, 1):
    cell = ws.cell(row=header_row, column=col_num, value=col_name)
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    cell.alignment = CENTER_ALIGN
    cell.border = THIN_BORDER

# Write data
for row_num, row_data in enumerate(action_output.values, header_row + 1):
    for col_num, value in enumerate(row_data, 1):
        cell = ws.cell(row=row_num, column=col_num, value=value)
        cell.border = THIN_BORDER
        cell.font = NORMAL_FONT
        # Highlight cost flag
        if col_num == 7 and value == 'COST TBD':
            cell.fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
            cell.font = Font(bold=True, size=10)

# Apply number formats
action_formats = {
    'D': '#,##0',      # Units
    'E': '$#,##0',     # Value
    'F': '$#,##0.00',  # Unit Cost
    'H': '#,##0',      # DC L12M
    'I': '#,##0',      # Network L12M
    'J': '0.0%',       # EVS
}
for col, fmt in action_formats.items():
    apply_number_format(ws, col, fmt, start_row=header_row+1)

# Column widths
action_widths = {'A': 14, 'B': 12, 'C': 18, 'D': 8, 'E': 12, 'F': 11, 'G': 10,
                 'H': 10, 'I': 12, 'J': 7, 'K': 45}
for col, width in action_widths.items():
    set_column_width(ws, col, width)

ws.freeze_panes = 'A5'

# Add summary at top
ws['A3'] = f"Total action items: {len(action_output)} | SCRAP: {len(action_output[action_output['Action']=='SCRAP'])} | RELOCATE: {len(action_output[action_output['Action']=='RELOCATE'])} | LIQUIDATE: {len(action_output[action_output['Action']=='LIQUIDATE'])} | EXPEDITE: {len(action_output[action_output['Action']=='EXPEDITE'])} | STOP_REORDER: {len(action_output[action_output['Action']=='STOP_REORDER'])}"
ws['A3'].font = Font(bold=True, size=10)
ws.merge_cells('A3:K3')

# ============================================================================
# SHEET 3: EXECUTIVE SUMMARY
# ============================================================================

ws = wb.create_sheet("Executive Summary")

# Title
ws['A1'] = "DuraBrake Inventory Disposition Analysis"
ws['A1'].font = Font(bold=True, size=16, color="1F4E79")
ws.merge_cells('A1:C1')

ws['A2'] = f"Generated: {datetime.now().strftime('%Y-%m-%d')}"
ws['A2'].font = Font(italic=True, size=10, color="666666")

# Section: Overview
row = 4
ws[f'A{row}'] = "INVENTORY POSITION"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = SECTION_FILL
ws.merge_cells(f'A{row}:C{row}')

metrics = [
    ('Total SKU×DC Rows', len(merged), ''),
    ('Total On-Hand Units', int(merged['on_hand_qty'].sum()), '#,##0'),
    ('Total On-Hand Value', merged['on_hand_value'].sum(), '$#,##0'),
    ('Total Excess Value', merged['excess_value'].sum(), '$#,##0'),
]

for label, value, fmt in metrics:
    row += 1
    ws[f'A{row}'] = label
    ws[f'B{row}'] = value
    if fmt:
        ws[f'B{row}'].number_format = fmt
    ws[f'B{row}'].alignment = RIGHT_ALIGN

# Section: Disposition Breakdown
row += 2
ws[f'A{row}'] = "DISPOSITION BREAKDOWN"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = SECTION_FILL
ws.merge_cells(f'A{row}:C{row}')

row += 1
ws[f'A{row}'] = "Disposition"
ws[f'B{row}'] = "Items"
ws[f'C{row}'] = "Value"
for col in ['A', 'B', 'C']:
    ws[f'{col}{row}'].font = Font(bold=True)
    ws[f'{col}{row}'].border = THIN_BORDER

dispositions = ['HOLD', 'EXPEDITE', 'REVIEW', 'STOP_REORDER', 'LIQUIDATE', 'RELOCATE', 'SCRAP']
for disp in dispositions:
    row += 1
    subset = merged[merged['disposition'] == disp]
    ws[f'A{row}'] = disp
    ws[f'B{row}'] = len(subset)
    ws[f'B{row}'].number_format = '#,##0'
    ws[f'C{row}'] = subset['on_hand_value'].sum()
    ws[f'C{row}'].number_format = '$#,##0'
    for col in ['A', 'B', 'C']:
        ws[f'{col}{row}'].border = THIN_BORDER

# Section: Stranded Detail
row += 2
ws[f'A{row}'] = "STRANDED INVENTORY"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = SECTION_FILL
ws.merge_cells(f'A{row}:C{row}')

canada_stranded = stranded[stranded['current_country'] == 'CA']
us_stranded = stranded[stranded['current_country'] == 'US']

stranded_metrics = [
    ('Stranded in Canada', len(canada_stranded), canada_stranded['value'].sum(), 'Cross-border eval required'),
    ('Stranded in US', len(us_stranded), us_stranded['value'].sum(), 'Domestic freight only'),
    ('Total Stranded', len(stranded), stranded['value'].sum(), ''),
]

row += 1
ws[f'A{row}'] = "Location"
ws[f'B{row}'] = "Items"
ws[f'C{row}'] = "Value"
ws[f'D{row}'] = "Notes"
for col in ['A', 'B', 'C', 'D']:
    ws[f'{col}{row}'].font = Font(bold=True)

for label, count, value, note in stranded_metrics:
    row += 1
    ws[f'A{row}'] = label
    ws[f'B{row}'] = count
    ws[f'C{row}'] = value
    ws[f'C{row}'].number_format = '$#,##0'
    ws[f'D{row}'] = note

# Section: Assumptions
row += 2
ws[f'A{row}'] = "KEY ASSUMPTIONS"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = SECTION_FILL
ws.merge_cells(f'A{row}:C{row}')

assumptions = [
    ('Cost of Capital', '15%', 'Annual, aligned with Financial Summary'),
    ('Lead Time (A-class)', '2.5 mo', 'Top 80% revenue SKUs'),
    ('Lead Time (BC-class)', '3.5 mo', 'Remaining SKUs'),
    ('Scrap Recovery', '10%', 'Of landed cost'),
    ('EVS Scrap Threshold', '<-25%', 'AND zero network sales AND no backlog'),
]

for param, value, note in assumptions:
    row += 1
    ws[f'A{row}'] = param
    ws[f'B{row}'] = value
    ws[f'C{row}'] = note

# Format
set_column_width(ws, 'A', 25)
set_column_width(ws, 'B', 15)
set_column_width(ws, 'C', 15)
set_column_width(ws, 'D', 30)

# ============================================================================
# SHEET 4: METHODOLOGY
# ============================================================================

ws = wb.create_sheet("Methodology")

ws['A1'] = "Methodology & Decision Logic"
ws['A1'].font = Font(bold=True, size=14, color="1F4E79")
ws.merge_cells('A1:C1')

# EVS Section
row = 3
ws[f'A{row}'] = "EVS (Economic Value per Stocked Dollar)"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = SECTION_FILL
ws.merge_cells(f'A{row}:C{row}')

row += 1
ws[f'A{row}'] = "Formula:"
ws[f'B{row}'] = "EVS = (GM% × Turns) - (Annual Carry Cost / Inv Value) - Cost of Capital"
ws.merge_cells(f'B{row}:C{row}')

row += 1
ws[f'A{row}'] = "Interpretation:"
ws[f'B{row}'] = "Positive EVS = generating return above cost of capital. Negative = destroying value."
ws.merge_cells(f'B{row}:C{row}')

# Newsvendor Section
row += 2
ws[f'A{row}'] = "Newsvendor Target Stock"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = SECTION_FILL
ws.merge_cells(f'A{row}:C{row}')

row += 1
ws[f'A{row}'] = "Formula:"
ws[f'B{row}'] = "Target = max(Lead Time Demand, Committed Backlog) + Safety Stock"
ws.merge_cells(f'B{row}:C{row}')

row += 1
ws[f'A{row}'] = "Safety Stock:"
ws[f'B{row}'] = "z(CR) × σ(monthly demand) × √(Lead Time)"
ws.merge_cells(f'B{row}:C{row}')

row += 1
ws[f'A{row}'] = "Critical Ratio:"
ws[f'B{row}'] = "CR = Cu / (Cu + Co), where Cu = underage cost (lost GP), Co = overage cost"
ws.merge_cells(f'B{row}:C{row}')

# Disposition Rules
row += 2
ws[f'A{row}'] = "Disposition Decision Rules"
ws[f'A{row}'].font = SECTION_FONT
ws[f'A{row}'].fill = SECTION_FILL
ws.merge_cells(f'A{row}:C{row}')

rules = [
    ('HOLD', 'EVS > 0% or strong backlog', 'Maintain current stocking'),
    ('EXPEDITE', 'On-hand < 50% of target, has demand', 'Replenish immediately'),
    ('REVIEW', 'EVS -15% to 0%, borderline', 'Investigate demand patterns'),
    ('STOP_REORDER', 'EVS -25% to -15%, decelerating', 'Let inventory run out'),
    ('LIQUIDATE', 'EVS < -15%, turns < 0.5', 'Markdown to move'),
    ('RELOCATE', 'Zero DC sales, positive network sales', 'Evaluate transfer economics'),
    ('SCRAP', 'EVS < -25%, zero network sales, no backlog', 'Write off inventory'),
]

row += 1
ws[f'A{row}'] = "Disposition"
ws[f'B{row}'] = "Trigger Condition"
ws[f'C{row}'] = "Action"
for col in ['A', 'B', 'C']:
    ws[f'{col}{row}'].font = Font(bold=True)
    ws[f'{col}{row}'].fill = HEADER_FILL
    ws[f'{col}{row}'].font = HEADER_FONT

for disp, condition, action in rules:
    row += 1
    ws[f'A{row}'] = disp
    ws[f'B{row}'] = condition
    ws[f'C{row}'] = action
    for col in ['A', 'B', 'C']:
        ws[f'{col}{row}'].border = THIN_BORDER

set_column_width(ws, 'A', 20)
set_column_width(ws, 'B', 45)
set_column_width(ws, 'C', 35)

# ============================================================================
# SHEET 5: FULL DISPOSITION DETAIL
# ============================================================================

ws = wb.create_sheet("Full Disposition")

# Prepare data
disposition_detail = merged[[
    'sku', 'dc', 'disposition', 'abc_class', 'trend',
    'on_hand_qty', 'backlog_units', 'l12m_units', 'network_l12m_units',
    'turns', 'gm_pct', 'evs',
    'target_stock', 'excess_qty',
    'unit_cost_landed', 'on_hand_value', 'excess_value'
]].copy()

# Add rationale
def get_rationale(row):
    disp = row['disposition']
    evs = row['evs'] if pd.notna(row['evs']) else -999

    if disp == 'HOLD':
        if evs > 0.10:
            return f"Strong EVS ({evs*100:.0f}%), positive return"
        elif row['backlog_units'] > 0:
            return f"Backlog: {int(row['backlog_units'])} units"
        else:
            return "Healthy position"
    elif disp == 'EXPEDITE':
        return f"Below target ({int(row['on_hand_qty'])}/{int(row['target_stock'])})"
    elif disp == 'REVIEW':
        return f"Borderline EVS ({evs*100:.0f}%)"
    elif disp == 'STOP_REORDER':
        return f"EVS {evs*100:.0f}%, {row['trend']}"
    elif disp == 'LIQUIDATE':
        return f"Slow ({row['turns']:.1f}x), EVS {evs*100:.0f}%"
    elif disp == 'RELOCATE':
        return f"Network demand: {int(row['network_l12m_units'])} L12M"
    elif disp == 'SCRAP':
        return "Zero network sales"
    return ""

disposition_detail['rationale'] = disposition_detail.apply(get_rationale, axis=1)
disposition_detail = disposition_detail.sort_values(['disposition', 'on_hand_value'], ascending=[True, False])

# Rename columns for clarity
disposition_detail.columns = [
    'SKU', 'DC', 'Disposition', 'ABC', 'Trend',
    'On Hand', 'Backlog', 'DC L12M', 'Network L12M',
    'Turns', 'GM%', 'EVS',
    'Target', 'Excess Qty',
    'Unit Cost', 'OH Value', 'Excess Value', 'Rationale'
]

# Write header
for col_num, col_name in enumerate(disposition_detail.columns, 1):
    cell = ws.cell(row=1, column=col_num, value=col_name)
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    cell.alignment = CENTER_ALIGN
    cell.border = THIN_BORDER

# Write data
for row_num, row_data in enumerate(disposition_detail.values, 2):
    for col_num, value in enumerate(row_data, 1):
        cell = ws.cell(row=row_num, column=col_num, value=value)
        cell.border = THIN_BORDER
        cell.font = NORMAL_FONT

# Apply number formats
col_formats = {
    'F': '#,##0',      # On Hand
    'G': '#,##0',      # Backlog
    'H': '#,##0',      # DC L12M
    'I': '#,##0',      # Network L12M
    'J': '0.00',       # Turns
    'K': '0.0%',       # GM%
    'L': '0.0%',       # EVS
    'M': '#,##0',      # Target
    'N': '#,##0',      # Excess Qty
    'O': '$#,##0.00',  # Unit Cost
    'P': '$#,##0',     # OH Value
    'Q': '$#,##0',     # Excess Value
}

for col, fmt in col_formats.items():
    apply_number_format(ws, col, fmt)

# Column widths
widths = {'A': 12, 'B': 18, 'C': 12, 'D': 5, 'E': 12, 'F': 10, 'G': 9, 'H': 10,
          'I': 12, 'J': 7, 'K': 7, 'L': 7, 'M': 9, 'N': 10, 'O': 11, 'P': 12, 'Q': 12, 'R': 30}
for col, width in widths.items():
    set_column_width(ws, col, width)

# Freeze header row and first two columns
ws.freeze_panes = 'C2'

# ============================================================================
# SHEET 6: STRANDED INVENTORY
# ============================================================================

ws = wb.create_sheet("Stranded - Transfer Eval")

stranded_detail = stranded.copy()

# Add cross-border flag
stranded_detail['Cross Border'] = stranded_detail['current_country'].apply(
    lambda x: 'Yes' if x == 'CA' else 'No'
)

# Add rationale
def get_transfer_rationale(row):
    if row['dest_1_mos'] and row['dest_1_mos'] < 999:
        mos = row['dest_1_mos']
        if mos < 6:
            return f"Quick: {mos:.1f} mo at {row['dest_1_dc']}"
        elif mos < 12:
            return f"Moderate: {mos:.1f} mo at {row['dest_1_dc']}"
        else:
            return f"Slow: {mos:.1f} mo at {row['dest_1_dc']}"
    return "Limited options"

stranded_detail['Transfer Notes'] = stranded_detail.apply(get_transfer_rationale, axis=1)

# Select and rename columns
stranded_output = stranded_detail[[
    'sku', 'current_dc', 'Cross Border', 'units', 'value', 'unit_cost',
    'network_l12m_units', 'dest_1_dc', 'dest_1_l12m', 'dest_1_mos',
    'dest_2_dc', 'dest_2_l12m', 'Transfer Notes'
]].copy()

stranded_output.columns = [
    'SKU', 'Current DC', 'Cross Border', 'Units', 'Value', 'Unit Cost',
    'Network L12M', 'Best Dest', 'Dest L12M', 'Mo to Sell',
    'Alt Dest', 'Alt L12M', 'Notes'
]

stranded_output = stranded_output.sort_values('Value', ascending=False)

# Write header
for col_num, col_name in enumerate(stranded_output.columns, 1):
    cell = ws.cell(row=1, column=col_num, value=col_name)
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    cell.alignment = CENTER_ALIGN
    cell.border = THIN_BORDER

# Write data
for row_num, row_data in enumerate(stranded_output.values, 2):
    for col_num, value in enumerate(row_data, 1):
        cell = ws.cell(row=row_num, column=col_num, value=value)
        cell.border = THIN_BORDER
        cell.font = NORMAL_FONT

# Number formats
stranded_formats = {
    'D': '#,##0',      # Units
    'E': '$#,##0',     # Value
    'F': '$#,##0.00',  # Unit Cost
    'G': '#,##0',      # Network L12M
    'I': '#,##0',      # Dest L12M
    'J': '0.0',        # Mo to Sell
    'L': '#,##0',      # Alt L12M
}
for col, fmt in stranded_formats.items():
    apply_number_format(ws, col, fmt)

# Column widths
stranded_widths = {'A': 12, 'B': 18, 'C': 12, 'D': 8, 'E': 12, 'F': 11, 'G': 12,
                   'H': 18, 'I': 10, 'J': 10, 'K': 18, 'L': 10, 'M': 30}
for col, width in stranded_widths.items():
    set_column_width(ws, col, width)

ws.freeze_panes = 'B2'

# ============================================================================
# SHEET 7: DEAD STOCK
# ============================================================================

ws = wb.create_sheet("Dead Stock - Scrap")

dead_detail = dead.copy()
dead_detail['Write Down (90%)'] = dead_detail['on_hand_value'] * 0.90
dead_detail['Recovery (10%)'] = dead_detail['on_hand_value'] * 0.10

# Flag items with zero cost
dead_detail['Cost Flag'] = dead_detail['unit_cost_landed'].apply(
    lambda x: 'COST TBD - Verify in QBO' if x == 0 else ''
)
dead_detail['Rationale'] = 'Zero L12M network sales, zero backlog'

dead_output = dead_detail[[
    'sku', 'dc', 'on_hand_qty', 'unit_cost_landed', 'Cost Flag', 'on_hand_value',
    'Write Down (90%)', 'Recovery (10%)', 'Rationale'
]].copy()

dead_output.columns = [
    'SKU', 'DC', 'Units', 'Unit Cost', 'Cost Flag', 'Value',
    'Write Down', 'Recovery', 'Rationale'
]

# Sort: items with cost first (actionable), then zero-cost items
dead_output['has_cost'] = dead_output['Unit Cost'] > 0
dead_output = dead_output.sort_values(['has_cost', 'Value'], ascending=[False, False])
dead_output = dead_output.drop('has_cost', axis=1)

# Write header
for col_num, col_name in enumerate(dead_output.columns, 1):
    cell = ws.cell(row=1, column=col_num, value=col_name)
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    cell.alignment = CENTER_ALIGN
    cell.border = THIN_BORDER

# Write data
for row_num, row_data in enumerate(dead_output.values, 2):
    for col_num, value in enumerate(row_data, 1):
        cell = ws.cell(row=row_num, column=col_num, value=value)
        cell.border = THIN_BORDER
        cell.font = NORMAL_FONT
        # Highlight cost flag column
        if col_num == 5 and value and 'TBD' in str(value):
            cell.fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
            cell.font = Font(bold=True, size=10)

# Number formats (columns shifted due to Cost Flag)
dead_formats = {
    'C': '#,##0',      # Units
    'D': '$#,##0.00',  # Unit Cost
    'F': '$#,##0',     # Value
    'G': '$#,##0',     # Write Down
    'H': '$#,##0',     # Recovery
}
for col, fmt in dead_formats.items():
    apply_number_format(ws, col, fmt)

# Column widths (updated for new column)
dead_widths = {'A': 12, 'B': 18, 'C': 8, 'D': 11, 'E': 22, 'F': 12, 'G': 12, 'H': 10, 'I': 35}
for col, width in dead_widths.items():
    set_column_width(ws, col, width)

# Count items needing cost verification
zero_cost_count = len(dead_output[dead_output['Cost Flag'].str.contains('TBD', na=False)])
has_cost_count = len(dead_output) - zero_cost_count

# Add totals row
total_row = len(dead_output) + 2
ws[f'A{total_row}'] = 'TOTAL'
ws[f'A{total_row}'].font = Font(bold=True)
ws[f'C{total_row}'] = dead_output['Units'].sum()
ws[f'C{total_row}'].number_format = '#,##0'
ws[f'F{total_row}'] = dead_output['Value'].sum()
ws[f'F{total_row}'].number_format = '$#,##0'
ws[f'G{total_row}'] = dead_output['Write Down'].sum()
ws[f'G{total_row}'].number_format = '$#,##0'
ws[f'H{total_row}'] = dead_output['Recovery'].sum()
ws[f'H{total_row}'].number_format = '$#,##0'

for col in ['A', 'C', 'F', 'G', 'H']:
    ws[f'{col}{total_row}'].font = Font(bold=True)
    ws[f'{col}{total_row}'].fill = SECTION_FILL

# Add note about cost verification
note_row = total_row + 2
ws[f'A{note_row}'] = f"⚠ {zero_cost_count} items have $0 cost in source data - verify in QuickBooks before finalizing write-down"
ws[f'A{note_row}'].font = Font(bold=True, color="C00000")
ws.merge_cells(f'A{note_row}:I{note_row}')

ws.freeze_panes = 'B2'

# ============================================================================
# SHEET 8: DISPOSITION PIVOT
# ============================================================================

ws = wb.create_sheet("Disposition Summary")

disp_pivot = merged[merged['on_hand_qty'] > 0].groupby('disposition').agg({
    'sku': 'count',
    'on_hand_qty': 'sum',
    'on_hand_value': 'sum',
    'excess_value': 'sum',
    'l12m_units': 'sum'
}).reset_index()

disp_pivot.columns = ['Disposition', 'SKU×DC Rows', 'On Hand Units', 'On Hand Value', 'Excess Value', 'L12M Units']
disp_pivot = disp_pivot.sort_values('On Hand Value', ascending=False)

# Add totals
totals = pd.DataFrame([{
    'Disposition': 'TOTAL',
    'SKU×DC Rows': disp_pivot['SKU×DC Rows'].sum(),
    'On Hand Units': disp_pivot['On Hand Units'].sum(),
    'On Hand Value': disp_pivot['On Hand Value'].sum(),
    'Excess Value': disp_pivot['Excess Value'].sum(),
    'L12M Units': disp_pivot['L12M Units'].sum()
}])
disp_pivot = pd.concat([disp_pivot, totals], ignore_index=True)

# Write header
for col_num, col_name in enumerate(disp_pivot.columns, 1):
    cell = ws.cell(row=1, column=col_num, value=col_name)
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    cell.alignment = CENTER_ALIGN
    cell.border = THIN_BORDER

# Write data
for row_num, row_data in enumerate(disp_pivot.values, 2):
    for col_num, value in enumerate(row_data, 1):
        cell = ws.cell(row=row_num, column=col_num, value=value)
        cell.border = THIN_BORDER
        cell.font = NORMAL_FONT
        if row_data[0] == 'TOTAL':
            cell.font = Font(bold=True)
            cell.fill = SECTION_FILL

# Number formats
pivot_formats = {
    'B': '#,##0',      # Rows
    'C': '#,##0',      # Units
    'D': '$#,##0',     # Value
    'E': '$#,##0',     # Excess
    'F': '#,##0',      # L12M
}
for col, fmt in pivot_formats.items():
    apply_number_format(ws, col, fmt)

# Column widths
pivot_widths = {'A': 15, 'B': 14, 'C': 14, 'D': 15, 'E': 14, 'F': 12}
for col, width in pivot_widths.items():
    set_column_width(ws, col, width)

# ============================================================================
# SAVE WORKBOOK
# ============================================================================

output_path = os.path.join(base_dir, 'analysis/DuraBrake_Inventory_Disposition.xlsx')
wb.save(output_path)

print(f"\nFormatted workbook saved to: {output_path}")
print(f"""
Sheets included:
  1. How to Use - Plain English guide to the workbook
  2. Action Items - {len(action_output)} items needing decisions, sorted by priority
  3. Executive Summary - Key metrics with section headers
  4. Methodology - Decision logic and formulas
  5. Full Disposition - {len(disposition_detail)} rows, frozen panes at C2
  6. Stranded - Transfer Eval - {len(stranded_output)} items, frozen at B2
  7. Dead Stock - Scrap - {len(dead_output)} items ({zero_cost_count} with cost TBD)
  8. Disposition Summary - Pivot with totals

Features:
  • Plain English explainer for non-technical users
  • Action Items tab sorted by priority (SCRAP → RELOCATE → LIQUIDATE → etc.)
  • Zero-cost items flagged as "COST TBD - Verify in QBO"
  • Header rows: Dark blue fill, white bold text
  • Number formats: Comma separators, $ for currency, % for rates
  • Frozen panes: Headers + key columns stay visible
""")
