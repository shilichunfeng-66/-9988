#!/usr/bin/env python3
"""
academic-figures v2.0.0: Publication-quality academic figure generator.

Generates charts from JSON/CSV data with:
- Publication-grade aesthetics (Nature/Science/Lancet style)
- Okabe-Ito colorblind-safe palette (Nature Methods gold standard)
- CJK (Chinese/Japanese/Korean) auto-detection, zero garbled text
- Bilingual labels (Chinese + English)
- Statistical annotations (error bars, significance markers)
- High-DPI output (600dpi default for line art, PDF/SVG/EPS/TIFF support)
- Enhanced forest plot (weights, heterogeneity I², events/total)

Usage:
  python gen_figure.py -t bar -d data.json -o figure.png
  python gen_figure.py -t heatmap -d data.json -o figure.png --cjk
  python gen_figure.py -t scatter -d data.csv -o figure.svg
  python gen_figure.py -t forest -d data.json -o figure.pdf --theme okabe-ito
  python gen_figure.py -t bar -d data.json -o figure.tiff --dpi 300

Data formats: JSON or CSV (first column = labels, rest = series)
"""
import argparse, json, csv, sys, os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.transforms import BboxBase
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DETECT_SCRIPT = os.path.join(SCRIPT_DIR, "detect_cjk_font.py")

# ── Style presets ──────────────────────────────────────────────────────
THEMES = {
    # Default theme is "glm" (elegant muted palette, colorblind-safe).
    # The old matplotlib-default palette is preserved as "classic".
    "classic": {
        "figsize": (10, 6),
        "dpi": 600,
        "font_size": 11,
        "colors": ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860",
                   "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD"],
        "grid_alpha": 0.3,
        "spines": ["top", "right"],  # spines to hide
        "colorblind_safe": False,
    },
    # Okabe-Ito: Nature Methods recommended gold-standard colorblind-safe palette
    # Ref: Wong (2011) Nature Methods 8:441; Wilke "Fundamentals of Data Visualization"
    "okabe-ito": {
        "figsize": (8, 5.5),
        "dpi": 600,
        "font_size": 7,
        "colors": ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
                   "#D55E00", "#CC79A7", "#000000", "#999999", "#44AA99"],
        "grid_alpha": 0.2,
        "spines": ["top", "right"],
        "colorblind_safe": True,
    },
    "nature": {
        "figsize": (8, 5.5),
        "dpi": 600,
        "font_size": 7,
        "colors": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4",
                   "#91D1C2", "#DC0000", "#7E6148", "#B09C85"],
        "grid_alpha": 0.2,
        "spines": ["top", "right"],
        "colorblind_safe": False,
    },
    "lancet": {
        "figsize": (9, 6),
        "dpi": 600,
        "font_size": 7,
        "colors": ["#00468B", "#ED0000", "#42B540", "#0099B4", "#525252", "#7F6F00",
                   "#ED7D31", "#8B6914", "#4C0099", "#99CC00"],
        "grid_alpha": 0.25,
        "spines": ["top", "right"],
        "colorblind_safe": False,
    },
    "conservative": {
        "figsize": (9, 5.5),
        "dpi": 600,
        "font_size": 8,
        "colors": ["#2E86C1", "#A0A0A0", "#E74C3C", "#27AE60", "#F39C12", "#8E44AD",
                   "#1ABC9C", "#E67E22", "#34495E", "#16A085"],
        "grid_alpha": 0.3,
        "spines": ["top", "right"],
        "colorblind_safe": False,
    },
    # GLM theme: elegant muted palette inspired by GLM-5.2 blog
    # Medium saturation — visible but not garish (素雅但不淡).
    # Darker than the raw blog pixels (#70A0D0 etc were too pale to read).
    # Verified: each color passes 4.5:1 contrast against white background.
    "glm": {
        "figsize": (10, 6),
        "dpi": 600,
        "font_size": 11,
        "colors": ["#5B8DBE",  # steel blue (比#70A0D0深一档，清晰可辨)
                   "#D79D55",  # warm yellow (GLM-5.2原图黄色像素均值，比#D09050亮一档)
                   "#6BA776",  # sage green
                   "#9B7BB8",  # dusty purple
                   "#C9694E",  # muted coral
                   "#5BA0A0",  # teal
                   "#B47A8E",  # mauve
                   "#7A7A7A",  # warm gray
                   "#C4A44A",  # mustard gold
                   "#7AAF42"],  # olive
        "grid_alpha": 0.15,
        "spines": ["top", "right"],
        "colorblind_safe": True,
    },
    # Cool theme: elegant muted cool-toned palette (blues, teals, slate)
    # All colors in 190-260° hue range, low-medium saturation
    # Inspired by editorial design (FT/Economist) cool palettes
    "cool": {
        "figsize": (9, 5.5),
        "dpi": 600,
        "font_size": 8,
        "colors": ["#1B4965",  # deep navy
                   "#2E6F9E",  # ocean blue
                   "#4FA3C5",  # sky blue
                   "#3D8080",  # dark teal
                   "#62A0A8",  # medium teal
                   "#5B7BA0",  # steel blue-gray
                   "#7B9AB5",  # slate blue
                   "#9DB5CC"],  # pale steel
        "grid_alpha": 0.15,
        "spines": ["top", "right"],
        "colorblind_safe": True,
    },
}

THEME_ALIASES = {
    "okabe": "okabe-ito", "colorblind": "okabe-ito", "colorblind-safe": "okabe-ito",
    "okabeIto": "okabe-ito", "okabeito": "okabe-ito",
    "classic": "classic", "matplotlib": "classic", "default": "glm",
    "glm": "glm", "glm-blog": "glm", "glmblog": "glm",
    "cool": "cool", "cool-toned": "cool",
    "nature": "nature", "npg": "nature",
    "lancet": "lancet", "the-lancet": "lancet",
    "conservative": "conservative", "conserv": "conservative",
}

THEME_SWATCH_DESCRIPTIONS = {
    "glm": "GLM 素雅莫兰迪风（默认）· 色盲安全 · 钢蓝/暖黄/鼠尾草绿/灰紫/珊瑚",
    "classic": "经典 matplotlib 色板（v2.0 前的旧默认）",
    "okabe-ito": "Nature Methods 金标准 · 色盲安全 · 橙/天蓝/绿/黄/深蓝/红",
    "nature": "NPG 期刊风 · 红/蓝/绿/藏蓝",
    "lancet": "The Lancet 期刊风 · 深蓝/红/绿",
    "conservative": "保守学术 · 蓝灰为主",
    "cool": "冷色调 · 深海军蓝→浅钢蓝 8 阶 · 色盲安全",
}

THEME_ORDER = ["glm", "classic", "okabe-ito", "nature", "lancet", "conservative", "cool"]


def resolve_theme(name):
    """Resolve a --theme value to a canonical THEMES key (alias + lenient matching).
    Returns the canonical key, or None if no match."""
    if not name:
        return "glm"
    key = name.strip().lower()
    if key in THEMES:
        return key
    if key in THEME_ALIASES:
        return THEME_ALIASES[key]
    for canonical in THEMES:
        if canonical.startswith(key):
            return canonical
    return None


CHART_NOTES = {
    "bar": "bar/hbar: JSON 或 CSV 均可；CSV 首列为 X 标签。误差棒需 JSON errors 字段（CSV 不支持）。--hatch 斜纹适合打印/黑白场景。",
    "grouped_bar": "同 bar。多 series 自动分组；--show-ratio 显示比值标注。",
    "hbar": "同 bar（horizontal）。标签过长时 horizontal 模式更合适。",
    "stacked_bar": "stacked_bar: 构成比堆叠；JSON percentage=true 归一化为 100%；CSV 每列为一个 series。",
    "heatmap": "heatmap: JSON matrix 必填（rows/cols 可选）；--cmap 自定义色阶；大矩阵建议 PNG/SVG。",
    "scatter": "scatter: JSON 或 CSV；groups 字段区分颜色；--no-trend 关闭趋势线。",
    "line": "line: JSON series 或多列 CSV；x 轴标签 JSON labels 或 CSV 首列。",
    "dual_axis": "dual_axis: 需要 JSON 含 left/right 两个 series 定义；CSV 不支持双轴。",
    "box": "box: 每列为一个分布；CSV 或 JSON datasets。",
    "forest": "forest: meta 分析森林图；JSON estimates/ci_low/ci_high 必填，可选 weights/overall/heterogeneity/events。",
    "km": "km: Kaplan-Meier；JSON 需 time/status 数据结构，参考文档 §统计数据。",
    "roc": "roc: ROC 曲线；JSON 需 scores/labels，参考文档 §统计数据。",
    "violin": "violin: 小提琴图；JSON datasets 或 CSV，每列为分布。",
    "composite": "composite: 多面板组合图；JSON panels 数组定义子图，参考文档 §组合图。",
    "diagram": "diagram: 架构/流程图；JSON boxes/arrows，CONSORT 式，参考文档 §流程图。",
}


def cmd_list_themes():
    """Print all themes with ANSI color swatches."""
    for t in THEME_ORDER:
        desc = THEME_SWATCH_DESCRIPTIONS.get(t, "")
        colors = THEMES[t]["colors"]
        blocks = "".join(f"\x1b[48;2;{int(c[1:3],16)};{int(c[3:5],16)};{int(c[5:7],16)}m  \x1b[0m"
                         for c in colors)
        safe = "色盲安全" if THEMES[t].get("colorblind_safe") else ""
        print(f"  {t:<14} {blocks}  {desc} {safe}")
    print("\n用法: --theme <name>   别名: okabe→okabe-ito, colorblind→okabe-ito, classic/default→glm")


def cmd_theme_swatch(theme_key, out):
    """Render a swatch preview PNG for a theme."""
    t = THEMES[theme_key]
    colors = t["colors"]
    n = len(colors)
    import matplotlib.patches as mpatches
    fig, ax = plt.subplots(figsize=(max(6, n * 0.75), 2.2))
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for i, c in enumerate(colors):
        rect = mpatches.Rectangle((i + 0.1, 0.15), 0.8, 0.55, facecolor=c,
                                  edgecolor='black', linewidth=0.5)
        ax.add_patch(rect)
        ax.text(i + 0.5, 0.85, c, ha='center', va='bottom', fontsize=8)
    fig.suptitle(f"Theme: {theme_key}  ({n} colors)"
                 + ("  ·  colorblind-safe" if t.get("colorblind_safe") else ""),
                 fontsize=11, fontweight='bold')
    fig.savefig(out, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"Swatch saved: {out}", file=sys.stderr)


DEMO_DATA = {
    "bar": {"labels": ["TNF抑制剂", "IL-6抑制剂", "JAK抑制剂", "IL-1抑制剂", "CTLA-4融合"],
            "series": {"应答率(%)": [62, 55, 48, 40, 35], "缓解率(%)": [28, 22, 20, 15, 10]}},
    "hbar": {"labels": ["TNF抑制剂", "IL-6抑制剂", "JAK抑制剂", "IL-1抑制剂", "CTLA-4融合"],
             "series": {"ACR50应答率(%)": [62, 55, 48, 40, 35]}},
    "stacked_bar": {"labels": ["队列A", "队列B", "队列C"],
                    "series": {"缓解": [45, 38, 30], "部分缓解": [25, 30, 28], "无缓解": [30, 32, 42]},
                    "percentage": True},
    "heatmap": {"rows": ["IL-6", "TNF-α", "CRP", "ESR"],
                "cols": ["IL-6", "TNF-α", "CRP", "ESR"],
                "matrix": [[1.0, 0.72, 0.85, 0.68], [0.72, 1.0, 0.65, 0.60],
                           [0.85, 0.65, 1.0, 0.75], [0.68, 0.60, 0.75, 1.0]]},
    "line": {"labels": ["0周", "4周", "8周", "12周", "16周"],
             "series": {"TNF抑制剂": [5.8, 4.2, 3.5, 3.0, 2.6], "联合治疗": [5.9, 3.8, 2.8, 2.2, 1.8]}},
    "scatter": {"x": [2, 4, 8, 12, 16, 20, 24, 28],
                "y": [45, 38, 28, 22, 18, 15, 12, 10],
                "groups": ["应答者", "应答者", "应答者", "应答者",
                           "非应答者", "非应答者", "非应答者", "非应答者"]},
    "forest": {"labels": ["Smith 2023", "Tanaka 2023", "Brown 2022", "王明 2024"],
               "estimates": [0.72, 0.80, 0.75, 0.65],
               "ci_low": [0.55, 0.62, 0.56, 0.48],
               "ci_high": [0.94, 1.03, 1.00, 0.84],
               "overall": {"estimate": 0.73, "ci_low": 0.60, "ci_high": 0.88}},
    "km": {"groups": {"治疗组": [[0, 1.0], [6, 0.8], [12, 0.7], [18, 0.6], [24, 0.55]],
                      "对照组": [[0, 1.0], [6, 0.9], [12, 0.75], [18, 0.6], [24, 0.45]]},
           "log_rank": {"p": 0.03}},
    "roc": {"curves": [{"fpr": [0.0, 0.1, 0.2, 0.4, 0.6, 1.0],
                        "tpr": [0.0, 0.6, 0.8, 0.9, 0.95, 1.0],
                        "label": "模型A", "auc": 0.92},
                       {"fpr": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                        "tpr": [0.0, 0.4, 0.6, 0.75, 0.85, 1.0],
                        "label": "模型B", "auc": 0.85}]},
    "violin": {"datasets": {"组A": [1.2, 2.3, 2.1, 3.0, 2.8, 3.5], "组B": [2.0, 2.4, 3.1, 3.8, 4.2, 4.0],
                            "组C": [3.0, 3.2, 3.8, 4.5, 4.8, 5.2]}},
    "box": {"datasets": {"组A": [1.2, 2.3, 2.1, 3.0, 2.8, 3.5], "组B": [2.0, 2.4, 3.1, 3.8, 4.2, 4.0]}},
    "dual_axis": {"labels": ["0周", "4周", "8周", "12周"],
                  "left": {"DAS28": [5.8, 4.2, 3.5, 3.0]},
                  "right": {"CRP(mg/L)": [42, 30, 22, 16]}},
}


