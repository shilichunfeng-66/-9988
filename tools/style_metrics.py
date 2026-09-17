#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文风指标实测工具（本科毕业论文降 AI 用）

配合 `reference-db/格式参考/本科生毕业论文文风基准-实测.md` 使用：
把待检 docx（或两份，做前后对比）跑一遍，输出句均字长 / 句长变异 CV / 长句占比 /
顿号·分号·破折号密度 / 括号数 /「本文」密度，与真人基准逐项对照。

用法
----
    python tools/style_metrics.py 待检稿.docx
    python tools/style_metrics.py 调整前.docx 调整后.docx      # 前后对比
    python tools/style_metrics.py 待检稿.docx --json          # 机器可读

口径说明（重要，别改）
--------------------
按**正文口径**统计：剔除标题（黑体）、署名行（楷体）、摘要与关键词、参考文献条目。
摘要是一整段长句，混进来会把句均与 CV 一起抬高，造成"假达标"，必须单列。
"""
import json
import re
import statistics
import sys

from docx import Document
from docx.oxml.ns import qn

# 真人定稿基准（见 reference-db/格式参考/本科生毕业论文文风基准-实测.md）
BASELINE = {
    "句均": 72.0,
    "CV": 0.83,
    "长句": 53.0,
    "顿号": 15.7,
    "分号": 1.1,
    "本文": 2.57,
}
# 各类型都应达标的硬线（理论推演型按此判断；调查实证型按 BASELINE 判断）
HARD = {"句均": 65.0, "长句": 45.0, "分号": 2.0, "括号": 2, "破折号": 0}
CJK = r"[\u4e00-\u9fff]"


def _ea_font(p):
    if not p.runs:
        return None
    try:
        return p.runs[0]._element.rPr.rFonts.get(qn("w:eastAsia"))
    except AttributeError:
        return None


def is_heading(p):
    """标题判定：样式版（Heading n）与直接排版版（黑体）都算。"""
    if p.style is not None and p.style.name.startswith("Heading"):
        return True
    return _ea_font(p) == "黑体"


def body_text(path):
    """抽出**正文**：从第一章标题起、到「参考文献」止，标题与前置页一律不计。

    这样两种排版稿（样式版 / 直接排版版）口径一致，封面、目录、摘要、Abstract、
    关键词、参考文献、致谢、附录都不会混进来把指标抬虚。
    """
    doc = Document(path)
    ps = doc.paragraphs
    start, end = None, len(ps)
    for i, p in enumerate(ps):
        t = p.text.strip()
        if is_heading(p) and re.match(r"^(一、|1[\s　]|1$)", t):
            start = i + 1
            break
    for i, p in enumerate(ps):
        if is_heading(p) and p.text.strip().replace(" ", "") == "参考文献":
            end = i
            break
    buf = []
    for p in ps[start if start is not None else 0:end]:
        t = p.text.strip()
        if not t or not p.runs or is_heading(p):
            continue
        if t.startswith("摘要") or t.startswith("Abstract") or t.startswith("关键词"):
            continue
        if re.match(r"^\[\d+\]", t):
            continue
        if len(re.findall(CJK, t)) < 4:
            continue
        buf.append(t)
    return "".join(buf)


def abstract_text(path):
    """取中文摘要正文：优先「摘要」标题的下一段；兼容摘要与标题同段的直接排版稿。"""
    doc = Document(path)
    ps = doc.paragraphs
    for i, p in enumerate(ps):
        t = p.text.strip()
        if p.style is not None and p.style.name.startswith("Heading") and t in ("摘要", "摘 要"):
            for nxt in ps[i + 1:]:
                if len(re.findall(CJK, nxt.text)) > 20:
                    return nxt.text.strip()
                if nxt.style.name.startswith("Heading"):
                    break
    for p in ps:
        t = p.text.strip()
        if t.startswith("摘要") and len(re.findall(CJK, t)) > 20:
            return t
    return ""


def sent_lengths(txt):
    parts = [s for s in re.split(r"[。！？]", txt) if len(re.findall(CJK, s)) > 3]
    return [len(re.findall(CJK, s)) for s in parts]


def measure(path):
    txt = body_text(path)
    cn = len(re.findall(CJK, txt))
    if not cn:
        return {}
    L = sent_lengths(txt)
    mean = sum(L) / len(L)
    ab = abstract_text(path)
    ab_L = sent_lengths(ab)
    per_k = lambda pat: round(len(re.findall(pat, txt)) / cn * 1000, 1)
    return {
        "文件": path,
        "正文字数": cn,
        "句数": len(L),
        "句均": round(mean, 1),
        "CV": round(statistics.pstdev(L) / mean, 2),
        "长句": round(sum(1 for x in L if x >= 60) / len(L) * 100),
        "顿号": per_k("、"),
        "分号": per_k("；"),
        "破折号": per_k("——"),
        "括号": len(re.findall(r"[（(]", txt)),
        "本文": per_k("本文"),
        "摘要字数": len(re.findall(CJK, ab)),
        "摘要句数": len(ab_L),
    }


def _basename(p):
    return str(p).replace("/", "\\").split("\\")[-1]


# 「结构过于对称」高 AI 风险句式（2026-09-17 实测：被 PaperPure 标红的段落几乎都中一条以上）
SYMMETRY_PATTERNS = [
    ("编号罗列 一是…二是…", r"一是.{2,60}?，二是"),
    ("递进排比 先靠…再靠…", r"先靠.{2,40}?再靠"),
    ("二元对称 理论上…实践上…", r"理论上.{2,80}?实践上"),
    ("分层对称 对…层面而言", r"对.{2,10}?层面而言"),
    ("镜像双句 X等…Y等则…", r"等[^，。]{0,6}则[^，。]{0,4}(聚焦|关注|提出|认为)"),
    ("序数词 首先/其次/最后", r"(首先，|其次，|最后，)"),
    ("套语 综上所述/由此可见", r"(综上所述|由此可见)"),
    ("递进套式 不仅…而且", r"不仅.{2,40}?而且"),
    ("四字对仗三连", r"([\u4e00-\u9fff]{2}，[\u4e00-\u9fff]{2}，){2}"),
    ("假靶子 不是A而是B", r"不是.{2,40}?而是"),
    ("定义式长列举 指因…、…、…等", r"指[^。]{6,60}?等(原因|因素|方面|情况)"),
]


def scan_patterns(path):
    """逐段扫描高 AI 风险的结构句式，返回 [(模式, 段前 24 字), ...]。"""
    doc = Document(path)
    hits = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if not t or is_heading(p):
            continue
        for name, pat in SYMMETRY_PATTERNS:
            if re.search(pat, t):
                hits.append((name, t[:24]))
    return hits


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    as_json = "--json" in argv
    if not args:
        print(__doc__)
        return 2
    rows = [measure(p) for p in args]
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    keys = ["正文字数", "句数", "句均", "CV", "长句", "顿号", "分号", "破折号", "括号", "本文", "摘要字数", "摘要句数"]
    labels = [_basename(r.get("文件", "?"))[:26] for r in rows]
    w = max(12, max(len(x) for x in labels) + 2)
    print("基准：句均≥65 / 长句≥45% / 分号≤2千字 / 括号≤2处 / 破折号 0；调查实证型另比真人基准\n")
    print(" ".join(["指标".ljust(8)] + [x.ljust(w) for x in labels]))
    for k in keys:
        print(" ".join([k.ljust(8)] + [str(r.get(k, "-")).ljust(w) for r in rows]))
    print("\n真人基准（调查实证型参考）: " + " / ".join(f"{k} {v}" for k, v in BASELINE.items()))

    print("\n结构对称扫描（高 AI 风险句式，命中越少越好）:")
    for r in rows:
        hits = scan_patterns(r["文件"])
        if not hits:
            print(f"  {_basename(r['文件'])}: 无命中")
            continue
        print(f"  {_basename(r['文件'])}: 命中 {len(hits)} 处")
        for name, head in hits:
            print(f"    - {name} ｜ {head}…")

    print("\n判定（按硬线，理论推演型口径）:")
    for r in rows:
        bad = []
        if r.get("句均", 0) < HARD["句均"]:
            bad.append("句均未达 65")
        if r.get("长句", 0) < HARD["长句"]:
            bad.append("长句占比未达 45%")
        if r.get("分号", 9) > HARD["分号"]:
            bad.append("分号偏高")
        if r.get("括号", 0) > HARD["括号"]:
            bad.append("括号偏多")
        if r.get("破折号", 0) > HARD["破折号"]:
            bad.append("有破折号")
        n_hit = len(scan_patterns(r["文件"]))
        if n_hit:
            bad.append(f"对称句式 {n_hit} 处")
        tag = "通过" if not bad else "、".join(bad)
        print(f"  {_basename(r.get('文件', '?'))}: {tag}")
    return 1 if any(
        r.get("句均", 0) < HARD["句均"] or r.get("长句", 0) < HARD["长句"] or r.get("破折号", 0) > 0
        for r in rows
    ) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
