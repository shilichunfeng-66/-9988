#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_doc.py — 正文回检工具（申报书 / 活页 / 论文 通用）

校验项（逐项给出问题清单）：
  1. 字数统计（中文字符 / 含标点）
  2. 文献表编号：是否 1→N 连续正序（不跳号、不倒序）
  3. 正文引用锚点 [n]：是否 ⊆ 文献表编号（有无"引了但没列"或"列了但没引"）
  4. 文献编号是否按正文首次引用顺序（中英混排，不按语种分组）
  5. 匿名合规（--anonymous）：可疑的姓名/单位/刊物/联系方式等个人信息
  6. 禁词检测：学生腔与 AI 腔黑名单（浅析、初探、综上所述、国际领先、赋能、抓手、闭环…）

用法：
    python tools/check_doc.py 稿件.md
    python tools/check_doc.py 稿件.md --anonymous --min-chars 5000
    python tools/check_doc.py 稿件.md --json

说明：面向 Markdown/纯文本稿件；docx 请先转 md 或粘贴正文为 txt。
退出码：0 = 通过（可含提示）；1 = 存在问题需修改。
"""
import io, os, re, sys, json, argparse

REF_HEAD = "参考文献"
CJK = r"[\u4e00-\u9fff]"

BANNED = [
    "浅析", "初探", "初探性", "综上所述", "由此可见", "值得注意的是", "众所周知",
    "国际领先", "填补空白", "国内首创", "世界领先",
    "赋能", "抓手", "闭环", "范式", "生态位", "痛点",
    "随着人工智能的飞速发展", "随着科技的不断发展", "随着社会的发展",
    "具有重要意义", "深远影响", "提供了有力支撑", "奠定了坚实基础",
]
BANNED_PATTERNS = [
    (r"不是[^，。；]{1,20}，而是", "「不是A而是B」假靶子句式"),
    (r"随着[^，。]{0,15}的(不断|飞速|快速)(发展|进步)", "「随着…的不断发展」套路开头"),
    (r"首先[^。]{0,80}其次[^。]{0,80}最后", "机械三段式（首先/其次/最后）"),
]
PII_PATTERNS = [
    (r"[\u4e00-\u9fff]{2,4}(教授|副教授|讲师|研究员|博士|硕士)", "疑似职称+人名"),
    (r"(大学|学院|师范大学|职业技术学院|研究所|附属医院)", "疑似单位名称"),
    (r"[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}", "邮箱地址"),
    (r"\b1[3-9]\d{9}\b", "手机号码"),
    (r"\b\d{17}[\dXx]\b", "身份证号"),
    (r"\d{4}\s*年\s*\d{1,2}\s*月.*(发表|刊于|出版)", "刊物发表时间信息"),
]


def read_text(path):
    if path.lower().endswith(".docx"):
        try:
            from docx import Document
            d = Document(path)
            return "\n".join(p.text for p in d.paragraphs)
        except Exception as e:
            print(f"[warn] 无法读取 docx（{e}），请转为 md/txt 后重试", file=sys.stderr)
            return ""
    return io.open(path, "r", encoding="utf-8", errors="replace").read()


def split_refs(text):
    """返回 (正文, 文献区)；找不到参考文献表则文献区为 None"""
    i = text.rfind(REF_HEAD)
    if i < 0:
        return text, None
    return text[:i], text[i:]


def parse_ref_numbers(ref_block):
    nums = []
    for line in ref_block.splitlines():
        m = re.match(r"\s*\[(\d+)\]", line)
        if m:
            nums.append(int(m.group(1)))
    return nums


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--anonymous", action="store_true", help="启用匿名合规检查（活页/盲审稿）")
    ap.add_argument("--min-chars", type=int, default=0, help="最低中文字符数（不足则报问题）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print(f"[error] 文件不存在: {args.file}"); sys.exit(2)
    text = read_text(args.file)
    if not text.strip():
        print("[error] 文件内容为空或无法解析"); sys.exit(2)

    body, refs = split_refs(text)
    report = {"file": args.file, "problems": [], "notes": []}

    # 1. 字数
    cjk = len(re.findall(CJK, text))
    total = len(re.sub(r"\s", "", text))
    report["chars"] = {"cjk": cjk, "with_punct": total}
    if args.min_chars and cjk < args.min_chars:
        report["problems"].append(f"字数不足: 中文字符 {cjk} < 要求 {args.min_chars}")

    # 2. 文献编号正序连续
    ref_nums = []
    if refs is None:
        report["notes"].append("未找到「参考文献」段：跳过文献校验（若本稿应含参考文献，请检查标题写法）")
    else:
        ref_nums = parse_ref_numbers(refs)
        if not ref_nums:
            report["problems"].append("参考文献段存在但没有解析到 [n] 编号条目")
        else:
            expect = list(range(1, len(ref_nums) + 1))
            if ref_nums != expect:
                report["problems"].append(f"文献编号非 1→N 正序连续: 实为 {ref_nums}")

    # 3. 正文锚点 ⊆ 文献表 + 编号是否按正文首次引用顺序
    cited_order = []
    for m in re.finditer(r"\[(\d+)\]", body):
        n = int(m.group(1))
        if n not in cited_order:
            cited_order.append(n)
    cited = sorted(set(cited_order))
    if ref_nums and cited_order and cited_order != ref_nums:
        report["problems"].append(
            f"文献编号未按正文首次引用顺序排列（规则: 按出现顺序编号、中英混排）: 正文顺序 {cited_order} vs 文献表 {ref_nums}")
    if ref_nums:
        ghost = [c for c in cited if c not in ref_nums]
        unused = [n for n in ref_nums if n not in cited]
        if ghost:
            report["problems"].append(f"正文引用了文献表不存在的编号: {ghost}")
        if unused:
            report["notes"].append(f"文献表列出但正文未引用: {unused}（建议删除或补引）")
    report["cited"] = cited
    report["ref_nums"] = ref_nums

    # 4. 匿名合规
    if args.anonymous:
        hits = []
        for pat, desc in PII_PATTERNS:
            for m in re.finditer(pat, text):
                frag = m.group(0).strip()
                if desc == "疑似单位名称" and frag in ("大学", "学院"):
                    continue
                hits.append(f"{desc}: 「{frag}」")
        if hits:
            report["problems"].append("匿名合规可疑项（请人工确认删除）: " + "; ".join(sorted(set(hits))[:12]))

    # 5. 禁词
    found = []
    for w in BANNED:
        c = text.count(w)
        if c:
            found.append(f"{w}×{c}")
    for pat, desc in BANNED_PATTERNS:
        n = len(re.findall(pat, text))
        if n:
            found.append(f"{desc}×{n}")
    if found:
        report["notes"].append("禁词/句式命中（AI 腔或学生腔，建议改写）: " + "; ".join(found))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"== 回检: {os.path.basename(args.file)} ==")
        print(f"字数: 中文字符 {cjk} / 含标点 {total}")
        print(f"文献: 表内 {len(ref_nums)} 条 / 正文引用 {len(cited)} 个编号")
        print(f"\n问题 {len(report['problems'])} 项:")
        for x in report["problems"]:
            print("  ✗ " + x)
        if not report["problems"]:
            print("  （无）")
        print(f"\n提示 {len(report['notes'])} 项:")
        for x in report["notes"]:
            print("  · " + x)

    sys.exit(1 if report["problems"] else 0)


if __name__ == "__main__":
    main()