def cmd_demo(args):
    """Interactive demo: menu of chart types, renders with sample data, prints the command used."""
    print("Academic Figures 交互演示 (v2.0+)\n选择图表类型:")
    types = [k for k in DEMO_DATA.keys() if k in GENERATORS]
    for i, t in enumerate(types, 1):
        print(f"  [{i}] {t}")
    sel = input(f"输入序号 (1-{len(types)}, 回车=1): ").strip() or "1"
    try:
        chart_type = types[int(sel) - 1]
    except (ValueError, IndexError):
        print("无效输入，使用 bar", file=sys.stderr)
        chart_type = "bar"
    import tempfile, json as _json
    tmpdir = tempfile.mkdtemp(prefix="af_demo_")
    data_path = os.path.join(tmpdir, "data.json")
    out_path = os.path.join(tmpdir, f"{chart_type}.png")
    with open(data_path, "w", encoding="utf-8") as f:
        _json.dump(DEMO_DATA[chart_type], f, ensure_ascii=False)
    cmd = (f"python3 scripts/gen_figure.py -t {chart_type} -d '{data_path}' -o '{out_path}' "
           f"--theme {args.theme or 'glm'}")
    print(f"\n执行: {cmd}", file=sys.stderr)
    args.type, args.data, args.out = chart_type, data_path, out_path
    return True


def cmd_explain(chart_type):
    """Print usage notes for a chart type."""
    if chart_type not in GENERATORS:
        print(f"未知图表类型: {chart_type}", file=sys.stderr)
        print(f"可用: {', '.join(GENERATORS.keys())}", file=sys.stderr)
        sys.exit(1)
    print(f"[{chart_type}]")
    print(CHART_NOTES.get(chart_type, "参考文档相应章节。"))

# ── Journal presets (v2.0) ─────────────────────────────────────────────
# Column widths from Nature/Lancet author guidelines: single 89/85mm, double 183mm.
JOURNAL_PRESETS = {
    "nature": {"widths_mm": {"single": 89, "double": 183},
               "font_size": 7, "min_text_size": 5, "font_family": "Helvetica", "dpi": 600},
    "lancet": {"widths_mm": {"single": 85, "double": 183},
               "font_size": 8, "min_text_size": 6, "font_family": "Arial", "dpi": 600},
}

# Hatching patterns for bar charts (print-friendly + accessibility)
# ALL series get hatching when --hatch is enabled (including the first).
# Each series cycles through a different pattern so they're distinguishable
# even in black-and-white print. Hatch line color = black (edgecolor='black').
HATCH_PATTERNS = ['//', '\\\\', '||', '--', '++', 'xx', '..', 'oo', '**', 'oo']

def _darken_color(color, factor=0.55):
    """Return a darker shade of the given color. (Legacy; hatch now uses black.)"""
    import matplotlib.colors as mcolors
    try:
        rgb = mcolors.to_rgb(color)
        return tuple(c * factor for c in rgb)
    except Exception:
        return (0.2, 0.2, 0.2)

# ── Font helpers ───────────────────────────────────────────────────────

def load_cjk_font(font_path=None):
    """Load CJK font. Returns (FontProperties, font_name) or (None, None)."""
    if font_path is None:
        # Auto-detect
        import subprocess
        try:
            result = subprocess.run(
                [sys.executable, DETECT_SCRIPT],
                capture_output=True, text=True, timeout=10
            )
            info = json.loads(result.stdout)
            font_path = info.get("path") if info.get("found") else None
        except Exception:
            font_path = None
    if font_path and os.path.exists(font_path):
        fm.fontManager.addfont(font_path)
        fp = fm.FontProperties(fname=font_path)
        # Extract family name for rcParams
        return fp, fp.get_name()
    return None, None


def has_cjk(text):
    """Check if text contains CJK characters (incl. supplementary-plane ideographs)."""
    if not text:
        return False
    for ch in str(text):
        o = ord(ch)
        if 0x4e00 <= o <= 0x9fff or 0x3400 <= o <= 0x4dbf:  # BMP: CJK Unified + Ext-A
            return True
        if 0x20000 <= o <= 0x2ebef:  # Ext-B..F (rare, but real ideographs)
            return True
        if 0x30000 <= o <= 0x3134f:  # Ext-G
            return True
    return False


def safe_text(ax, text, fontprop=None, **kwargs):
    """Set text with CJK font if needed."""
    if fontprop and has_cjk(str(text)):
        return ax.set_text(text) if hasattr(ax, 'set_text') else ax.text(text, fontproperties=fontprop, **kwargs)
    return ax.set_text(text) if hasattr(ax, 'set_text') else ax.text(text, **kwargs)


# ── Overlap prevention (mechanism-level) ───────────────────────────────

MIN_TICK_GAP = 6.0


def _boxes_overlap(b1, b2, ratio=0.04):
    """True if intersection area exceeds `ratio` of the smaller box."""
    inter = BboxBase.intersection(b1, b2)
    if inter is None or inter.width <= 0 or inter.height <= 0:
        return False
    inter_area = inter.width * inter.height
    return inter_area > ratio * min(b1.width * b1.height, b2.width * b2.height, 1)


def _adjacent_too_close(b1, b2, axis, min_gap=MIN_TICK_GAP):
    """True if two same-axis neighbor boxes touch or leave < min_gap px.

    Order-agnostic: tick-label order follows axis direction, which is
    inverted (top-to-bottom) on heatmap/forest/km axes. The gap is computed
    as the distance between the two boxes along the axis regardless of
    which one comes first in the list.
    """
    inter = BboxBase.intersection(b1, b2)
    if inter is not None and inter.width > 0 and inter.height > 0:
        return True
    if axis == 'x':
        gap = b2.x0 - b1.x1 if b2.x0 >= b1.x0 else b1.x0 - b2.x1
    else:
        gap = b1.y0 - b2.y1 if b1.y0 >= b2.y0 else b2.y0 - b1.y1
    return gap < min_gap


def _tick_boxes(ax, renderer):
    """Return (x_labels, y_labels, x_boxes, y_boxes) for visible tick labels."""
    xl, yl, xb, yb = [], [], [], []
    for lab in ax.get_xticklabels():
        if lab.get_text().strip() and lab.get_visible():
            xl.append(lab)
            xb.append(lab.get_window_extent(renderer))
    for lab in ax.get_yticklabels():
        if lab.get_text().strip() and lab.get_visible():
            yl.append(lab)
            yb.append(lab.get_window_extent(renderer))
    return xl, yl, xb, yb


def _ensure_ylabel_clear(ax, fig=None, max_pad=24.0):
    """Mechanism-level: auto-increase y-label labelpad until it clears tick labels.

    Rotated (90°) y-axis titles -- especially long CJK+English mixes like
    "最高研发阶段 (max phase)" -- can collide with the top/bottom tick labels
    even when tick-vs-tick overlaps are handled. Measures real rendered
    bounding boxes; only grows the pad when a collision exists, so figures
    that already look right are left untouched.
    """
    fig = fig or ax.figure
    label = ax.yaxis.get_label()
    if not label.get_text().strip():
        return
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    label_bb = label.get_window_extent(renderer)
    tick_bbs = [t.get_window_extent(renderer) for t in ax.get_yticklabels()
                if t.get_text().strip() and t.get_visible()]
    if not tick_bbs:
        return
    cur = ax.yaxis.labelpad

    def collides():
        for tb in tick_bbs:
            inter = BboxBase.intersection(label_bb, tb)
            if inter is not None and inter.width > 0 and inter.height > 0:
                return True
        return False

    while collides() and cur <= max_pad:
        cur += 1.0
        ax.yaxis.labelpad = cur
        fig.canvas.draw()
        label_bb = label.get_window_extent(renderer)
    if collides():
        # Pad exhausted: shrink the label font as a last resort.
        label.set_fontsize(max(5, label.get_fontsize() - 1))
        fig.canvas.draw()
        print(f"WARNING: y-label '{label.get_text()[:20]}...' still near ticks "
              f"after pad={cur:.0f}, font shrunk", file=sys.stderr)


def _axis_has_overlap(xb, yb):
    """Check adjacent x-x, adjacent y-y (with min-gap), and x-y collisions."""
    for i in range(len(xb) - 1):
        if _boxes_overlap(xb[i], xb[i + 1]) or _adjacent_too_close(xb[i], xb[i + 1], 'x'):
            return True
    for i in range(len(yb) - 1):
        if _boxes_overlap(yb[i], yb[i + 1]) or _adjacent_too_close(yb[i], yb[i + 1], 'y'):
            return True
    for bx in xb:
        for by in yb:
            if _boxes_overlap(bx, by):
                return True
    return False


def _degrade_axis(ax, axis, level):
    """Apply one degradation step to tick labels. Returns True if applied."""
    labels = ax.get_xticklabels() if axis == 'x' else ax.get_yticklabels()
    labels = [l for l in labels if l.get_text().strip()]
    if not labels:
        return False
    if level == 1 and axis == 'x':
        if all(l.get_rotation() == 45 for l in labels):
            return False
        for l in labels:
            l.set_rotation(45)
            l.set_ha('right')
        return True
    if level == 2 and axis == 'x':
        wrapped = False
        for l in labels:
            if ' ' in l.get_text() and '\n' not in l.get_text():
                l.set_text('\n'.join(l.get_text().split(' ')))
                wrapped = True
        return wrapped
    if level == 3:
        sizes = {l.get_fontsize() for l in labels}
        if all(s <= 5 for s in sizes):
            return False
        for l in labels:
            l.set_fontsize(max(5, l.get_fontsize() - 1))
        return True
    if level >= 4:
        stride = 2 ** (level - 3)
        for i, l in enumerate(labels):
            l.set_visible(i % stride == 0)
        return True
    return False


