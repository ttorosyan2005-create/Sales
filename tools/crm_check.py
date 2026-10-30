#!/usr/bin/env python3
"""Проверка базы лидов: формат, дубли, стоп-лист.

Использование:
  python3 tools/crm_check.py                      # проверить data/leads.csv
  python3 tools/crm_check.py --candidate "Имя" [--site домен] [--inn ИНН] [--phone телефон]
"""
import argparse
import csv
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
LEADS = ROOT / "data" / "leads.csv"
STOP = ROOT / "data" / "do_not_contact.csv"

COLUMNS = ["id", "компания", "сегмент", "район", "адрес", "сайт", "соцсети", "ИНН", "ЛПР и должность",
           "рабочий контакт", "признаки соответствия", "оценка", "обоснование", "рекомендуемые позиции",
           "канал первого касания", "статус", "дата", "источник"]
STATUSES = {"new", "qualified", "contacted", "replied", "meeting", "deal", "lost"}
NOT_FOUND = "не найдено"
STOP_WORDS = ["ооо", "ип", "ресторан", "кафе", "бар", "лавка", "магазин", "restaurant", "cafe"]


def norm_name(s):
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[«»\"'`.,!?()\-–—]", " ", s)
    words = [w for w in s.split() if w not in STOP_WORDS]
    return " ".join(words)


def norm_site(s):
    s = (s or "").strip().lower()
    if not s or s == NOT_FOUND:
        return ""
    if "://" not in s:
        s = "http://" + s
    host = urlparse(s).netloc
    return host[4:] if host.startswith("www.") else host


def norm_inn(s):
    d = re.sub(r"\D", "", s or "")
    return d if len(d) in (10, 12) else ""


def norm_phones(s):
    out = set()
    for m in re.findall(r"(?:\+7|8)?[\s(]*\d{3}[\s)]*\d{3}[\s-]*\d{2}[\s-]*\d{2}", s or ""):
        d = re.sub(r"\D", "", m)
        if len(d) == 11 and d[0] in "78":
            d = d[1:]
        if len(d) == 10:
            out.add(d)
    return out


def read(path):
    if not path.exists():
        return [], []
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames or [], list(r)


def keys(row, name_col, site_col, inn_col, phone_cols):
    return {
        "name": norm_name(row.get(name_col, "")),
        "site": norm_site(row.get(site_col, "")),
        "inn": norm_inn(row.get(inn_col, "")),
        "phones": set().union(*(norm_phones(row.get(c, "")) for c in phone_cols)),
    }


def lead_keys(row):
    return keys(row, "компания", "сайт", "ИНН", ["рабочий контакт"])


def stop_keys(row):
    return keys(row, "компания", "сайт", "ИНН", ["телефон организации"])


def match(a, b):
    why = []
    if a["name"] and a["name"] == b["name"]:
        why.append("название")
    if a["site"] and a["site"] == b["site"]:
        why.append("сайт")
    if a["inn"] and a["inn"] == b["inn"]:
        why.append("ИНН")
    if a["phones"] & b["phones"]:
        why.append("телефон")
    return why


def check_candidate(args):
    cand = {"name": norm_name(args.candidate), "site": norm_site(args.site), "inn": norm_inn(args.inn),
            "phones": norm_phones(args.phone)}
    found = False
    for row in read(STOP)[1]:
        why = match(cand, stop_keys(row))
        if why:
            found = True
            print(f"СТОП-ЛИСТ: {row.get('компания')} — совпадение: {', '.join(why)}; причина: {row.get('причина')}")
    for row in read(LEADS)[1]:
        why = match(cand, lead_keys(row))
        if why:
            found = True
            print(f"ДУБЛЬ: {row.get('id')} {row.get('компания')} — совпадение: {', '.join(why)}; статус: {row.get('статус')}")
    if not found:
        print("OK: совпадений нет")
    return 1 if found else 0


def check_base():
    errors = []
    header, rows = read(LEADS)
    if header != COLUMNS:
        errors.append(f"заголовок leads.csv не совпадает с форматом.\n  ожидается: {COLUMNS}\n  есть:      {header}")
    ids = {}
    for i, row in enumerate(rows, start=2):
        rid = row.get("id", "")
        tag = f"строка {i} ({rid or 'без id'})"
        if not re.fullmatch(r"L-\d{4}", rid or ""):
            errors.append(f"{tag}: id должен быть вида L-0001")
        if rid in ids:
            errors.append(f"{tag}: id повторяется (строка {ids[rid]})")
        ids[rid] = i
        for c in COLUMNS:
            if not (row.get(c) or "").strip():
                errors.append(f"{tag}: пустая ячейка «{c}», нужно «{NOT_FOUND}»")
        score = row.get("оценка", "")
        if not (score.isdigit() and 1 <= int(score) <= 10):
            errors.append(f"{tag}: оценка должна быть целым числом 1–10, сейчас «{score}»")
        if row.get("статус") not in STATUSES:
            errors.append(f"{tag}: недопустимый статус «{row.get('статус')}»")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row.get("дата", "")):
            errors.append(f"{tag}: дата должна быть ГГГГ-ММ-ДД")
        if "http" not in row.get("источник", ""):
            errors.append(f"{tag}: в источнике нет URL")

    lk = [(r, lead_keys(r)) for r in rows]
    for a in range(len(lk)):
        for b in range(a + 1, len(lk)):
            why = match(lk[a][1], lk[b][1])
            if why:
                errors.append(f"ДУБЛЬ: {lk[a][0]['id']} и {lk[b][0]['id']} — совпадение: {', '.join(why)}")
    stops = [(s, stop_keys(s)) for s in read(STOP)[1]]
    for r, k in lk:
        for s, sk in stops:
            why = match(k, sk)
            if why and r.get("статус") != "lost":
                errors.append(f"СТОП-ЛИСТ: {r['id']} {r['компания']} совпадает с «{s['компания']}» ({', '.join(why)}), статус должен быть lost")

    print(f"Лидов: {len(rows)}; в стоп-листе: {len(stops)}")
    by_status = {}
    for r in rows:
        by_status[r.get("статус")] = by_status.get(r.get("статус"), 0) + 1
    if by_status:
        print("По статусам: " + ", ".join(f"{k}: {v}" for k, v in sorted(by_status.items(), key=str)))
    for e in errors:
        print("ОШИБКА:", e)
    print("OK" if not errors else f"Ошибок: {len(errors)}")
    return 1 if errors else 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidate")
    p.add_argument("--site", default="")
    p.add_argument("--inn", default="")
    p.add_argument("--phone", default="")
    args = p.parse_args()
    sys.exit(check_candidate(args) if args.candidate else check_base())


if __name__ == "__main__":
    main()
