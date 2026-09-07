#!/usr/bin/env python3
"""
Extract structured lab data from Chinese hospital PDF reports.
Usage: python3 extract_lab_pdf.py /path/to/folder/ [output.json]

Outputs JSON: [{"date": "YYYY-MM-DD", "day": N, "indicators": {name: value, ...}}, ...]

Desensitization: automatically strips patient names, IDs, hospital names.
"""
import fitz, os, re, json, sys, warnings
from collections import defaultdict

warnings.filterwarnings("ignore")

# === INDICATOR REGEX PATTERNS ===
# Extend this list per hospital/LIS system as needed.
# Pattern: (standardized_name, regex)
INDICATORS = [
    # Blood count
    ("白细胞", r"白细胞计数\s+([\d.]+[↑↓]?)\s*(10\^9/L)"),
    ("中性粒细胞%", r"中性粒细胞百分数\s+([\d.]+[↑↓]?)\s*(%)"),
    ("中性粒细胞#", r"中性粒细胞绝对值\s+([\d.]+[↑↓]?)\s*(10\^9/L)"),
    ("淋巴细胞%", r"淋巴细胞百分数\s+([\d.]+[↑↓]?)\s*(%)"),
    ("淋巴细胞#", r"淋巴细胞绝对值\s+([\d.]+[↑↓]?)\s*(10\^9/L)"),
    ("血红蛋白", r"血红蛋白浓度\s+([\d.]+[↑↓]?)\s*(g/L)"),
    ("血小板", r"血小板计数\s+([\d.]+[↑↓]?)\s*(10\^9/L)"),
    ("红细胞", r"红细胞计数\s+([\d.]+[↑↓]?)\s*(10\^12/L)"),
    # HLH markers
    ("铁蛋白", r"铁蛋白\s+([\d.]+[↑↓]?)\s*(ng/mL)"),
    ("甘油三酯", r"甘油三酯\s+([\d.]+[↑↓]?)\s*(mmol/L)"),
    ("纤维蛋白原", r"纤维蛋白原\s+([\d.]+[↑↓]?)\s*(g/L)"),
    ("LDH", r"乳酸脱氢酶\s+([\d.]+[↑↓]?)\s*(U/L|mg/L)"),
    # Coagulation
    ("PT", r"凝血酶原时间\s+([\d.]+[↑↓]?)\s*(秒)"),
    ("APTT", r"活化部分凝血活酶时间\s+([\d.]+[↑↓]?)\s*(秒)"),
    ("D-二聚体", r"D-二聚体\s+([\d.]+[↑↓]?)\s*(ug/ml)"),
    ("INR", r"国际标准化比值\s+([\d.]+[↑↓]?)"),
    # Inflammation
    ("CRP", r"C反应蛋白\s+([\d.]+[↑↓]?)\s*(mg/L)"),
    ("PCT", r"降钙素原\s+([\d.]+[↑↓]?)"),
    # Liver
    ("ALT", r"谷丙转氨酶\s+([\d.]+[↑↓]?)\s*(U/L)"),
    ("AST", r"谷草转氨酶\s+([\d.]+[↑↓]?)\s*(U/L)"),
    ("总胆红素", r"总胆红素\s+([\d.]+[↑↓]?)\s*(umol/L)"),
    ("白蛋白", r"白蛋白\s+([\d.]+[↑↓]?)\s*(g/L)"),
    ("球蛋白", r"球蛋白\s+([\d.]+[↑↓]?)\s*(g/L)"),
    ("GGT", r"谷氨酰转肽酶\s+([\d.]+[↑↓]?)\s*(U/L)"),
    # Renal
    ("肌酐", r"肌酐\s+([\d.]+[↑↓]?)\s*(umol/L)"),
    # Blood gas
    ("乳酸", r"乳酸\s+([\d.]+[↑↓]?)\s*(mmol/L)"),
    # T-cell subsets
    ("CD3+", r"总T淋巴细胞百分率.*?([\d.]+[↑↓]?)\s*%"),
    ("CD4+", r"辅助/诱导T淋巴细胞百分率.*?([\d.]+[↑↓]?)\s*%"),
    ("CD8+", r"抑制/细胞毒性T淋巴细胞百分率.*?([\d.]+[↑↓]?)\s*%"),
]

SKIP_KEYWORDS = ["彩色多普勒", "心电图报告"]

def extract_date(text):
    for field in ["采集时间", "接收时间", "报告时间"]:
        m = re.search(field + r"[：:]\s*(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)
    return None

def extract_indicators(text):
    items = {}
    for name, pattern in INDICATORS:
        m = re.search(pattern, text)
        if m:
            clean = re.sub(r"[↑↓]", "", m.group(1))
            try:
                items[name] = float(clean)
            except ValueError:
                items[name] = clean
    return items

def process_folder(folder):
    results = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".pdf"):
            continue
        path = os.path.join(folder, f)
        try:
            doc = fitz.open(path)
            text = "".join(page.get_text() for page in doc)
            doc.close()
        except Exception:
            continue

        if any(kw in text for kw in SKIP_KEYWORDS):
            continue

        date = extract_date(text)
        indicators = extract_indicators(text)
        if indicators:
            results.append({"file": f, "date": date, "indicators": indicators})

    # Convert to day numbers
    dates = sorted(set(r["date"] for r in results if r["date"]))
    date_to_day = {d: i + 1 for i, d in enumerate(dates)}

    for r in results:
        if r["date"]:
            r["day"] = date_to_day[r["date"]]
        # Desensitize: remove filename
        del r["file"]

    return results

if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    out = sys.argv[2] if len(sys.argv) > 2 else None
    data = process_folder(folder)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(data)} records to {out}")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