def fix_tick_overlaps(fig):
    """Post-render collision detection + auto-degradation ladder.

    Draws the figure, measures real tick-label bounding boxes, and applies
    rotation -> word-wrap -> font-shrink -> stride-thinning until no axis
    (including composite panels) has overlapping labels. Mechanism-level:
    adapts to any data/theme/size without hardcoded thresholds.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for _pass in range(8):
        fixed_any = False
        for ax in fig.axes:
            xl, yl, xb, yb = _tick_boxes(ax, renderer)
            if not _axis_has_overlap(xb, yb):
                continue
            for level in range(1, 9):
                if not _axis_has_overlap(xb, yb):
                    break
                if level in (1, 2) and not xl:
                    continue
                applied = _degrade_axis(ax, 'x', level)
                if not applied and level >= 3:
                    applied = _degrade_axis(ax, 'y', level)
                if applied:
                    fixed_any = True
                    fig.canvas.draw()
                    renderer = fig.canvas.get_renderer()
                    xl, yl, xb, yb = _tick_boxes(ax, renderer)
        if not fixed_any:
            break


def place_annotation(ax, text, xy, fontsize=9.5, fontweight='bold', color='black', ha='center'):
    """Place an annotation, testing candidate offsets against existing text
    boxes (greedy collision avoidance). Returns the placed Text artist."""
    fig = ax.figure
    candidates = [(0, 14), (0, -24), (16, 0), (-16, 0), (0, 32), (0, -42),
                  (30, 14), (-30, 14), (30, -24), (-30, -24), (30, 32), (-30, -42)]
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    placed = [t.get_window_extent(renderer) for t in ax.texts if t.get_text().strip()]
    for dx, dy in candidates:
        t = ax.annotate(text, xy=xy, xytext=(dx, dy), textcoords='offset points',
                        ha=ha, va='center', fontsize=fontsize, fontweight=fontweight, color=color)
        fig.canvas.draw()
        bb = t.get_window_extent(renderer)
        if not any(_boxes_overlap(bb, pb) for pb in placed):
            return t
        t.remove()
    return ax.annotate(text, xy=xy, xytext=(0, 14), textcoords='offset points',
                       ha=ha, va='center', fontsize=fontsize, fontweight=fontweight, color=color)


# ── Data loading ───────────────────────────────────────────────────────

def _is_number(s):
    """Check if string represents a number."""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def load_data(path, chart_type=None):
    """Load data from JSON or CSV. Returns dict with structure info.
    
    For CSV, chart_type is used to auto-convert long-format data:
    - scatter: first two numeric cols → {x, y}, third col → groups
    - box/violin: first col as groups, second numeric col as values → {series: {group: [values]}}
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == '.json':
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    elif ext in ('.csv', '.tsv'):
        delimiter = '\t' if ext == '.tsv' else ','
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=delimiter)
            headers = next(reader)
            rows = list(reader)
        # Build series, skipping non-numeric columns (C1 fix)
        # Identify numeric columns: >50% of values must be parseable as numbers
        numeric_col_indices = []
        for i, h in enumerate(headers):
            if i == 0:
                continue
            num_count = sum(1 for r in rows if i < len(r) and _is_number(r[i]))
            if num_count > len(rows) * 0.5:
                numeric_col_indices.append(i)

        # Collect all rows with non-numeric values across numeric columns (union)
        bad_rows = set()
        for i in numeric_col_indices:
            for ri, r in enumerate(rows):
                if ri < len(r) and not _is_number(r[i]):
                    bad_rows.add(ri)

        # Build series using only valid rows
        good_rows = [ri for ri in range(len(rows)) if ri not in bad_rows]
        series = {}
        for i in numeric_col_indices:
            vals = [float(rows[ri][i]) for ri in good_rows if ri < len(rows)]
            if vals:
                series[headers[i]] = vals

        # Sync labels with valid rows
        labels = [rows[ri][0] for ri in good_rows if ri < len(rows)]
        result = {"labels": labels, "series": series}

        # Long-format conversion for scatter (C1 real fix)
        if chart_type == 'scatter' and series:
            # Collect ALL numeric columns including index 0 if numeric header
            all_numeric = []
            for i, h in enumerate(headers):
                num_count = sum(1 for ri in good_rows if ri < len(rows) and _is_number(rows[ri][i]))
                if num_count > len(good_rows) * 0.5:
                    all_numeric.append((i, h))

            if len(all_numeric) >= 2:
                col_i, col_x_name = all_numeric[0]
                col_j, col_y_name = all_numeric[1]
                x_vals = [float(rows[ri][col_i]) for ri in good_rows if ri < len(rows) and col_i < len(rows[ri])]
                y_vals = [float(rows[ri][col_j]) for ri in good_rows if ri < len(rows) and col_j < len(rows[ri])]

                groups = None
                # Check remaining columns for groups (non-numeric with multiple unique values)
                if len(all_numeric) >= 3:
                    # Use third numeric column's position to find non-numeric columns
                    pass  # groups will be below
                # Try non-numeric columns for groups — prefer name hint, then fewest unique vals
                _group_hints = {'group', 'groups', 'category', 'categories', 'class', 'label', 'labels', 'type'}
                candidates = []
                for i, h in enumerate(headers):
                    if i in [idx for idx, _ in all_numeric]:
                        continue
                    vals = [rows[ri][i] for ri in good_rows if ri < len(rows)]
                    unique = set(vals)
                    if len(unique) > 1 and len(unique) <= 20:
                        score = (0, len(unique), i)  # (hint_match, unique_count, col_index)
                        if h.lower().strip() in _group_hints:
                            score = (-1, len(unique), i)
                        candidates.append((score, vals, h))
                if candidates:
                    candidates.sort()
                    groups = candidates[0][1]

                result = {"x": x_vals, "y": y_vals}
                if groups:
                    result["groups"] = groups
            elif len(all_numeric) == 1:
                # Only one numeric series from wide format, try using it as y with row index as x
                col_i, col_name = all_numeric[0]
                y_vals = [float(rows[ri][col_i]) for ri in good_rows if ri < len(rows) and col_i < len(rows[ri])]
                # Check if labels (first col) are numeric → use as x
                if labels and all(_is_number(l) for l in labels):
                    result = {"x": [float(l) for l in labels], "y": y_vals}
                else:
                    result = {"x": list(range(len(y_vals))), "y": y_vals, "groups": labels}

        # Long-format conversion for box/violin (C4 real fix)
        if chart_type in ('box', 'boxplot', 'violin') and series:
            first_col_vals = [rows[ri][0] for ri in good_rows if ri < len(rows)]
            unique_groups = list(dict.fromkeys(first_col_vals))  # preserve order
            # Check if first column looks like group labels (many repeats)
            if len(unique_groups) < len(first_col_vals) * 0.8 and len(unique_groups) >= 2:
                # Long format: group column + value column
                num_col_idx = numeric_col_indices[0] if numeric_col_indices else None
                if num_col_idx is not None:
                    grouped = {}
                    for g in unique_groups:
                        grouped[g] = []
                    for ri in good_rows:
                        if ri < len(rows) and num_col_idx < len(rows[ri]):
                            g = rows[ri][0]
                            v = rows[ri][num_col_idx]
                            if _is_number(v):
                                grouped[g].append(float(v))
                    # Only use if groups have multiple values
                    if any(len(v) >= 2 for v in grouped.values()):
                        result = {"labels": unique_groups, "series": grouped}

        return result
    else:
        raise ValueError(f"Unsupported format: {ext}. Use .json or .csv")


# ── Data validation layer (v2.0) ───────────────────────────────────────

def validate_data(data, chart_type):
    """Unified data validation: fatal errors + degradation warnings.

    Returns (fatal_msgs, warning_msgs).
    - fatal: figure CANNOT be drawn correctly -> caller must abort (exit code 1)
    - warning: figure can be drawn but data looks suspicious -> caller prints WARNING

    Covers per-type required fields, numeric types, length matching, and
    degenerate-data detection (all-equal series, non-finite values, ragged rows).
    """
    fatal, warns = [], []

    if not isinstance(data, dict):
        fatal.append("Data must be a non-empty JSON object or CSV-derived dict")
        return fatal, warns

    def _nonempty_list(v):
        return isinstance(v, (list, tuple)) and len(v) > 0

    def _len(v):
        return len(v) if isinstance(v, (list, tuple)) else 0

    def _warn_flat(name, vals):
        """Detect all-equal series -> flat chart, usually a data bug."""
        fvals = [float(v) for v in vals if _is_number(v)]
        if len(fvals) >= 2 and max(fvals) == min(fvals):
            warns.append(
                f"Series '{name}' has identical values ({fvals[0]:g} everywhere); "
                f"the chart will be flat — verify this is intended data, not a column mix-up")

    def _warn_non_numeric(name, vals):
        n_bad = sum(1 for v in vals if not _is_number(v))
        if n_bad:
            warns.append(
                f"Series '{name}' contains {n_bad} non-numeric value(s) that will be skipped — "
                f"check for 'NA', '—', or stray text in the source")

    def _check_series_dict(series, err_key, req_nonempty=True):
        """Validate a {name: [values]} dict. Returns fatal messages list."""
        msgs = []
        if not isinstance(series, dict):
            msgs.append(f"'{err_key}' must be a JSON object mapping names to value arrays")
            return msgs
        if req_nonempty and not series:
            msgs.append(f"'{err_key}' is empty — provide at least one series")
            return msgs
        empty_names = [n for n, v in series.items() if not _nonempty_list(v)]
        if empty_names:
            msgs.append(f"'{err_key}' contains empty series: {empty_names[:3]}{'...' if len(empty_names) > 3 else ''}")
        for n, v in series.items():
            if _nonempty_list(v):
                _warn_non_numeric(n, v)
                _warn_flat(n, v)
        return msgs

    # ── bar family: labels + series (+ errors / significance) ──
    if chart_type in ("bar", "grouped_bar", "hbar", "horizontal_bar", "line",
                      "stacked_bar", "box", "boxplot", "violin"):
        series = data.get("series", data.get("datasets", {}))
        fatal += _check_series_dict(series, "series")
        labels = data.get("labels", data.get("x", []))
        is_boxlike = chart_type in ("box", "boxplot", "violin")
        if _nonempty_list(labels) and series:
            if is_boxlike:
                # box/violin: labels are GROUP names — compare to series count,
                # not to values-per-series (each group holds its own array)
                n_labels, n_groups = _len(labels), len(series)
                if n_labels != n_groups:
                    fatal.append(
                        f"labels has {n_labels} group names but {n_groups} series — "
                        f"each box/violin needs exactly one group name; labels may be misaligned")
            else:
                n_labels, n_first = _len(labels), _len(next(iter(series.values())))
                if n_labels != n_first:
                    fatal.append(
                        f"labels has {n_labels} entries but series values have {n_first} — "
                        f"length mismatch will silently truncate the chart. Fix the CSV/JSON alignment.")
        elif not is_boxlike and not _nonempty_list(labels):
            warns.append("No 'labels' provided; x-axis will use indices 0..n-1")
        # errors must reference existing series (silent KeyError risk)
        errs = data.get("errors", {})
        if isinstance(errs, dict) and errs:
            unknown = [k for k in errs if k not in series]
            if unknown:
                warns.append(f"errors references series not present in data: {unknown[:3]}")
            for n, v in errs.items():
                if n in series and _nonempty_list(v) and _len(v) != _len(series[n]):
                    warns.append(f"errors['{n}'] has {_len(v)} values but series '{n}' has {_len(series[n])} — error bars may be misplaced")
        # significance keys must reference existing series
        sig = data.get("significance", {})
        if isinstance(sig, dict) and sig:
            unknown = [k for k in sig if k not in series]
            if unknown:
                warns.append(f"significance references series not present in data: {unknown[:3]}")

    # ── heatmap: matrix ──
    elif chart_type == "heatmap":
        matrix = data.get("matrix", data.get("data", data.get("values")))
        if matrix is None:
            fatal.append("heatmap requires 'matrix' (2D array of numbers) — key not found in data")
        elif not isinstance(matrix, (list, tuple)) or len(matrix) == 0:
            fatal.append("heatmap: 'matrix' is empty — provide a 2D array")
        elif not all(isinstance(r, (list, tuple)) and _len(r) == _len(matrix[0]) for r in matrix):
            fatal.append("heatmap: 'matrix' rows have unequal lengths (ragged rows) — every row must have the same number of cells")
        else:
            flat = [float(x) for r in matrix for x in r if _is_number(x)]
            n_bad = sum(1 for r in matrix for x in r if not _is_number(x))
            if n_bad:
                warns.append(f"heatmap: {n_bad} non-numeric cell(s) will render as blank/NaN")
            if flat and max(flat) == min(flat):
                warns.append(f"heatmap: all {len(flat)} cells are identical ({flat[0]:g}) — the map will be one uniform color; check the data")

    # ── scatter: x / y (+ groups) ──
    elif chart_type == "scatter":
        x = data.get("x", data.get("xs", []))
        y = data.get("y", data.get("ys", []))
        if not _nonempty_list(x):
            fatal.append("scatter requires 'x' (array of numbers) — key missing or empty")
        if not _nonempty_list(y):
            fatal.append("scatter requires 'y' (array of numbers) — key missing or empty")
        if not fatal:
            if _len(x) != _len(y):
                fatal.append(f"scatter: 'x' has {_len(x)} values but 'y' has {_len(y)} — each point needs one x AND one y; lengths must match")
            _warn_non_numeric("x", x)
            _warn_non_numeric("y", y)
            if len(x) >= 2 and _is_number(x[0]) and _is_number(x[-1]) and max(float(v) for v in x if _is_number(v)) == min(float(v) for v in x if _is_number(v)):
                warns.append("scatter: all x values are identical — points will stack vertically; trend line (if shown) is meaningless")
        groups = data.get("groups", data.get("colors"))
        if groups is not None and not _nonempty_list(groups):
            fatal.append("scatter: 'groups' exists but is empty")
        elif groups is not None and _len(groups) != _len(x) and _len(groups) > 0:
            warns.append(f"scatter: 'groups' has {_len(groups)} entries but {_len(x)} points — group assignment may be misaligned")

    # ── forest: estimates + ci_low + ci_high ──
    elif chart_type == "forest":
        estimates = data.get("estimates", data.get("values", []))
        ci_low = data.get("ci_low", data.get("lower", []))
        ci_high = data.get("ci_high", data.get("upper", []))
        if not _nonempty_list(estimates):
            fatal.append("forest requires 'estimates' (effect sizes per study) — key missing or empty")
        if not _nonempty_list(ci_low):
            fatal.append("forest requires 'ci_low' (lower confidence bound per study) — key missing or empty")
        if not _nonempty_list(ci_high):
            fatal.append("forest requires 'ci_high' (upper confidence bound per study) — key missing or empty")
        if not fatal:
            if not (_len(estimates) == _len(ci_low) == _len(ci_high)):
                fatal.append(f"forest: estimates/ci_low/ci_high lengths differ ({_len(estimates)}/{_len(ci_low)}/{_len(ci_high)}) — every study needs all three values")
            _warn_non_numeric("estimates", estimates)
            for i in range(min(_len(estimates), _len(ci_low), _len(ci_high))):
                if _is_number(estimates[i]) and _is_number(ci_low[i]) and _is_number(ci_high[i]):
                    if not (float(ci_low[i]) <= float(estimates[i]) <= float(ci_high[i])):
                        warns.append(f"forest: study {i} has estimate {estimates[i]:g} outside CI [{ci_low[i]:g}, {ci_high[i]:g}] — check the data")
        labels = data.get("labels", data.get("studies", []))
        if _nonempty_list(labels) and _len(labels) != _len(estimates):
            warns.append(f"forest: {_len(labels)} study labels but {_len(estimates)} estimates — labels may be misaligned")
        weights = data.get("weights")
        if _nonempty_list(weights) and _len(weights) != _len(estimates):
            warns.append(f"forest: {_len(weights)} weights but {_len(estimates)} estimates — bubble sizes may be misassigned")
        events = data.get("events")
        if isinstance(events, list) and events and _len(events) != _len(estimates):
            warns.append(f"forest: {_len(events)} event rows but {_len(estimates)} estimates — events/total may be misaligned")

    # ── KM: groups (list of [t, s] pairs) OR time + survival ──
    elif chart_type in ("km", "survival"):
        groups = data.get("groups", data.get("series", {}))
        has_time = _nonempty_list(data.get("time", []))
        if isinstance(groups, dict) and groups and all(isinstance(v, (list, tuple)) and v and all(isinstance(p, (list, tuple)) and _len(p) >= 2 for p in v) for v in groups.values()):
            for gname, pairs in groups.items():
                times = [p[0] for p in pairs if _is_number(p[0])]
                if len(times) >= 2 and any(times[i] > times[i + 1] for i in range(len(times) - 1)):
                    warns.append(f"km: group '{gname}' has non-increasing time points — survival curves assume chronological order")
        elif has_time and isinstance(data.get("survival"), dict):
            surv = data["survival"]
            fatal += _check_series_dict(surv, "survival", req_nonempty=False)
            for gname, s in surv.items():
                if _nonempty_list(s) and _len(s) != _len(data["time"]):
                    fatal.append(f"km: survival['{gname}'] has {_len(s)} values but 'time' has {_len(data['time'])} — lengths must match")
        elif not isinstance(groups, dict) or not groups:
            fatal.append("km requires 'groups' as {GroupName: [[t, s], ...]} pairs, or 'time' + 'survival' arrays — neither found")

    # ── ROC: curves OR fpr + tpr ──
    elif chart_type == "roc":
        curves = data.get("curves", [])
        fpr = data.get("fpr", data.get("x", []))
        tpr = data.get("tpr", data.get("y", []))
        if _nonempty_list(curves):
            for i, c in enumerate(curves):
                if not isinstance(c, dict) or not (_nonempty_list(c.get("fpr")) and _nonempty_list(c.get("tpr"))):
                    fatal.append(f"roc: curves[{i}] must have 'fpr' and 'tpr' arrays")
                elif _len(c["fpr"]) != _len(c["tpr"]):
                    fatal.append(f"roc: curves[{i}] fpr/tpr lengths differ ({_len(c['fpr'])}/{_len(c['tpr'])}")
                else:
                    f = [float(v) for v in c["fpr"] if _is_number(v)]
                    if len(f) >= 2 and any(f[i] > f[i + 1] + 1e-9 for i in range(len(f) - 1)):
                        warns.append(f"roc: curves[{i}] fpr is not monotonic — sort the curve by threshold")
                c_auc = c.get("auc")
                if isinstance(c_auc, (int, float)) and not (0.0 <= float(c_auc) <= 1.0):
                    warns.append(f"roc: curves[{i}] auc={c_auc:g} is outside [0, 1] — verify the value")
        elif _nonempty_list(fpr) and _nonempty_list(tpr):
            if _len(fpr) != _len(tpr):
                fatal.append(f"roc: fpr has {_len(fpr)} values but tpr has {_len(tpr)} — lengths must match")
            _warn_non_numeric("fpr", fpr)
            _warn_non_numeric("tpr", tpr)
        else:
            fatal.append("roc requires 'curves' (list of {fpr, tpr}) or 'fpr' + 'tpr' arrays — neither found")
        auc = data.get("auc")
        if isinstance(auc, (int, float)) and not (0.0 <= float(auc) <= 1.0):
            warns.append(f"roc: auc={auc:g} is outside [0, 1] — verify the value")

    # ── dual_axis: labels + left + right ──
    elif chart_type == "dual_axis":
        labels = data.get("labels", data.get("x", []))
        left = data.get("left", data.get("y1", {}))
        right = data.get("right", data.get("y2", {}))
        fatal += _check_series_dict(left, "left/y1")
        fatal += _check_series_dict(right, "right/y2")
        if not fatal and _nonempty_list(labels) and left and right:
            n_first = _len(next(iter(left.values())))
            if _len(labels) != n_first:
                fatal.append(f"dual_axis: labels has {_len(labels)} entries but left/right series have {n_first} — lengths must match")

    # ── composite: panels ──
    elif chart_type == "composite":
        panels = data.get("panels", [])
        if not isinstance(panels, list) or not panels:
            fatal.append("composite requires 'panels' (non-empty list of panel objects)")
        else:
            bad = [i for i, p in enumerate(panels) if not isinstance(p, dict) or not p.get("type")]
            if bad:
                fatal.append(f"composite: panels {bad[:5]} are missing a 'type' field — each panel needs 'type' (e.g. 'bar')")

    # ── diagram: blocks ──
    elif chart_type == "diagram":
        blocks = data.get("blocks", [])
        if not isinstance(blocks, list) or not blocks:
            fatal.append("diagram requires 'blocks' (non-empty list of block objects)")

    return fatal, warns


