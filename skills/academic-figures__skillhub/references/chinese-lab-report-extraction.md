# Chinese Hospital Lab Report PDF Extraction

## Problem

Chinese hospital LIS (Laboratory Information System) PDFs use non-standard layouts:
- `page.find_tables()` returns 0 tables (not real PDF tables)
- `page.get_text()` produces **column-mixed** text — header fields (项目名称, 结果, 单位…) and data are interleaved, not row-aligned
- Sequential "6 lines per item" parsing fails because text blocks from different columns merge unpredictably

## Solution: Regex-on-Full-Text

Extract the full text blob, then apply per-indicator regex patterns:

```python
import fitz, re

doc = fitz.open("lab_report.pdf")
text = "".join(page.get_text() for page in doc)
doc.close()

# Known indicator patterns (indicator name → numeric value)
INDICATORS = [
    ("白细胞", r"白细胞计数\s+([\d.]+[↑↓]?)\s*(10\^9/L)"),
    ("血红蛋白", r"血红蛋白浓度\s+([\d.]+[↑↓]?)\s*(g/L)"),
    ("血小板", r"血小板计数\s+([\d.]+[↑↓]?)\s*(10\^9/L)"),
    ("铁蛋白", r"铁蛋白\s+([\d.]+[↑↓]?)\s*(ng/mL)"),
    ("CRP", r"C反应蛋白\s+([\d.]+[↑↓]?)\s*(mg/L)"),
    ("纤维蛋白原", r"纤维蛋白原\s+([\d.]+[↑↓]?)\s*(g/L)"),
    ("LDH", r"乳酸脱氢酶\s+([\d.]+[↑↓]?)\s*(U/L|mg/L)"),
    # ... add more as needed
]

for name, pattern in INDICATORS:
    m = re.search(pattern, text)
    if m:
        val = float(re.sub(r"[↑↓]", "", m.group(1)))
        # store {name: val, unit: m.group(2)}
```

## Key Patterns

- **Date extraction**: Search for `采集时间/接收时间/报告时间：YYYY-MM-DD` in footer area
- **Specimen type**: `标本类型：` followed by value
- **Skip non-lab reports**: Filter out 超声, 心电图, 外送检验 (康圣达/金域)
- **Same-day dedup**: Multiple reports may share a date — merge by indicator name

## Desensitization Checklist

When converting to chart data:
- Remove: 患儿姓名, 住院号, 床号, 医院/科室名称, 检验者/审核者
- Convert dates → "第N天" (day N)
- Only retain: indicator name, numeric value, unit, reference range

## Arrow Position Variation

Hospital LIS PDFs inconsistently place ↑/↓ arrows:
- Most local reports: `208.48↑` (arrow after number)
- Some凝血 reports: `↑10.66` (arrow **before** number)
- Some external reports: `↑` on a **separate line** from the value

Regex must handle all three: `(?:↑|↓)?([\d.]+)` or `([\d.]+)[↑↓]?`

## External Lab Reports (康圣达/金域)

Different format from local hospital reports:
- Table structure: `项目名 | 英文简称 | 结果 | 参考区间 | 单位 | 检测方法`
- Values may be on separate lines or same row
- Arrow may be on its own line (e.g., `FOL\n13.20\n...` then later `↓\n化学发光法`)
- Use a separate extraction function that searches for indicator name, then scans next few lines for the first numeric value

```python
def extract_external_value(text, indicator_name, max_lines=4):
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if indicator_name in line:
            for j in range(i+1, min(i+max_lines, len(lines))):
                vline = lines[j].strip()
                m = re.match(r'^([\d.]+|<[\d.]+)', vline)
                if m:
                    val_str = m.group(1).replace('<','').replace('>','')
                    return float(val_str)
    return None
```

## Pitfalls

1. **Indicator names vary across hospitals** — the same test may have different Chinese names. Build a regex list per hospital/LIS system.
2. **MuPDF ExtGState warnings** — `cannot find ExtGState resource 'GS00N'/'GSFFN'` are cosmetic warnings from hospital PDF security watermarks; they don't affect text extraction.
3. **Column order instability** — some reports swap "结果" and "单位" columns between reports. Always anchor on the Chinese indicator name, not on position.
4. **NK activity, T-cell subsets** — these often come from separate specialized labs with different report formats; may need separate parsing logic.
5. **Sequential-line parsing fails** — do NOT assume "项目名称\n结果\n单位\n参考区间\n互认\n检测方法" = 6 consecutive lines. The PDF text extraction interleaves columns. Always use regex anchored on indicator name.
6. **Date from barcode vs footer** — barcodes (条码号) contain date (YYMMDDHHMMSS) but may be unreliable. Always prefer `采集时间/接收时间/报告时间：YYYY-MM-DD` from the footer area.
