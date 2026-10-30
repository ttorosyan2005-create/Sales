#!/usr/bin/env python3
"""Сводит research/regions/*.csv в data/regional_wholesalers.csv и .xlsx (лист на каждый округ)."""
import csv, glob, os, re, sys
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDER = ["ЦФО", "СЗФО", "ЮФО", "СКФО", "ПФО", "УФО", "СФО", "ДФО"]
FIELDS = ["компания", "федеральный округ", "регион", "город", "тип", "что продаёт (факты)", "сайт", "рабочий контакт", "ИНН",
          "признаки соответствия", "оценка", "обоснование", "рекомендуемые позиции", "канал первого касания", "связь с нами", "источник"]

def norm(s): return re.sub(r"[^a-zа-я0-9]", "", s.lower().replace("ё", "е").replace("ооо", ""))

rows, seen, dup = [], {}, []
for f in sorted(glob.glob(os.path.join(ROOT, "research", "regions", "*.csv"))):
    for r in csv.DictReader(open(f, encoding="utf-8")):
        r = {k: (r.get(k) or "не найдено").strip() or "не найдено" for k in FIELDS}
        site = re.sub(r"^https?://(www\.)?", "", r["сайт"]).split("/")[0].lower()
        key = site if site and site != "не найдено" else norm(r["компания"])
        if key in seen:
            dup.append((r["компания"], seen[key])); continue
        seen[key] = r["компания"]
        try: r["оценка"] = int(float(str(r["оценка"]).replace(",", ".")))
        except ValueError: r["оценка"] = 0
        rows.append(r)
rows.sort(key=lambda r: (ORDER.index(r["федеральный округ"]) if r["федеральный округ"] in ORDER else 99, -r["оценка"], r["компания"]))
for i, r in enumerate(rows, 1):
    r["id"] = f"R-{i:04d}"; r["статус"] = "qualified" if r["оценка"] >= 6 else "new"; r["дата"] = "2026-10-30"
cols = ["id"] + FIELDS[:-1] + ["статус", "дата", "источник"]
with open(os.path.join(ROOT, "data", "regional_wholesalers.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)

wb = Workbook(); summary = wb.active; summary.title = "Сводка"
hdr_font = Font(bold=True, color="FFFFFF"); hdr_fill = PatternFill("solid", fgColor="1F4E78")
summary.append(["Округ", "Оптовиков", "Оценка 8–10", "Уже продают наши марки", "Возможные конкуренты"])
widths = {"id": 8, "компания": 30, "регион": 18, "город": 16, "тип": 20, "что продаёт (факты)": 45, "сайт": 28, "рабочий контакт": 30,
          "ИНН": 13, "признаки соответствия": 45, "оценка": 8, "обоснование": 45, "рекомендуемые позиции": 40,
          "канал первого касания": 24, "связь с нами": 18, "статус": 10, "дата": 11, "источник": 45, "федеральный округ": 10}
for fo in ORDER + sorted({r["федеральный округ"] for r in rows} - set(ORDER)):
    part = [r for r in rows if r["федеральный округ"] == fo]
    if not part: continue
    summary.append([fo, len(part), sum(r["оценка"] >= 8 for r in part),
                    sum("наши" in r["связь с нами"] for r in part), sum("конкурент" in r["связь с нами"] for r in part)])
    ws = wb.create_sheet(fo); ws.append(cols)
    for r in part: ws.append([r[c] for c in cols])
    for c in ws[1]: c.font = hdr_font; c.fill = hdr_fill; c.alignment = Alignment(wrap_text=True, vertical="top")
    for i, c in enumerate(cols, 1): ws.column_dimensions[get_column_letter(i)].width = widths.get(c, 18)
    for row in ws.iter_rows(min_row=2):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
        sc = row[cols.index("оценка")]
        sc.fill = PatternFill("solid", fgColor="C6EFCE" if sc.value >= 8 else ("FFEB9C" if sc.value >= 6 else "F2F2F2"))
    ws.freeze_panes = "C2"; ws.auto_filter.ref = ws.dimensions
summary.append(["Всего", len(rows)])
for c in summary[1]: c.font = hdr_font; c.fill = hdr_fill
for col, wdt in zip("ABCDE", (12, 12, 14, 24, 22)): summary.column_dimensions[col].width = wdt
wb.save(os.path.join(ROOT, "data", "regional_wholesalers.xlsx"))
print(f"оптовиков: {len(rows)}; дублей убрано: {len(dup)}")
for a, b in dup: print("  дубль:", a, "=", b)