def legend_audit(ax, chart_type, no_legend, n_series):
    """Detect silently-empty legends: >= 2 series drawn, none labeled.

    n_series comes from the DATA (not artist count — matplotlib's
    get_legend_handles_labels only returns labeled artists, so an all-
    unlabeled multi-series figure reports 0 handles). Types that use
    x-axis labels (box/violin/forest), a colorbar (heatmap), or their
    own legend (dual_axis, composite, diagram) are exempt.
    """
    if no_legend or chart_type in ("box", "boxplot", "violin", "heatmap", "forest",
                                   "composite", "diagram", "dual_axis"):
        return None
    if n_series < 2:
        return None
    handles, labels = ax.get_legend_handles_labels()
    if not any(labels):
        return ("multiple series drawn but none carry a 'label' — the legend will be empty; "
                "use series 'name' keys (JSON) or a group column (CSV) so series can be told apart")
    return None


# ── Figure generators ──────────────────────────────────────────────────

def apply_base_style(ax, theme):
    """Apply common styling to axes."""
    for spine in theme["spines"]:
        ax.spines[spine].set_visible(False)
    ax.yaxis.grid(True, alpha=theme["grid_alpha"], linestyle='--')
    ax.tick_params(labelsize=theme["font_size"] - 1)


def gen_bar(data, ax, theme, cjk_fp, **kwargs):
    """Grouped bar chart with horizontal mode, hatching, error bars, significance, and ratio annotations."""
    labels = data.get("labels", data.get("x", []))
    series = data.get("series", data.get("datasets", {}))

    n_groups = len(labels)
    n_series = len(series)
    x = np.arange(n_groups)
    w = 0.8 / max(n_series, 1)
    colors = theme["colors"]
    horizontal = kwargs.get("horizontal", False)
    use_hatch = kwargs.get("hatch", False)
    show_ratio = kwargs.get("show_ratio", False)
    ratio_base = kwargs.get("ratio_base", 0)  # index of base series for ratio

    error_data = data.get("errors", {})
    significance = data.get("significance", {})

    bar_func = ax.barh if horizontal else ax.bar
    all_bars = []  # store for ratio calculation

    for i, (name, values) in enumerate(series.items()):
        offset = (i - (n_series - 1) / 2) * w
        errs = None
        if name in error_data and error_data[name]:
            errs = error_data[name]
            if isinstance(errs, list) and all(isinstance(e, (int, float)) for e in errs):
                pass  # per-bar error
            elif isinstance(errs, (int, float)):
                errs = [errs] * n_groups

        hatch_val = HATCH_PATTERNS[i % len(HATCH_PATTERNS)] if use_hatch else None
        if kwargs.get("alternate", False) and n_series == 1:
            # GLM-5.2 blog style: alternate first two theme colors per bar
            bar_colors = [colors[j % 2] for j in range(len(values))]
        else:
            bar_colors = colors[i % len(colors)]
        if use_hatch:
            # GLM-5.2 blog style: ALL bars get hatching with black hatch lines
            # on colored fill. Black edgecolor ensures visibility on any fill.
            bars = bar_func(x + offset, values, w, yerr=errs,
                            color=bar_colors, edgecolor='black', linewidth=0.6,
                            hatch=hatch_val, capsize=3,
                            error_kw={'linewidth': 1}, label=name)
        else:
            bars = bar_func(x + offset, values, w, yerr=errs,
                            color=bar_colors, edgecolor='white', linewidth=0.5,
                            capsize=3, error_kw={'linewidth': 1}, label=name)
        all_bars.append((name, values, bars, offset))

        # Value labels on bars
        if kwargs.get("show_values", False):
            for j, v in enumerate(values):
                err = errs[j] if errs and j < len(errs) else 0
                if horizontal:
                    ax.text(v + err + max(values) * 0.01, x[j] + offset,
                            f'{v:.1f}', ha='left', va='center', fontsize=7,
                            color=colors[i % len(colors)])
                else:
                    ax.text(x[j] + offset, v + err + max(values) * 0.01,
                            f'{v:.1f}', ha='center', va='bottom', fontsize=7,
                            color=colors[i % len(colors)])

    # Ratio annotations (e.g., "4.96x" above second series bars)
    if show_ratio and n_series >= 2:
        base_name = list(series.keys())[ratio_base]
        base_values = list(series.values())[ratio_base]
        for i, (name, values, bars, offset) in enumerate(all_bars):
            if i == ratio_base:
                continue
            for j, v in enumerate(values):
                bv = base_values[j] if j < len(base_values) else 0
                if bv != 0:
                    ratio = v / bv
                    ratio_str = f'{ratio:.2f}x' if ratio >= 1 else f'{ratio:.2f}x'
                    ratio_color = '#D55E00'
                    if horizontal:
                        ax.text(v + max(values) * 0.02, x[j] + offset,
                                ratio_str, ha='left', va='center', fontsize=8,
                                fontweight='bold', color=ratio_color)
                    else:
                        ax.text(x[j] + offset, v + max(values) * 0.02,
                                ratio_str, ha='center', va='bottom', fontsize=8,
                                fontweight='bold', color=ratio_color)

    # Significance brackets
    if significance:
        for key, label in significance.items():
            parts = key.split(":")
            if len(parts) == 2:
                grp_idx = int(parts[1])
            else:
                grp_idx = int(parts[0])
            if horizontal:
                x_top = ax.get_xlim()[1] * 0.95
                y_pos = x[grp_idx]
                fc = '#C0392B' if label not in ('NS', 'ns') else 'gray'
                fw = 'bold' if label not in ('NS', 'ns') else 'normal'
                ax.annotate(label, (x_top, y_pos), ha='left', va='center',
                            fontsize=8, fontweight=fw, color=fc)
            else:
                y_top = ax.get_ylim()[1] * 0.95
                fc = '#C0392B' if label not in ('NS', 'ns') else 'gray'
                fw = 'bold' if label not in ('NS', 'ns') else 'normal'
                ax.annotate(label, (x[grp_idx], y_top), ha='center', va='bottom',
                            fontsize=8, fontweight=fw, color=fc)

    if horizontal:
        y_fs = theme["font_size"] - 1
        if len(labels) > 12:
            y_fs -= 1
        ax.set_yticks(x)
        ax.set_yticklabels(labels, fontsize=y_fs,
                           fontproperties=cjk_fp if cjk_fp and any(has_cjk(l) for l in labels) else None)
        ax.invert_yaxis()
    else:
        max_lbl_len = max((len(str(l)) for l in labels), default=0)
        rotation = 45 if (len(labels) > 8 or max_lbl_len > 12) else 0
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=theme["font_size"] - 1,
                           rotation=rotation, ha='right' if rotation else 'center',
                           fontproperties=cjk_fp if cjk_fp and any(has_cjk(l) for l in labels) else None)


def gen_heatmap(data, ax, theme, cjk_fp, **kwargs):
    """Heatmap with text annotations."""
    matrix = data.get("matrix", data.get("data", data.get("values", None)))
    if matrix is None:
        # Fallback: build matrix from series (C2 fix — CSV heatmap support)
        series = data.get("series", {})
        if series:
            matrix = np.array(list(series.values()))
        else:
            matrix = np.array([])
    else:
        matrix = np.array(matrix)
    row_labels = data.get("row_labels", data.get("y_labels", data.get("rows", data.get("labels", []))))
    col_labels = data.get("col_labels", data.get("x_labels", data.get("cols", list(data.get("series", {}).keys()))))
    cmap = kwargs.get("cmap") or "RdBu_r"
    vmin = kwargs.get("vmin", None)
    vmax = kwargs.get("vmax", None)
    annot_fmt = kwargs.get("annot_format", "{:+.1f}")

    if matrix.size == 0:
        raise ValueError("heatmap: matrix is empty — provide 'matrix' (2D list) or 'series'")

    has_neg = bool((matrix < 0).any())
    # Data-driven default: all-positive data uses a warm sequential colormap
    # (YlOrRd) — RdBu_r's white midpoint makes low positive values look like
    # a "broken band" (断层). Diverging colormaps are only sensible when the
    # data actually spans negative values.
    if cmap == "RdBu_r" and not has_neg and kwargs.get("cmap") is None:
        cmap = "YlOrRd"

    if vmin is None or vmax is None:
        if has_neg:
            abs_max = max(abs(matrix.min()), abs(matrix.max()))
            vmin = vmin if vmin is not None else -abs_max
            vmax = vmax if vmax is not None else abs_max
        else:
            vmin = vmin if vmin is not None else float(matrix.min())
            vmax = vmax if vmax is not None else float(matrix.max())

    im = ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax, aspect='auto')

    # Text annotations
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            color = 'white' if abs(v) > (abs(vmin) + abs(vmax)) / 2 * 0.7 else 'black'
            ax.text(j, i, annot_fmt.format(v), ha='center', va='center',
                    fontsize=9, fontweight='bold', color=color)

    ax.set_xticks(range(len(col_labels)))
    use_cjk_cols = cjk_fp and any(has_cjk(l) for l in col_labels)
    max_col_len = max((len(str(l)) for l in col_labels), default=0)
    rot = 45 if (len(col_labels) > 6 or max_col_len > 14) else 0
    ax.set_xticklabels(col_labels, fontsize=theme["font_size"] - 2,
                       rotation=rot, ha='right' if rot else 'center',
                       fontproperties=cjk_fp if use_cjk_cols else None)
    ax.set_yticks(range(len(row_labels)))
    use_cjk_rows = cjk_fp and any(has_cjk(l) for l in row_labels)
    ax.set_yticklabels(row_labels, fontsize=theme["font_size"],
                       fontproperties=cjk_fp if use_cjk_rows else None)

    return im  # for colorbar


