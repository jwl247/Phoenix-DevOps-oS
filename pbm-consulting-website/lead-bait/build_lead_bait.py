"""Lead bait: every open federal construction + steel bid Set-Aside Radar holds, set-aside and
no-certification alike. Rows exported from pbm_radar_db (public SAM.gov notices) on PULLED into the
two .tsv files beside this script; rebuild with:  python3 build_lead_bait.py"""
import csv
from datetime import date
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

PULLED = "2026-10-03"
TYPE = {"o": "Solicitation", "k": "Combined synopsis/solicitation", "p": "Presolicitation", "r": "Sources sought"}
WHO = {"NONE": "Any business (no set-aside)", "SBA": "Small business", "SDVOSBC": "Service-disabled veteran-owned small business",
       "SDVOSBS": "Service-disabled veteran-owned (sole source)", "8A": "8(a) program firms", "EDWOSB": "Econ. disadvantaged women-owned",
       "ISBEE": "Indian small business economic enterprise"}
N6 = {"236118": "Residential remodeling", "236220": "Commercial & institutional building", "237110": "Water & sewer lines",
      "237120": "Oil & gas pipelines", "237130": "Power & communication lines", "237310": "Highway, street & bridge",
      "237990": "Other heavy & civil", "238110": "Concrete foundation & structure", "238150": "Glass & glazing", "238160": "Roofing",
      "238190": "Other foundation, structure & exterior", "238210": "Electrical", "238220": "Plumbing, heating & A/C",
      "238290": "Other building equipment (elevators, doors)", "238320": "Painting", "238330": "Flooring", "238910": "Site preparation",
      "238990": "All other specialty trades", "332311": "Prefab metal buildings & components", "332312": "Fabricated structural metal",
      "332321": "Metal windows & doors", "332322": "Sheet metal work", "332323": "Ornamental & architectural metal"}
GROUPS = [("2361", "Residential building"), ("2362", "Commercial & institutional building"), ("2371", "Utility systems"),
          ("2373", "Highway, street & bridge"), ("2379", "Other heavy & civil"), ("2381", "Foundation, structure & exterior"),
          ("2382", "Building equipment (electrical, plumbing, HVAC)"), ("2383", "Building finishing"), ("2389", "Other specialty trades"),
          ("3323", "Architectural & structural metals")]
GNAME = dict(GROUPS)

rows = []
for part in ("bids-2026-10-03-part1.tsv", "bids-2026-10-03-part2.tsv"):
    with open(part, encoding="utf-8") as f:
        rows += list(csv.DictReader(f, delimiter="\t"))
for r in rows:
    r["title"] = r["title"].replace("â€“", "–").strip()
rows.sort(key=lambda r: (r["due"] == "", r["due"], r["title"]))

F = "Arial"
H = Font(name=F, bold=True, color="FFFFFF"); B = Font(name=F); BB = Font(name=F, bold=True)
LINK = Font(name=F, color="0563C1", underline="single"); SMALL = Font(name=F, size=9, color="666666")
HEAD = PatternFill("solid", fgColor="1F3A4D"); BAND = PatternFill("solid", fgColor="EEF3F6")
OPEN = PatternFill("solid", fgColor="E5F2E7"); EDGE = Border(bottom=Side(style="thin", color="C9D3D9"))

def sheet(wb, title, headers, widths):
    ws = wb.create_sheet(title); ws.append(headers)
    for c in ws[1]:
        c.font = H; c.fill = HEAD; c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30
    for i, w in enumerate(widths, 1): ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    return ws

def finish(ws, link_col=None, date_col=1, days_col=2):
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for c in row:
            c.font = B; c.border = EDGE; c.alignment = Alignment(vertical="top", wrap_text=True)
            if c.row % 2 == 0: c.fill = BAND
        if date_col: row[date_col - 1].number_format = "ddd mmm d"
        if days_col: row[days_col - 1].number_format = '0;"past";0'
        if link_col: row[link_col - 1].font = LINK
    ws.auto_filter.ref = ws.dimensions

