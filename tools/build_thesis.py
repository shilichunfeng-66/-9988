#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 md 源生成符合《本科毕业论文体例规范》的 docx。

用法
----
    python tools/build_thesis.py 源文件.md 输出.docx
    python tools/build_thesis.py 源文件.md 输出.docx --header "池州学院本科毕业论文"

源文件标记（md 子集）
--------------------
    %TITLE% 论文题目        ← 封面标题（黑体二号居中）
    %SUB%   署名行           ← 封面副行（楷体三号居中）
    %TOC%                    ← 占位，构建器自动在此节插入 TOC 域
    # 一级标题  /  ## 二级  /  ### 三级   ← 走 Heading 1/2/3 样式，目录域据此抓取
    %TCAP%  表1　表题        ← 表题（表上方，五号加粗居中）
    %TWIDTH% 16|42|42        ← 列宽百分比（不均等列宽时必写，避免长文字折行）
    %TABLE% 单元格 | 单元格   ← 表格行（首次出现建表，首行为表头）
    %TNOTE% 注：数据来源…     ← 表注（表下方，小五）
    **关键词**：…             ← 加粗标签段
    [1] …                    ← 参考文献条目（自动用小五、无缩进）

产出结构：封面（无页眉页脚） / 目录（页眉，无页码） / 摘要→附录（页眉 + 页脚「- n -」，页码从 1 起）。
体例参数见 reference-db/格式参考/本科毕业论文体例规范.md。
"""
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

DEFAULT_HEADER = "池州学院本科毕业论文"
PAGE_BREAK_BEFORE = {"Abstract", "1 绪论", "参考文献", "摘要"}

BODY_EA, BODY_SIZE = "宋体", 12
HEAD = {
    1: dict(size=15, align=WD_ALIGN_PARAGRAPH.CENTER, before=18, after=12),
    2: dict(size=14, align=WD_ALIGN_PARAGRAPH.LEFT, before=12, after=6),
    3: dict(size=12, align=WD_ALIGN_PARAGRAPH.LEFT, before=8, after=6),
}


def w(tag, **attrs):
    el = OxmlElement("w:" + tag)
    for k, v in attrs.items():
        el.set(qn(k if ":" in k else "w:" + k), v)
    return el


def set_font(run, ea, size, bold=False, latin="Times New Roman"):
    run.font.name = latin
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), ea)


def set_indent(p, chars=200, pt=24):
    pPr = p._p.get_or_add_pPr()
    ind = pPr.find(qn("w:ind"))
    if ind is None:
        ind = w("ind")
        pPr.append(ind)
    ind.set(qn("w:firstLineChars"), str(chars))
    ind.set(qn("w:firstLine"), str(int(Pt(pt).twips)))


def add_field(p, instr, placeholder):
    r = p.add_run()
    r._r.append(w("fldChar", fldCharType="begin"))
    it = w("instrText", **{"xml:space": "preserve"})
    it.text = instr
    r._r.append(it)
    r._r.append(w("fldChar", fldCharType="separate"))
    t = w("t")
    t.text = placeholder
    r._r.append(t)
    r._r.append(w("fldChar", fldCharType="end"))
    return r


def _insert_bordered(tblPr, el, before_tags=("w:tblLook", "w:tblLayout", "w:tblCellMar")):
    """按 CT_TblPr 的元素顺序把 tblBorders 插到正确位置（否则 Word 可能报错）。"""
    for tag in before_tags:
        anchor = tblPr.find(qn(tag))
        if anchor is not None:
            anchor.addprevious(el)
            return
    tblPr.append(el)


def set_col_widths(table, widths, total_cm=14.66):
    """按百分比设列宽（三线表列宽不均等时用）。"""
    table.autofit = False
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblLayout")):
        tblPr.remove(old)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    _insert_bordered(tblPr, layout, before_tags=("w:tblCellMar", "w:tblLook"))
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if i < len(widths):
                cell.width = Cm(total_cm * widths[i] / 100.0)


def three_line(table, header_rows=1):
    """论文三线表：顶线 1.5pt、表头下线 0.75pt、底线 1.5pt，无竖线、无内部横线。"""
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:" + edge)
        if edge in ("top", "bottom"):
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "12")          # 1.5pt = 12/8 pt
        else:
            el.set(qn("w:val"), "none")
            el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    _insert_bordered(tblPr, borders)

    if not header_rows or len(table.rows) < header_rows:
        return
    for cell in table.rows[header_rows - 1].cells:
        tcPr = cell._tc.get_or_add_tcPr()
        for old in tcPr.findall(qn("w:tcBorders")):
            tcPr.remove(old)
        tcb = OxmlElement("w:tcBorders")
        b = OxmlElement("w:bottom")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "6")                # 0.75pt
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "000000")
        tcb.append(b)
        tcPr.append(tcb)


def restart_page_numbering(section, start=1):
    sectPr = section._sectPr
    pg = w("pgNumType", start=str(start))
    anchor = None
    for tag in ("w:cols", "w:docGrid"):
        el = sectPr.find(qn(tag))
        if el is not None:
            anchor = el
            break
    if anchor is not None:
        anchor.addprevious(pg)
    else:
        sectPr.append(pg)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    src_path, out_path = args[0], args[1]
    header_text = DEFAULT_HEADER
    if "--header" in argv:
        header_text = argv[argv.index("--header") + 1]

    doc = Document()

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(BODY_SIZE)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_EA)
    pf = normal.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)

    for lvl in (1, 2, 3):
        try:
            st = doc.styles[f"TOC {lvl}"]
        except KeyError:
            continue
        st.font.name = "Times New Roman"
        st.font.size = Pt(BODY_SIZE)
        st.font.bold = False
        st.font.color.rgb = RGBColor(0, 0, 0)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_EA)
        st.paragraph_format.line_spacing = 1.5
        st.paragraph_format.space_before = Pt(0)
        st.paragraph_format.space_after = Pt(0)

    for lvl, cfg in HEAD.items():
        st = doc.styles[f"Heading {lvl}"]
        st.font.name = "Times New Roman"
        st.font.size = Pt(cfg["size"])
        st.font.bold = True
        st.font.color.rgb = RGBColor(0, 0, 0)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        st.paragraph_format.alignment = cfg["align"]
        st.paragraph_format.space_before = Pt(cfg["before"])
        st.paragraph_format.space_after = Pt(cfg["after"])
        st.paragraph_format.line_spacing = 1.5

    for s in doc.sections:
        s.page_width, s.page_height = Cm(21), Cm(29.7)
        s.top_margin = s.bottom_margin = Cm(2.54)
        s.left_margin = s.right_margin = Cm(3.17)

    src = open(src_path, encoding="utf-8").read().split("\n")
    title = src[0].replace("%TITLE%", "").strip()
    subtitle = src[1].replace("%SUB%", "").strip()

    # ---------- 封面 ----------
    cover = doc.sections[0]
    cover.header.is_linked_to_previous = False
    for _ in range(6):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(p.add_run(title), "黑体", 22, bold=True)
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(p.add_run(subtitle), "楷体", 14)

    # ---------- 目录（新节） ----------
    sec2 = doc.add_section(WD_SECTION.NEW_PAGE)
    sec2.header.is_linked_to_previous = False
    sec2.footer.is_linked_to_previous = False
    hp = sec2.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(hp.add_run(header_text), "宋体", 10.5)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(18)
    set_font(p.add_run("目　录"), "黑体", 16, bold=True)
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.5
    set_font(add_field(p, ' TOC \\o "1-3" \\h \\z \\u ', "（目录域：打开后按 Ctrl+A 再按 F9 更新）"), BODY_EA, BODY_SIZE)

    # ---------- 正文（新节，页码从 1 起） ----------
    sec3 = doc.add_section(WD_SECTION.NEW_PAGE)
    sec3.header.is_linked_to_previous = False
    sec3.footer.is_linked_to_previous = False
    hp = sec3.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(hp.add_run(header_text), "宋体", 10.5)
    fp = sec3.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(fp.add_run("- "), "宋体", 10.5)
    set_font(add_field(fp, " PAGE ", "1"), "宋体", 10.5)
    set_font(fp.add_run(" -"), "宋体", 10.5)
    restart_page_numbering(sec3, 1)

    def add_body(text, size=BODY_SIZE, indent=True, align=None):
        par = doc.add_paragraph()
        if align is not None:
            par.alignment = align
        if indent:
            set_indent(par)
        set_font(par.add_run(text), BODY_EA, size)
        return par

    pending_widths = None
    pending_table = None
    for raw in src[2:]:
        ln = raw.strip()
        if not ln or ln.startswith("%TITLE%") or ln.startswith("%SUB%") or ln.startswith("%TOC%"):
            continue
        if ln.startswith("### "):
            pending_table = None
            doc.add_paragraph(ln[4:], style="Heading 3")
            continue
        if ln.startswith("## "):
            pending_table = None
            doc.add_paragraph(ln[3:], style="Heading 2")
            continue
        if ln.startswith("# "):
            pending_table = None
            h = doc.add_paragraph(ln[2:], style="Heading 1")
            if ln[2:].strip() in PAGE_BREAK_BEFORE:      # 中英文摘要/正文/参考文献各自另页
                h.paragraph_format.page_break_before = True
            continue
        if ln.startswith("%TWIDTH%"):
            pending_widths = [float(x) for x in ln.replace("%TWIDTH%", "").split("|")]
            continue
        if ln.startswith("%TCAP%"):
            pending_table = None
            cap = doc.add_paragraph()
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.paragraph_format.space_before = Pt(8)
            cap.paragraph_format.space_after = Pt(3)
            cap.paragraph_format.line_spacing = 1.15
            set_font(cap.add_run(ln.replace("%TCAP%", "").strip()), BODY_EA, 10.5, bold=True)
            continue
        if ln.startswith("%TNOTE%"):
            pending_table = None
            note = doc.add_paragraph()
            note.paragraph_format.space_before = Pt(3)
            note.paragraph_format.space_after = Pt(10)
            note.paragraph_format.line_spacing = 1.15
            set_font(note.add_run(ln.replace("%TNOTE%", "").strip()), BODY_EA, 9)
            continue
        if ln.startswith("%TABLE%"):
            cells = [c.strip() for c in ln.replace("%TABLE%", "").split("|")]
            if pending_table is None:
                pending_table = doc.add_table(rows=0, cols=len(cells))
                pending_table.alignment = WD_TABLE_ALIGNMENT.CENTER
                pending_table.autofit = True
                three_line(pending_table, header_rows=0)   # 先上顶线底线
            row = pending_table.add_row()
            for i, c in enumerate(cells):
                cell_p = row.cells[i].paragraphs[0]
                cell_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cell_p.paragraph_format.line_spacing = 1.15
                cell_p.paragraph_format.space_before = Pt(2)
                cell_p.paragraph_format.space_after = Pt(2)
                first = len(pending_table.rows) == 1
                set_font(cell_p.add_run(c), BODY_EA, 10.5, bold=first)
            if len(pending_table.rows) == 1:
                three_line(pending_table)          # 补表头下线
                if pending_widths:
                    set_col_widths(pending_table, pending_widths)
            continue
        pending_table = None
        if ln.startswith("%NOTE%"):
            add_body(ln.replace("%NOTE%", "").strip(), size=10.5)
            continue
        if ln.startswith("**"):
            m = re.match(r"\*\*(.+?)\*\*(.*)", ln)
            par = doc.add_paragraph()
            set_font(par.add_run(m.group(1)), BODY_EA, BODY_SIZE, bold=True)
            set_font(par.add_run(m.group(2)), BODY_EA, BODY_SIZE)
            continue
        if re.match(r"^\[\d+\]", ln):
            par = doc.add_paragraph()
            set_font(par.add_run(ln), BODY_EA, 10.5)
            continue
        add_body(ln)

    uf = w("updateFields", val="true")
    doc.settings.element.insert(0, uf)
    doc.save(out_path)
    print("已生成", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