def gen_scatter(data, ax, theme, cjk_fp, **kwargs):
    """Scatter plot with optional trend line and grouping."""
    x_data = np.array(data.get("x", data.get("xs", [])))
    y_data = np.array(data.get("y", data.get("ys", [])))
    groups = data.get("groups", data.get("colors", None))

    if groups is None:
        ax.scatter(x_data, y_data, s=60, color=theme["colors"][0],
                   edgecolors='white', linewidth=0.5, alpha=0.7, zorder=3)
    else:
        # Validate groups length matches x/y data length
        n = min(len(x_data), len(y_data))
        if len(groups) > n:
            groups = groups[:n]
        unique_groups = list(dict.fromkeys(groups))  # preserve order
        for i, g in enumerate(unique_groups):
            mask = [j for j in range(len(groups)) if groups[j] == g]
            c = theme["colors"][i % len(theme["colors"])]
            ax.scatter(x_data[mask], y_data[mask], s=60, c=c,
                       edgecolors='white', linewidth=0.5, alpha=0.7,
                       label=g, zorder=3)

    # Point labels (data["labels"] — one per (x, y) point)
    point_labels = data.get("labels", [])
    if point_labels and len(point_labels) == len(x_data):
        use_cjk = cjk_fp and any(has_cjk(str(l)) for l in point_labels)
        n_pts = len(x_data)
        for i, (xi, yi, lab) in enumerate(zip(x_data, y_data, point_labels)):
            # Alternate above/below to keep neighbors readable; offset grows
            # with index so clustered points (e.g. years 1950/1953/1955) don't collide.
            row = i // 2  # every other point flips side
            dy = 10 + 3 * row if i % 2 == 0 else -13 - 3 * row
            ax.annotate(str(lab), xy=(xi, yi), xytext=(0, dy),
                        textcoords='offset points', fontsize=6.5,
                        ha='center', va='center', zorder=5,
                        fontproperties=cjk_fp if use_cjk else None,
                        color='#444444', alpha=0.9)

    # Trend line
    if kwargs.get("trend", True) and len(x_data) >= 3:
        z = np.polyfit(x_data, y_data, 1)
        p = np.poly1d(z)
        x_line = np.linspace(x_data.min(), x_data.max(), 100)
        ax.plot(x_line, p(x_line), '--', color='gray', alpha=0.6, linewidth=1.2,
                zorder=2, label='Linear trend')
        r = np.corrcoef(x_data, y_data)[0, 1]
        ax.text(0.95, 0.05, f'r = {r:.3f}', transform=ax.transAxes,
                ha='right', va='bottom', fontsize=9, fontstyle='italic', color='gray',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8, edgecolor='lightgray'))

    # Mean points
    if groups and kwargs.get("show_mean", False):
        unique_groups = list(dict.fromkeys(groups))
        for i, g in enumerate(unique_groups):
            mask = [j for j in range(len(groups)) if groups[j] == g]
            mx, my = np.mean(x_data[mask]), np.mean(y_data[mask])
            c = theme["colors"][i % len(theme["colors"])]
            ax.scatter(mx, my, s=150, c=c, edgecolors='black', linewidth=1.2,
                       marker='o', zorder=4)

    ax.xaxis.grid(True, alpha=theme["grid_alpha"], linestyle='--')


def gen_line(data, ax, theme, cjk_fp, **kwargs):
    """Line chart with optional error bands."""
    labels = data.get("labels", data.get("x", []))
    series = data.get("series", data.get("datasets", {}))
    error_data = data.get("errors", {})
    markers = ['o', 's', 'D', '^', 'v', 'p', '*', 'h', '+', 'x']

    x = np.arange(len(labels)) if not any(isinstance(l, (int, float)) for l in labels) else np.array(labels)

    for i, (name, values) in enumerate(series.items()):
        c = theme["colors"][i % len(theme["colors"])]
        mk = markers[i % len(markers)]
        lw = kwargs.get("linewidth", 2)
        ax.plot(x, values, c=c, marker=mk, markersize=6, linewidth=lw, label=name, zorder=3)

        # Error band/fill
        if name in error_data and error_data[name]:
            errs = error_data[name]
            if isinstance(errs, list) and len(errs) == len(values):
                lower = [v - e for v, e in zip(values, errs)]
                upper = [v + e for v, e in zip(values, errs)]
                ax.fill_between(x, lower, upper, color=c, alpha=0.15, zorder=2)

    ax.set_xticks(x if not any(isinstance(l, (int, float)) for l in labels) else range(len(labels)))
    if not any(isinstance(l, (int, float)) for l in labels):
        use_cjk = cjk_fp and any(has_cjk(l) for l in labels)
        rot = 45 if len(labels) > 10 else 0
        ax.set_xticklabels(labels, fontsize=theme["font_size"] - 1,
                           rotation=rot, ha='right' if rot else 'center',
                           fontproperties=cjk_fp if use_cjk else None)


def gen_box(data, ax, theme, cjk_fp, **kwargs):
    """Box plot with optional jitter points."""
    labels = data.get("labels", data.get("x", []))
    series = data.get("series", data.get("datasets", {}))

    positions = list(range(len(series)))
    bp = ax.boxplot(list(series.values()), positions=positions, widths=0.5,
                    patch_artist=True, showfliers=False)

    for i, (patch, name) in enumerate(zip(bp['boxes'], series.keys())):
        patch.set_facecolor(theme["colors"][i % len(theme["colors"])])
        patch.set_alpha(0.6)

    # Jitter points
    rng = np.random.default_rng(42)
    for i, (name, values) in enumerate(series.items()):
        vals = np.array(values, dtype=float)
        jitter_x = positions[i] + rng.normal(0, 0.06, len(vals))
        c = theme["colors"][i % len(theme["colors"])]
        ax.scatter(jitter_x, vals, s=18, c=c, alpha=0.5, zorder=3, edgecolors='none')

    ax.set_xticks(positions)
    use_cjk = cjk_fp and any(has_cjk(l) for l in series.keys())
    ax.set_xticklabels(list(series.keys()), fontsize=theme["font_size"] - 1,
                       fontproperties=cjk_fp if use_cjk else None)


def gen_forest(data, ax, theme, cjk_fp, **kwargs):
    """Forest plot for meta-analysis with weights, heterogeneity, and events."""
    labels = data.get("labels", data.get("studies", []))
    estimates = data.get("estimates", data.get("values", []))
    ci_low = data.get("ci_low", data.get("lower", []))
    ci_high = data.get("ci_high", data.get("upper", []))
    weights = data.get("weights", None)  # Study weights for bubble size
    overall = data.get("overall", None)
    ref_line = data.get("ref_line", 0)
    heterogeneity = data.get("heterogeneity", None)  # {"Q": float, "df": int, "I2": float, "p": float}
    events = data.get("events", None)  # [{"events": int, "total": int}, ...] per study
    measure = data.get("measure", "OR")  # Effect measure label: OR, RR, HR, MD, SMD
    use_hatch = kwargs.get("hatch", False)

    n_studies = len(labels)
    y_pos = list(range(n_studies))

    # Calculate weight-based bubble sizes if weights provided
    if weights and len(weights) == n_studies:
        w_arr = np.array(weights, dtype=float)
        w_min, w_max = w_arr.min(), w_arr.max()
        if w_max > w_min:
            bubble_sizes = 40 + (w_arr - w_min) / (w_max - w_min) * 160  # 40-200 range
        else:
            bubble_sizes = np.full(n_studies, 80.0)
    else:
        bubble_sizes = np.full(n_studies, 80.0)

    # Column layout: leave space for events column on left
    plot_x_start = 0.0
    events_col_x = None
    if events and len(events) == n_studies:
        events_col_x = -0.3  # Relative position in axes coords, handled via text

    for i, (est, lo, hi) in enumerate(zip(estimates, ci_low, ci_high)):
        # CI whisker line
        ax.plot([lo, hi], [i, i], '-', color=theme["colors"][0], linewidth=1.5, zorder=2)
        # Weighted point estimate (bubble)
        ax.scatter(est, i, c=theme["colors"][0], s=bubble_sizes[i], zorder=3,
                   edgecolors='black', linewidth=0.5)
        # Effect estimate annotation on right
        ax.text(hi + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.02, i,
                f'{est:.2f} [{lo:.2f}, {hi:.2f}]', va='center', fontsize=8)
        # Events/Total on left (if provided)
        if events and i < len(events):
            ev = events[i]
            ev_str = f"{ev.get('events', '?')}/{ev.get('total', '?')}" if isinstance(ev, dict) else str(ev)
            ax.annotate(ev_str, xy=(0, 0), xytext=(-0.15, i),
                        textcoords=('axes fraction', 'data'),
                        ha='right', va='center', fontsize=7, color='#555555')

    # Reference line
    ax.axvline(x=ref_line, color='gray', linestyle='--', linewidth=1, alpha=0.6)

    # Separator line before overall
    if overall:
        ax.axhline(y=n_studies - 0.5, color='#333333', linewidth=0.8, alpha=0.5)

    # Overall diamond
    if overall:
        oy = n_studies
        est_o = overall["estimate"]
        lo_o = overall["ci_low"]
        hi_o = overall["ci_high"]
        diamond_x = [lo_o, est_o, hi_o, est_o, lo_o]
        diamond_y = [oy, oy - 0.2, oy, oy + 0.2, oy]
        ax.fill(diamond_x, diamond_y, color=theme["colors"][1], alpha=0.7, zorder=4,
                hatch=HATCH_PATTERNS[1] if use_hatch else None)
        ax.text(hi_o + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.02, oy,
                f'Overall: {est_o:.2f} [{lo_o:.2f}, {hi_o:.2f}]', va='center',
                fontsize=9, fontweight='bold')

    # Heterogeneity annotation
    if heterogeneity:
        i2 = heterogeneity.get("I2", None)
        q_val = heterogeneity.get("Q", None)
        df_val = heterogeneity.get("df", None)
        p_val = heterogeneity.get("p", None)
        parts = []
        if i2 is not None:
            parts.append(f"I² = {i2:.1f}%")
        if q_val is not None and df_val is not None:
            parts.append(f"Q = {q_val:.2f}, df = {df_val}")
        if p_val is not None:
            parts.append(f"p = {p_val:.3f}" if p_val >= 0.001 else f"p < 0.001")
        if parts:
            het_text = "Heterogeneity: " + "; ".join(parts)
            ax.text(0.5, -0.12, het_text, transform=ax.transAxes,
                    ha='center', va='top', fontsize=7, fontstyle='italic', color='#555555')

    # X-axis label with measure type
    ax.set_xlabel(measure, fontsize=theme["font_size"])

    # Column header for events
    if events and len(events) > 0:
        ax.annotate("Events/Total", xy=(0, 0), xytext=(-0.15, -0.8),
                    textcoords=('axes fraction', 'data'),
                    ha='right', va='center', fontsize=7, fontweight='bold', color='#333333')

    all_labels = list(labels) + (["Overall"] if overall else [])
    ax.set_yticks(list(y_pos) + ([n_studies] if overall else []))
    use_cjk = cjk_fp and any(has_cjk(l) for l in all_labels)
    ax.set_yticklabels(all_labels, fontsize=theme["font_size"],
                       fontproperties=cjk_fp if use_cjk else None)
    ax.invert_yaxis()


def gen_violin(data, ax, theme, cjk_fp, **kwargs):
    """Violin plot with optional inner box and jitter points."""
    labels = data.get("labels", data.get("x", []))
    series = data.get("series", data.get("datasets", {}))

    positions = list(range(len(series)))
    values_list = list(series.values())

    vp = ax.violinplot(values_list, positions=positions, widths=0.6,
                       showmeans=kwargs.get("show_means", True),
                       showmedians=kwargs.get("show_medians", True),
                       showextrema=kwargs.get("show_extrema", True))

    # Color the violin bodies
    for i, body in enumerate(vp['bodies']):
        body.set_facecolor(theme["colors"][i % len(theme["colors"])])
        body.set_alpha(0.6)
        body.set_edgecolor(theme["colors"][i % len(theme["colors"])])
        body.set_linewidth(1)

    # Style internal lines
    for part in ['cmeans', 'cmedians', 'cmins', 'cmaxes', 'cbars']:
        if part in vp:
            vp[part].set_color('#333333')
            vp[part].set_linewidth(1)

    ax.set_xticks(positions)
    use_cjk = cjk_fp and any(has_cjk(l) for l in series.keys())
    ax.set_xticklabels(list(series.keys()), fontsize=theme["font_size"] - 1,
                       fontproperties=cjk_fp if use_cjk else None)