def bid_rows(ws, subset):
    for i, r in enumerate(subset, 2):
        ws.append([date.fromisoformat(r["due"]) if r["due"] else None, f'=IF(A{i}="","",A{i}-TODAY())', r["title"],
                   N6.get(r["naics"], r["naics"]), GNAME.get(r["naics"][:4], ""), ", ".join(x for x in (r["city"], r["state"]) if x) or "See notice",
                   WHO.get(r["setaside"], r["setaside"]), TYPE.get(r["type"], r["type"]), r["agency"], r["naics"],
                   f'=HYPERLINK("https://sam.gov/opp/{r["id"]}/view","Open on SAM.gov")'])
        if r["setaside"] == "NONE": ws.cell(row=i, column=7).fill = OPEN

wb = Workbook(); ws = wb.active; ws.title = "Read Me"
lines = [
    ("Open Federal Construction & Steel Bids", Font(name=F, bold=True, size=16)),
    (f"{len(rows)} open bids, pulled {PULLED} by Set-Aside Radar from SAM.gov", Font(name=F, size=11, color="555555")),
    ("", B),
    ("The tabs", BB),
    ("All Open Bids: every open bid, soonest deadline first, with days left and a link to the notice.", B),
    ("Steel & Metals: the same, only structural steel, concrete, masonry, roofing and metal fabrication.", B),
    ("By Trade: how many open bids each trade has, split into set-asides and open-to-anyone.", B),
    ("", B),
    ("\"Who can bid\" tells you who is eligible. Green = any business can bid, no certification needed.", B),
    ("The rest are set aside: small businesses, veteran-owned, 8(a), women-owned and so on.", B),
    ("", B),
    ("PBM Consulting Service · pbmconsultingservice.com · 6814 Chris Madsen Rd, Guthrie, OK 73044", BB),
    ("", B),
    ("Source: SAM.gov contract opportunities (public U.S. government data), as stored by Set-Aside Radar.", SMALL),
    ("Radar keeps every set-aside notice; open-to-anyone notices appear only when SAM.gov marks them \"No set aside used\",", SMALL),
    ("so the open-to-anyone list is a partial count. Check each notice on SAM.gov before bidding: terms can change.", SMALL),
]
for i, (t, f) in enumerate(lines, 1): ws.cell(row=i, column=1, value=t).font = f
ws.column_dimensions["A"].width = 110

hdr = ["Due", "Days left", "Job", "Trade", "Trade group", "Where", "Who can bid", "Notice type", "Agency", "NAICS", "Notice"]
wid = [12, 9, 50, 28, 26, 20, 30, 22, 30, 9, 16]
ws = sheet(wb, "All Open Bids", hdr, wid); bid_rows(ws, rows); finish(ws, link_col=11)
steel = [r for r in rows if r["naics"][:4] in ("2381", "3323")]
ws = sheet(wb, "Steel & Metals", hdr, wid); bid_rows(ws, steel); finish(ws, link_col=11)

ws = sheet(wb, "By Trade", ["NAICS group", "Trade", "Set-aside bids", "Open to anyone", "Total open"], [12, 46, 15, 15, 12])
n = len(rows) + 1
for i, (code, name) in enumerate(GROUPS, 2):
    ws.append([code, name,
               f"=COUNTIFS('All Open Bids'!$E$2:$E${n},B{i},'All Open Bids'!$G$2:$G${n},\"<>Any business (no set-aside)\")",
               f"=COUNTIFS('All Open Bids'!$E$2:$E${n},B{i},'All Open Bids'!$G$2:$G${n},\"Any business (no set-aside)\")",
               f"=C{i}+D{i}"])
last = ws.max_row
ws.append(["", "All trades", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})", f"=SUM(E2:E{last})"])
finish(ws, date_col=None, days_col=None)
for c in ws[ws.max_row]: c.font = BB
ws.cell(row=ws.max_row + 2, column=1, value="Counts come from the All Open Bids tab, so they update if rows there change.").font = SMALL

out = f"PBM-Open-Federal-Construction-Bids-{PULLED}.xlsx"
wb.save(out); print(out, len(rows), "bids,", len(steel), "steel & metals")