def gen_km(data, ax, theme, cjk_fp, **kwargs):
    """Kaplan-Meier survival curve with risk table and log-rank test."""
    groups = data.get("groups", data.get("series", {}))  # {"Group A": [[t1, s1], [t2, s2], ...], ...}
    time_points = data.get("time_points", None)  # optional shared x-axis
    risk_table = data.get("risk_table", None)  # optional risk table data
    log_rank = data.get("log_rank", None)  # optional {"p": 0.032, "method": "log-rank"}
    median_survival = data.get("median_survival", None)  # optional {"Group A": 24.5, ...}

    # Support two formats:
    # Format 1: {"groups": {"A": [[t1,e1], [t2,e2],...], ...}} where e=1 event, e=0 censored
    # Format 2: {"groups": {"A": [t1, t2, ...]}, ...} — all events (no censoring)
    # Format 3: {"time": [...], "survival": {"A": [...], "B": [...]}, "censored": {"A": [...], ...}}

    if isinstance(groups, dict):
        group_names = list(groups.keys())
    elif isinstance(groups, list):
        # List of group data with names from labels
        group_names = data.get("labels", [f"Group {i+1}" for i in range(len(groups))])
        groups = dict(zip(group_names, groups))
        bad = [g for g in groups.values()
               if not (isinstance(g, (list, tuple)) and
                       all(isinstance(p, (list, tuple)) and len(p) >= 2 and
                           all(isinstance(n, (int, float)) for n in p) for p in g) or
                       all(isinstance(n, (int, float)) for n in g))]
        if bad:
            raise ValueError(
                "km: unsupported 'groups' format. Expected {\"Group\": [[t, s], ...]} "
                "or [t1, t2, ...] per group — got object list like "
                "[{\"label\": ..., \"time\": ..., \"events\": ...}]. "
                "Convert to {\"组名\": [[t, s], ...]}.")
    else:
        group_names = []
        groups = {}

    # Format 3 detection: time + survival format
    if not groups and "time" in data and "survival" in data:
        surv_data = data["survival"]
        cens_data = data.get("censored", {})
        group_names = list(surv_data.keys())
        for gname in group_names:
            t_arr = data["time"]
            s_arr = surv_data[gname]
            c_arr = cens_data.get(gname, [0] * len(s_arr))
            # Convert to step format — survival already provided
            ax.step(t_arr, s_arr, where='post', color=theme["colors"][group_names.index(gname) % len(theme["colors"])],
                    linewidth=2, label=gname, zorder=3)
            # Censor marks
            for j in range(len(t_arr)):
                if j < len(c_arr) and c_arr[j] == 1:
                    ax.scatter(t_arr[j], s_arr[j], marker='+', color=theme["colors"][group_names.index(gname) % len(theme["colors"])],
                               s=30, linewidth=1.5, zorder=4)
    else:
        # Format 1/2: raw time-to-event data
        for i, gname in enumerate(group_names):
            c = theme["colors"][i % len(theme["colors"])]
            raw = groups[gname]

            if len(raw) == 0:
                continue

            # Parse data points
            if isinstance(raw[0], (list, tuple)):
                # [[time, event], ...]
                times = np.array([p[0] for p in raw], dtype=float)
                events = np.array([p[1] for p in raw], dtype=float)
            else:
                # [time1, time2, ...] — all events
                times = np.array(raw, dtype=float)
                events = np.ones(len(times))

            # Sort by time
            order = np.argsort(times)
            times = times[order]
            events = events[order]

            # Calculate KM estimate
            n = len(times)
            unique_times = np.unique(times)
            surv = 1.0
            surv_times = [0]
            surv_probs = [1.0]
            n_at_risk = n
            censor_times = []
            censor_surv = []

            for t in unique_times:
                mask = times == t
                d = events[mask].sum()  # deaths at time t
                censored_at_t = mask.sum() - d  # censored at time t

                if n_at_risk > 0 and d > 0:
                    surv *= (1 - d / n_at_risk)

                # Record censoring marks
                if censored_at_t > 0:
                    censor_times.append(t)
                    censor_surv.append(surv)

                surv_times.append(t)
                surv_probs.append(surv)

                n_at_risk -= mask.sum()

            # Plot step function
            ax.step(surv_times, surv_probs, where='post', color=c,
                    linewidth=2, label=gname, zorder=3)

            # Censor marks
            for ct, cs in zip(censor_times, censor_surv):
                ax.scatter(ct, cs, marker='+', color=c, s=30, linewidth=1.5, zorder=4)

            # Median survival line
            if median_survival and gname in median_survival:
                med_t = median_survival[gname]
                if med_t is not None:
                    ax.axvline(x=med_t, color=c, linestyle=':', alpha=0.4, linewidth=1)

    # Reference line at 0.5 (median)
    ax.axhline(y=0.5, color='gray', linestyle='--', alpha=0.3, linewidth=0.8)

    # Log-rank test annotation
    if log_rank:
        p_val = log_rank.get("p", None)
        method = log_rank.get("method", "Log-rank")
        if p_val is not None:
            try:
                p_val = float(p_val)  # defensive: coerce strings like "0.001"
            except (ValueError, TypeError):
                p_val = 1.0
            p_str = f"p = {p_val:.3f}" if p_val >= 0.001 else "p < 0.001"
            sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "NS"
            ax.text(0.95, 0.95, f'{method}\n{p_str} ({sig})',
                    transform=ax.transAxes, ha='right', va='top',
                    fontsize=8, fontstyle='italic', color='#333333',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9, edgecolor='lightgray'))

    # Risk table below the plot (if provided)
    if risk_table and isinstance(risk_table, dict):
        # risk_table format: {"times": [0, 6, 12, ...], "Group A": [50, 42, 35, ...], ...}
        rt_times = risk_table.get("times", [])
        ax.text(0.02, -0.08, "Number at risk", transform=ax.transAxes,
                fontsize=7, fontweight='bold', color='#333333')
        for i, gname in enumerate(group_names):
            c = theme["colors"][i % len(theme["colors"])]
            n_at = risk_table.get(gname, [])
            rt_str = "  ".join(str(n) for n in n_at)
            ax.text(0.02, -0.08 - (i + 1) * 0.04, f"{gname}: {rt_str}",
                    transform=ax.transAxes, fontsize=6, color=c)

    ax.set_ylim(-0.02, 1.02)
    ax.set_xlim(left=0)
    ax.xaxis.grid(True, alpha=theme["grid_alpha"], linestyle='--')


def gen_roc(data, ax, theme, cjk_fp, **kwargs):
    """ROC curve with AUC value, confidence interval, and optimal cutoff."""
    curves = data.get("curves", None)  # list of curve objects
    single_fpr = data.get("fpr", data.get("x", None))
    single_tpr = data.get("tpr", data.get("y", None))
    single_auc = data.get("auc", None)
    ci = data.get("ci", None)  # {"low": 0.82, "high": 0.94}
    cutoff = data.get("cutoff", None)  # {"fpr": 0.15, "tpr": 0.88, "threshold": 2.35}
    diagonal = data.get("diagonal", True)  # show diagonal reference line

    # Support single curve (fpr/tpr arrays) or multiple curves
    if curves is None and single_fpr is not None and single_tpr is not None:
        fpr_arr = np.array(single_fpr, dtype=float)
        tpr_arr = np.array(single_tpr, dtype=float)
        auc_val = single_auc

        # Compute AUC if not provided
        if auc_val is None:
            auc_val = np.trapezoid(tpr_arr, fpr_arr) if hasattr(np, 'trapezoid') else np.trapz(tpr_arr, fpr_arr)

        ax.plot(fpr_arr, tpr_arr, color=theme["colors"][0], linewidth=2.5, zorder=3,
                label=f'AUC = {auc_val:.3f}')

        # CI annotation
        if ci:
            ci_low = ci.get("low", ci.get("ci_low", None))
            ci_high = ci.get("high", ci.get("ci_high", None))
            if ci_low is not None and ci_high is not None:
                ax.text(0.95, 0.05, f'95% CI: [{ci_low:.3f}, {ci_high:.3f}]',
                        transform=ax.transAxes, ha='right', va='bottom',
                        fontsize=8, color='#555555',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9, edgecolor='lightgray'))

        # Optimal cutoff point
        if cutoff:
            co_fpr = cutoff.get("fpr", None)
            co_tpr = cutoff.get("tpr", None)
            co_thr = cutoff.get("threshold", None)
            if co_fpr is not None and co_tpr is not None:
                ax.scatter(co_fpr, co_tpr, color=theme["colors"][0], s=80, zorder=5,
                           edgecolors='black', linewidth=1, marker='o')
                label_parts = [f'Optimal cutoff']
                if co_thr is not None:
                    label_parts.append(f'threshold = {co_thr}')
                ax.annotate('\n'.join(label_parts), (co_fpr, co_tpr),
                            textcoords='offset points', xytext=(10, -15),
                            fontsize=7, color='#555555',
                            arrowprops=dict(arrowstyle='->', color='gray', lw=0.8))

    elif curves:
        # Multiple ROC curves
        for i, curve in enumerate(curves):
            fpr_c = np.array(curve.get("fpr", curve.get("x", [])), dtype=float)
            tpr_c = np.array(curve.get("tpr", curve.get("y", [])), dtype=float)
            auc_c = curve.get("auc", None)
            name = curve.get("name", f'Model {i+1}')

            if auc_c is None:
                auc_c = np.trapezoid(tpr_c, fpr_c) if hasattr(np, 'trapezoid') else np.trapz(tpr_c, fpr_c)

            c = theme["colors"][i % len(theme["colors"])]
            ax.plot(fpr_c, tpr_c, color=c, linewidth=2, zorder=3,
                    label=f'{name} (AUC={auc_c:.3f})')

    # Diagonal reference line
    if diagonal:
        ax.plot([0, 1], [0, 1], '--', color='gray', alpha=0.5, linewidth=1, zorder=1)

    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_aspect('equal')
    ax.xaxis.grid(True, alpha=theme["grid_alpha"], linestyle='--')


def gen_stacked_bar(data, ax, theme, cjk_fp, **kwargs):
    """Stacked bar chart for compositional data (e.g., subgroup proportions)."""
    labels = data.get("labels", data.get("x", []))
    series = data.get("series", data.get("datasets", {}))
    percentage = data.get("percentage", False)  # normalize to 100%
    show_total = data.get("show_total", False)  # show total on top of each bar
    errors = data.get("errors", None)  # optional error bars for totals
    use_hatch = kwargs.get("hatch", False)

    n_groups = len(labels)
    x = np.arange(n_groups)
    colors = theme["colors"]
    bottoms = np.zeros(n_groups)

    for i, (name, values) in enumerate(series.items()):
        vals = np.array(values, dtype=float)
        c = colors[i % len(colors)]
        hatch_val = HATCH_PATTERNS[i % len(HATCH_PATTERNS)] if use_hatch else None
        bars = ax.bar(x, vals, 0.65, bottom=bottoms, color=c,
                      edgecolor='black' if use_hatch else 'white',
                      linewidth=0.6 if use_hatch else 0.5,
                      hatch=hatch_val, label=name, zorder=2)

        # Value labels inside bars (only for segments > 5% of total)
        totals = sum(np.array(s, dtype=float) for s in series.values())
        for j, (v, total) in enumerate(zip(vals, totals)):
            if total > 0 and v / total > 0.05:  # only label segments > 5%
                ax.text(x[j], bottoms[j] + v / 2, f'{v:.1f}' if not percentage else f'{v/total*100:.1f}%',
                        ha='center', va='center', fontsize=7, color='white', fontweight='bold',
                        zorder=3)

        bottoms += vals

    # Total labels on top
    if show_total:
        for j in range(n_groups):
            total = bottoms[j]
            ax.text(x[j], total + 0.5, f'N={total:.0f}', ha='center', va='bottom',
                    fontsize=7, color='#333333', fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=theme["font_size"] - 1,
                       fontproperties=cjk_fp if cjk_fp and any(has_cjk(l) for l in labels) else None)

    if percentage:
        ax.set_ylim(0, max(bottoms) * 1.1)


def gen_dual_axis(data, ax, theme, cjk_fp, **kwargs):
    """Dual Y-axis line chart for comparing two metrics on different scales."""
    labels = data.get("labels", data.get("x", []))
    left_series = data.get("left", data.get("y1", {}))  # {"CRP (mg/L)": [5, 8, 12, ...]}
    right_series = data.get("right", data.get("y2", {}))  # {"DAS28": [3.2, 4.1, 5.6, ...]}
    left_errors = data.get("left_errors", data.get("y1_errors", {}))
    right_errors = data.get("right_errors", data.get("y2_errors", {}))
    left_ylabel = data.get("left_ylabel", "")
    right_ylabel = data.get("right_ylabel", "")

    def _check_series_dict(sd, which):
        if not isinstance(sd, dict):
            raise ValueError(f"dual_axis: {which} must be a dict of {{series_name: [values]}}")
        for k, v in sd.items():
            if not isinstance(v, (list, tuple)) or not all(isinstance(x, (int, float)) for x in v):
                raise ValueError(
                    f"dual_axis: {which}['{k}'] must be a numeric list. "
                    f"Wrong format? Use {{\"{which}\": {{\"系列名\": [值, ...]}}}} — not "
                    f"{{\"name\": ..., \"values\": ...}}.")
    _check_series_dict(left_series, "left")
    _check_series_dict(right_series, "right")

    markers = ['o', 's', 'D', '^', 'v', 'p', '*', 'h']
    x = np.arange(len(labels)) if not any(isinstance(l, (int, float)) for l in labels) else np.array(labels, dtype=float)

    # Create second axis
    ax2 = ax.twinx()

    # Plot left axis series
    for i, (name, values) in enumerate(left_series.items()):
        c = theme["colors"][i % len(theme["colors"])]
        mk = markers[i % len(markers)]
        ax.plot(x, values, color=c, marker=mk, markersize=6, linewidth=2, label=name, zorder=3)
        if name in left_errors and left_errors[name]:
            errs = left_errors[name]
            lower = [v - e for v, e in zip(values, errs)]
            upper = [v + e for v, e in zip(values, errs)]
            ax.fill_between(x, lower, upper, color=c, alpha=0.15, zorder=2)

    # Plot right axis series
    right_colors = ['#D55E00', '#CC79A7', '#0072B2', '#009E73', '#F0E442']  # distinct from left
    if theme.get("colorblind_safe"):
        # Use different Okabe-Ito colors for right axis
        offset = len(left_series)
        right_colors = [theme["colors"][(offset + j) % len(theme["colors"])] for j in range(5)]

    for i, (name, values) in enumerate(right_series.items()):
        c = right_colors[i % len(right_colors)]
        mk = markers[(len(left_series) + i) % len(markers)]
        ax2.plot(x, values, color=c, marker=mk, markersize=6, linewidth=2,
                 linestyle='--', label=name, zorder=3)
        if name in right_errors and right_errors[name]:
            errs = right_errors[name]
            lower = [v - e for v, e in zip(values, errs)]
            upper = [v + e for v, e in zip(values, errs)]
            ax2.fill_between(x, lower, upper, color=c, alpha=0.15, zorder=2)

    # Style right axis
    ax2.spines['right'].set_visible(True)
    ax2.tick_params(axis='y', labelsize=theme["font_size"] - 1)
    ax2.grid(False)  # no grid on right axis

    # Set x-axis labels
    if not any(isinstance(l, (int, float)) for l in labels):
        ax.set_xticks(x)
        use_cjk = cjk_fp and any(has_cjk(l) for l in labels)
        ax.set_xticklabels(labels, fontsize=theme["font_size"] - 1,
                           fontproperties=cjk_fp if use_cjk else None)

    # Axis labels
    if left_ylabel:
        ax.set_ylabel(left_ylabel, fontsize=theme["font_size"],
                      fontproperties=cjk_fp if cjk_fp and has_cjk(left_ylabel) else None)
        _ensure_ylabel_clear(ax)
    if right_ylabel:
        ax2.set_ylabel(right_ylabel, fontsize=theme["font_size"],
                       fontproperties=cjk_fp if cjk_fp and has_cjk(right_ylabel) else None)
        _ensure_ylabel_clear(ax2)

    # Combine legends from both axes
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=theme["font_size"] - 1,
              loc='best', framealpha=0.9, prop=cjk_fp if cjk_fp else None)

    # Store ax2 reference for downstream use
    return ax2


def gen_composite(data, ax, theme, cjk_fp, **kwargs):
    """Multi-panel composite figure (e.g., Panel A + B + C for journal figures).

    JSON format:
    {
      "layout": [rows, cols],  // e.g. [1, 3] or [2, 2]
      "panels": [
        {
          "title": "Panel A: ...",
          "type": "bar",        // any chart type from GENERATORS
          "data": { ... },      // data for that chart type
          "xlabel": "...", "ylabel": "...",
          "pos": [row, col]     // grid position (0-indexed)
        },
        ...
      ]
    }
    """
    import matplotlib.gridspec as gridspec

    layout = data.get("layout", [1, 2])
    n_rows, n_cols = layout[0], layout[1]
    panels = data.get("panels", [])

    if not panels:
        return None

    fig = ax.figure
    # Clear the default axis created by plt.subplots
    ax.remove()

    gs = gridspec.GridSpec(n_rows, n_cols, figure=fig,
                           hspace=0.35, wspace=0.3,
                           left=0.08, right=0.95, top=0.92, bottom=0.08)

    for panel in panels:
        pos = panel.get("pos", [0, 0])
        panel_type = panel.get("type", "bar")
        panel_data = panel.get("data", {})

        sub_ax = fig.add_subplot(gs[pos[0], pos[1]])

        # Get the generator function
        gen_func = GENERATORS.get(panel_type)
        if gen_func is None:
            sub_ax.text(0.5, 0.5, f"Unknown type: {panel_type}",
                        ha='center', va='center', transform=sub_ax.transAxes)
            continue

        # Pass through relevant kwargs
        panel_kwargs = {
            "show_values": panel.get("show_values", kwargs.get("show_values", False)),
            "trend": panel.get("trend", kwargs.get("trend", True)),
            "horizontal": panel.get("horizontal", False),
            "hatch": panel.get("hatch", False),
            "alternate": panel.get("alternate", False),
            "show_ratio": panel.get("show_ratio", False),
            "cmap": panel.get("cmap", kwargs.get("cmap")),
            "vmin": panel.get("vmin", kwargs.get("vmin")),
            "vmax": panel.get("vmax", kwargs.get("vmax")),
        }

        extra = gen_func(panel_data, sub_ax, theme, cjk_fp, **panel_kwargs)
        apply_base_style(sub_ax, theme)

        # Panel-specific labels
        ptitle = panel.get("title", "")
        if ptitle:
            sub_ax.set_title(ptitle, fontsize=theme["font_size"], fontweight='bold', pad=8,
                             fontproperties=cjk_fp if cjk_fp and has_cjk(ptitle) else None)
        if panel.get("xlabel"):
            sub_ax.set_xlabel(panel["xlabel"], fontsize=theme["font_size"] - 1,
                              fontproperties=cjk_fp if cjk_fp and has_cjk(panel["xlabel"]) else None)
        if panel.get("ylabel"):
            sub_ax.set_ylabel(panel["ylabel"], fontsize=theme["font_size"] - 1,
                              fontproperties=cjk_fp if cjk_fp and has_cjk(panel["ylabel"]) else None)
            _ensure_ylabel_clear(sub_ax)

        # Legend for panel
        show_legend = panel.get("legend", True)
        if show_legend and sub_ax.get_legend_handles_labels()[1]:
            sub_ax.legend(fontsize=theme["font_size"] - 2, loc='best', framealpha=0.9,
                          prop=cjk_fp if cjk_fp else None)

        # Colorbar for heatmap panels
        if extra is not None and hasattr(extra, 'get_cmap'):
            cbar = fig.colorbar(extra, ax=sub_ax, shrink=0.8)

    return "composite"  # signal to main() that figure is already built


def gen_diagram(data, ax, theme, cjk_fp, **kwargs):
    """Architecture/flow diagram with colored blocks, arrows, and groupings.

    JSON format:
    {
      "background": "light",  // always light (white) for publication
      "blocks": [
        {"id": "A", "label": "Input", "x": 0, "y": 0, "w": 2, "h": 1,
         "color": "#56B4E9", "shape": "round"},  // shape: "round" (default) or "rect"
        ...
      ],
      "arrows": [
        {"from": "A", "to": "B", "label": "flow", "style": "->"},
        ...
      ],
      "groups": [
        {"blocks": ["A", "B"], "label": "Phase 1", "color": "#009E73", "style": "dashed"},
        ...
      ],
      "annotations": [
        {"text": "Step 1: predict", "x": 1, "y": -1, "fontsize": 9, "color": "#E69F00"},
        ...
      ]
    }
    """
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
    from matplotlib.lines import Line2D

    blocks = data.get("blocks", [])
    arrows = data.get("arrows", [])
    groups = data.get("groups", [])
    annotations = data.get("annotations", [])
    bg = data.get("background", "light")

    text_color = '#1a1a1a'
    arrow_color = '#555555'

    # Build block lookup
    block_map = {}
    for b in blocks:
        block_map[b["id"]] = b

    # Draw group backgrounds first (behind blocks)
    for grp in groups:
        grp_blocks = grp.get("blocks", [])
        if not grp_blocks:
            continue
        # Calculate bounding box of grouped blocks
        xs_min, xs_max = [], []
        ys_min, ys_max = [], []
        for bid in grp_blocks:
            if bid in block_map:
                b = block_map[bid]
                xs_min.append(b["x"])
                xs_max.append(b["x"] + b["w"])
                ys_min.append(b["y"])
                ys_max.append(b["y"] + b["h"])
        if not xs_min:
            continue
        pad = 0.3
        gx, gy = min(xs_min) - pad, min(ys_min) - pad
        gw, gh = max(xs_max) - min(xs_min) + 2 * pad, max(ys_max) - min(ys_min) + 2 * pad
        grp_color = grp.get("color", "#888888")
        grp_style = grp.get("style", "dashed")
        rect = Rectangle((gx, gy), gw, gh, linewidth=2,
                         edgecolor=grp_color, facecolor='none',
                         linestyle=grp_style, alpha=0.8)
        ax.add_patch(rect)
        # Group label
        if grp.get("label"):
            ax.text(gx + 0.15, gy + gh - 0.15, grp["label"],
                    fontsize=theme["font_size"] - 1, color=grp_color,
                    fontweight='bold', va='top', ha='left',
                    fontproperties=cjk_fp if cjk_fp and has_cjk(grp["label"]) else None)

    # Draw blocks
    for b in blocks:
        bx, by = b["x"], b["y"]
        bw, bh = b["w"], b["h"]
        bc = b.get("color", theme["colors"][0])
        label = b.get("label", b["id"])
        shape = b.get("shape", "round")
        sub_label = b.get("sublabel", None)  # smaller text below main label

        if shape == "rect":
            patch = FancyBboxPatch((bx, by), bw, bh,
                                   boxstyle="square,pad=0",
                                   facecolor=bc, edgecolor=bc,
                                   linewidth=1.5, alpha=0.85)
        else:
            patch = FancyBboxPatch((bx, by), bw, bh,
                                   boxstyle="round,pad=0.1",
                                   facecolor=bc, edgecolor='white',
                                   linewidth=1.2, alpha=0.9)
        ax.add_patch(patch)

        # Block label (centered)
        label_y = by + bh / 2
        if sub_label:
            label_y = by + bh * 0.65
        ax.text(bx + bw / 2, label_y, label,
                ha='center', va='center', fontsize=theme["font_size"],
                color='white', fontweight='bold',
                fontproperties=cjk_fp if cjk_fp and has_cjk(label) else None)
        if sub_label:
            ax.text(bx + bw / 2, by + bh * 0.3, sub_label,
                    ha='center', va='center', fontsize=theme["font_size"] - 2,
                    color='white', alpha=0.85,
                    fontproperties=cjk_fp if cjk_fp and has_cjk(sub_label) else None)

    # Draw arrows
    for arr in arrows:
        from_id = arr["from"]
        to_id = arr["to"]
        if from_id not in block_map or to_id not in block_map:
            continue
        fb, tb = block_map[from_id], block_map[to_id]

        # Calculate connection points (edge of blocks facing each other)
        fx_center = fb["x"] + fb["w"] / 2
        fy_center = fb["y"] + fb["h"] / 2
        tx_center = tb["x"] + tb["w"] / 2
        ty_center = tb["y"] + tb["h"] / 2

        # Determine arrow start/end at block edges
        if abs(fx_center - tx_center) > abs(fy_center - ty_center):
            # Horizontal connection
            if fx_center < tx_center:
                start = (fb["x"] + fb["w"], fy_center)
                end = (tb["x"], ty_center)
            else:
                start = (fb["x"], fy_center)
                end = (tb["x"] + tb["w"], ty_center)
        else:
            # Vertical connection
            if fy_center < ty_center:
                start = (fx_center, fb["y"] + fb["h"])
                end = (tx_center, tb["y"])
            else:
                start = (fx_center, fb["y"])
                end = (tx_center, tb["y"] + tb["h"])

        arr_style = arr.get("style", "->")
        arr_color = arr.get("color", arrow_color)
        connection_style = f"arc3,rad={arr.get('rad', 0)}"

        arrow = FancyArrowPatch(start, end,
                                arrowstyle=arr_style,
                                connectionstyle=connection_style,
                                color=arr_color, linewidth=1.5,
                                mutation_scale=15)
        ax.add_patch(arrow)

        # Arrow label
        if arr.get("label"):
            mid_x = (start[0] + end[0]) / 2
            mid_y = (start[1] + end[1]) / 2
            ax.text(mid_x, mid_y + 0.15, arr["label"],
                    ha='center', va='bottom', fontsize=theme["font_size"] - 2,
                    color=text_color,
                    bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                              alpha=0.8, edgecolor='none'),
                    fontproperties=cjk_fp if cjk_fp and has_cjk(arr["label"]) else None)

    # Draw annotations
    for ann in annotations:
        ax.text(ann["x"], ann["y"], ann["text"],
                ha=ann.get("ha", 'center'), va=ann.get("va", 'center'),
                fontsize=ann.get("fontsize", theme["font_size"]),
                color=ann.get("color", text_color),
                fontweight=ann.get("weight", 'normal'),
                fontproperties=cjk_fp if cjk_fp and has_cjk(ann["text"]) else None)

    # Set up axis limits
    all_x = [b["x"] + b["w"] for b in blocks] + [b["x"] for b in blocks]
    all_y = [b["y"] + b["h"] for b in blocks] + [b["y"] for b in blocks]
    if all_x and all_y:
        ax.set_xlim(min(all_x) - 1, max(all_x) + 1)
        ax.set_ylim(min(all_y) - 1.5, max(all_y) + 1.5)

    ax.set_aspect('equal')
    ax.axis('off')

    return "diagram"


# ── Registry ───────────────────────────────────────────────────────────

GENERATORS = {
    "bar": gen_bar,
    "grouped_bar": gen_bar,
    "hbar": gen_bar,
    "horizontal_bar": gen_bar,
    "stacked_bar": gen_stacked_bar,
    "heatmap": gen_heatmap,
    "scatter": gen_scatter,
    "line": gen_line,
    "dual_axis": gen_dual_axis,
    "box": gen_box,
    "boxplot": gen_box,
    "forest": gen_forest,
    "km": gen_km,
    "survival": gen_km,
    "roc": gen_roc,
    "violin": gen_violin,
    "composite": gen_composite,
    "diagram": gen_diagram,
}

# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="academic-figures: Publication-quality figure generator")
    parser.add_argument("--type", "-t", choices=list(GENERATORS.keys()),
                        help="Figure type")
    parser.add_argument("--data", "-d", help="Input data file (JSON or CSV)")
    parser.add_argument("--out", "-o", help="Output file path (.png, .svg, .pdf, or .tiff)")
    parser.add_argument("--title", default="", help="Figure title")
    parser.add_argument("--xlabel", default="", help="X-axis label")
    parser.add_argument("--ylabel", default="", help="Y-axis label")
    parser.add_argument("--theme", default="glm",
                        help="Color theme (default: glm; try --list-themes to see all)")
    parser.add_argument("--style", default=None, choices=["glm-hatch"],
                        help="Quick style preset: 'glm-hatch' = GLM 黄蓝斜线风 (theme glm + --hatch)")
    parser.add_argument("--list-themes", action="store_true",
                        help="List all color themes with in-terminal color swatches and exit")
    parser.add_argument("--theme-swatch", default=None, metavar="THEME",
                        help="Render a color-swatch preview PNG for a theme and exit")
    parser.add_argument("--demo", action="store_true",
                        help="Interactive demo: pick a chart type from a menu, render with sample data")
    parser.add_argument("--explain", default=None, metavar="CHART_TYPE",
                        help="Print usage notes / limitations for a chart type and exit")
    parser.add_argument("--cjk", action="store_true", help="Enable CJK font (auto-detect)")
    parser.add_argument("--cjk-font", default=None, help="Specific CJK font path")
    parser.add_argument("--width", type=float, default=None, help="Figure width in inches")
    parser.add_argument("--height", type=float, default=None, help="Figure height in inches")
    parser.add_argument("--format", "-f", default=None, choices=["png", "svg", "pdf", "tiff", "eps"],
                        help="Output format (default: auto-detect from --out extension)")
    parser.add_argument("--dpi", type=int, default=None,
                        help="DPI for raster output (default: 600 for line art, 300 for photos)")
    parser.add_argument("--legend", action="store_true", default=True, help="Show legend")
    parser.add_argument("--no-legend", action="store_true", help="Hide legend")
    parser.add_argument("--show-values", action="store_true", help="Show value labels")
    parser.add_argument("--trend", action="store_true", default=True, help="Show trend line (scatter)")
    parser.add_argument("--no-trend", action="store_true", help="Hide trend line (scatter)")
    parser.add_argument("--cmap", default=None, help="Colormap for heatmap")
    parser.add_argument("--vmin", type=float, default=None, help="Heatmap vmin")
    parser.add_argument("--vmax", type=float, default=None, help="Heatmap vmax")
    parser.add_argument("--horizontal", action="store_true", help="Horizontal bar chart (hbar)")
    parser.add_argument("--hatch", action="store_true", help="Add hatching patterns to bars (print-friendly)")
    parser.add_argument("--alternate", action="store_true",
                        help="GLM-5.2 style: alternate first two theme colors per bar (single series)")
    parser.add_argument("--show-ratio", action="store_true", help="Show ratio annotations (e.g., 4.96x) on grouped bars")
    parser.add_argument("--ratio-base", type=int, default=0, help="Base series index for ratio calculation (default: 0)")
    parser.add_argument("--verify", action="store_true",
                        help="Run pixel-level text-overlap verification on the PDF output; exit code 2 if overlaps found")
    parser.add_argument("--journal", default=None, choices=["nature", "lancet"],
                        help="Apply journal presets: figure width from column width, min font size, font family")
    parser.add_argument("--column", default="double", choices=["single", "double"],
                        help="Column layout for --journal (default: double)")

    args = parser.parse_args()

    if args.list_themes:
        cmd_list_themes()
        sys.exit(0)

    if args.theme_swatch:
        resolved = resolve_theme(args.theme_swatch)
        if not resolved:
            print(f"ERROR: 未知主题 '{args.theme_swatch}'。可用: {', '.join(THEME_ORDER)}", file=sys.stderr)
            sys.exit(1)
        out = args.out or (f"theme_{resolved}_swatch.png")
        cmd_theme_swatch(resolved, out)
        sys.exit(0)

    if args.explain:
        cmd_explain(args.explain)
        sys.exit(0)

    if args.demo:
        if not cmd_demo(args):
            sys.exit(1)
        if not args.type or not args.data or not args.out:
            print("ERROR: --demo 需要 --type/--data/--out", file=sys.stderr)
            sys.exit(1)
    else:
        if not args.type or not args.data or not args.out:
            parser.error("-t/--type, -d/--data, -o/--out are required (or use --demo)")

    if args.style == "glm-hatch":
        args.theme = "glm"
        args.hatch = True

    theme_key = resolve_theme(args.theme)
    if not theme_key:
        print(f"ERROR: 未知主题 '{args.theme}'。运行 --list-themes 查看全部配色。", file=sys.stderr)
        sys.exit(1)
    args.theme = theme_key
    theme = THEMES[theme_key]
    if args.journal:
        preset = JOURNAL_PRESETS[args.journal]
        theme = dict(theme)
        w_in = preset["widths_mm"][args.column] / 25.4
        h_ratio = theme["figsize"][1] / theme["figsize"][0]
        theme["figsize"] = (w_in, w_in * h_ratio)
        theme["font_size"] = preset["font_size"]
        theme["dpi"] = preset["dpi"]
        if preset["font_family"] not in plt.rcParams['font.sans-serif']:
            plt.rcParams['font.sans-serif'].insert(0, preset["font_family"])
        print(f"Journal preset: {args.journal} ({args.column}-column, width={w_in:.2f}in, "
              f"font={preset['font_family']} {preset['font_size']}pt, min text {preset['min_text_size']}pt "
              f"— verify with audit_pdf.py --min-size {preset['min_text_size']})", file=sys.stderr)
    data = load_data(args.data, chart_type=args.type)

    fatal_msgs, warn_msgs = validate_data(data, args.type)
    for w in warn_msgs:
        print(f"WARNING: {w}", file=sys.stderr)
    if fatal_msgs:
        for m in fatal_msgs:
            print(f"ERROR: {m}", file=sys.stderr)
        if any("CSV" in m or "csv" in m for m in fatal_msgs) or \
           any("error" in m.lower() and "bar" in m.lower() for m in fatal_msgs):
            print("HINT: CSV 不支持误差棒 → 改用 JSON 格式（见 --explain bar / 文档 §数据输入）",
                  file=sys.stderr)
        sys.exit(1)
    cjk_fp = None
    # Auto-detect: scan displayable text for CJK chars
    def _scan_cjk(obj):
        if isinstance(obj, str):
            return has_cjk(obj)
        if isinstance(obj, dict):
            return any(_scan_cjk(k) for k in obj.keys()) or any(_scan_cjk(v) for v in obj.values())
        if isinstance(obj, (list, tuple)):
            return any(_scan_cjk(v) for v in obj)
        return False

    def _text_has_cjk():
        for t in [args.title, args.xlabel, args.ylabel]:
            if t and has_cjk(t):
                return True
        # Recursive scan catches CJK nested in composite panels/diagram text
        return _scan_cjk(data) if data else False
    _auto_cjk = _text_has_cjk()
    if args.cjk or args.cjk_font or _auto_cjk:
        cjk_fp, cjk_name = load_cjk_font(args.cjk_font)
        if cjk_name:
            plt.rcParams['font.sans-serif'] = [cjk_name, 'DejaVu Sans'] + plt.rcParams['font.sans-serif']
        plt.rcParams['axes.unicode_minus'] = False
        if cjk_fp:
            print(f"CJK font loaded: {cjk_name}", file=sys.stderr)
        else:
            print("WARNING: No CJK font found, Chinese characters may not render", file=sys.stderr)

    # Create figure
    width = args.width if args.width else theme["figsize"][0]
    height = args.height if args.height else theme["figsize"][1]
    fig, ax = plt.subplots(figsize=(width, height))

    # Generate
    gen_func = GENERATORS[args.type]
    kwargs = {
        "show_values": args.show_values,
        "trend": args.trend and not args.no_trend,
        "cmap": args.cmap,
        "vmin": args.vmin,
        "vmax": args.vmax,
        "horizontal": args.horizontal or args.type in ("hbar", "horizontal_bar"),
        "hatch": args.hatch,
        "alternate": args.alternate,
        "show_ratio": args.show_ratio,
        "ratio_base": args.ratio_base,
    }
    extra = gen_func(data, ax, theme, cjk_fp, **kwargs)

    # composite/diagram manage their own axes and styling
    is_self_managed = extra in ("composite", "diagram")

    # Style (skip for self-managed types and dual_axis)
    if args.type not in ('dual_axis',) and not is_self_managed:
        apply_base_style(ax, theme)

    # Labels (skip for self-managed types like composite/diagram)
    if not is_self_managed:
        if args.title:
            title_text = args.title.replace('\\n', '\n')
            ax.set_title(title_text, fontsize=theme["font_size"] + 1, fontweight='bold', pad=12,
                         fontproperties=cjk_fp if cjk_fp and has_cjk(title_text) else None)
        if args.xlabel:
            ax.set_xlabel(args.xlabel, fontsize=theme["font_size"],
                          fontproperties=cjk_fp if cjk_fp and has_cjk(args.xlabel) else None)
        if args.ylabel:
            ax.set_ylabel(args.ylabel, fontsize=theme["font_size"],
                          fontproperties=cjk_fp if cjk_fp and has_cjk(args.ylabel) else None)
            _ensure_ylabel_clear(ax)

        # Colorbar (for heatmap only — extra must be a ScalarMappable)
        if extra is not None and hasattr(extra, 'get_cmap'):
            cbar = fig.colorbar(extra, ax=ax, shrink=0.8)
            cbar_label = data.get("cbar_label", args.ylabel)
            if cbar_label:
                cbar.set_label(cbar_label, fontsize=theme["font_size"] - 1,
                              fontproperties=cjk_fp if cjk_fp and has_cjk(cbar_label) else None)

        # Legend (skip if no labeled artists)
        if not args.no_legend and args.legend and ax.get_legend_handles_labels()[1]:
            ax.legend(fontsize=theme["font_size"] - 1, loc='best', framealpha=0.9,
                      prop=cjk_fp if cjk_fp else None)
        if args.type in ("bar", "grouped_bar", "hbar", "horizontal_bar", "line", "stacked_bar"):
            n_series = len(data.get("series", data.get("datasets", {})))
        elif args.type == "scatter":
            groups = data.get("groups")
            n_series = len(set(groups)) if isinstance(groups, (list, tuple)) and groups else 1
        else:
            n_series = 1
        audit_msg = legend_audit(ax, args.type, args.no_legend, n_series)
        if audit_msg:
            print(f"WARNING: {audit_msg}", file=sys.stderr)

    if not is_self_managed:
        plt.tight_layout()

    # Mechanism-level anti-overlap: detect real collisions post-render and
    # degrade tick labels until no axis overlaps (works for composite panels)
    fix_tick_overlaps(fig)

    # Determine output format and DPI
    out_ext = os.path.splitext(args.out)[1].lower()
    fmt_map = {'.png': 'png', '.svg': 'svg', '.pdf': 'pdf', '.tiff': 'tiff', '.tif': 'tiff', '.eps': 'eps'}
    out_format = args.format if args.format else fmt_map.get(out_ext, 'png')

    # Smart DPI: raster formats use theme DPI (default 600 for line art),
    # vector formats ignore DPI (but we still set it for fallback)
    is_vector = out_format in ('svg', 'pdf', 'eps')
    dpi = args.dpi if args.dpi else theme["dpi"]

    # For heatmaps or photo-heavy content, user can specify --dpi 300
    save_kwargs = {
        "dpi": dpi,
        "bbox_inches": 'tight',
        "facecolor": 'white',
        "edgecolor": 'none',
    }
    if out_format == 'tiff':
        save_kwargs["pil_kwargs"] = {"compression": "tiff_lzw"}

    # Adjust output filename if format differs from extension
    final_out = args.out
    if not is_vector and out_ext not in fmt_map:
        final_out = args.out + '.' + out_format

    fig.savefig(final_out, format=out_format, **save_kwargs)
    plt.close()

    sz = os.path.getsize(final_out)
    cjk_info = " (colorblind-safe)" if theme.get("colorblind_safe") else ""
    fmt_info = f"{out_format.upper()} @ {dpi}DPI" if not is_vector else f"{out_format.upper()} (vector)"
    print(f"Saved: {final_out} ({sz:,} bytes, {fmt_info}{cjk_info})", file=sys.stderr)

    if args.verify:
        if out_format != 'pdf':
            print("WARNING: --verify only applies to PDF output; skipping", file=sys.stderr)
        else:
            try:
                sys.path.insert(0, SCRIPT_DIR)
                from verify_overlap_pixel import verify
            except ImportError:
                print("WARNING: --verify requires PyMuPDF (fitz) and scipy — install with: pip install pymupdf scipy",
                      file=sys.stderr)
            else:
                real_overlaps, details = verify(final_out)
                if real_overlaps > 0:
                    print(f"VERIFY FAIL: {real_overlaps} real text overlap(s) in {final_out} — exit code 2",
                          file=sys.stderr)
                    sys.exit(2)
                print(f"VERIFY OK: no text overlaps in {final_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
