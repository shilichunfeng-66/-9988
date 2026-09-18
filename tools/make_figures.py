#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""make_figures.py — 本科毕业论文（理工科）图纸与曲线生成

铁律：**凡带精确信息（尺寸、编号、坐标、数值）的图，一律用代码画**，
AI 生图只能用于不含尺寸链的原理示意/概念图，且生成后必须人工核对。

图纸统一要求：300 dpi、白底、中文标签、线宽 ≥1.0 pt、坐标轴带物理量与单位、
图题在**图的下面**（五号加粗居中，与论文体例一致）。

用法
----
    python tools/make_figures.py --list
    python tools/make_figures.py --kind beam   --out outputs/图_简支梁
    python tools/make_figures.py --kind shaft  --out outputs/图_阶梯轴
    python tools/make_figures.py --kind flow   --out outputs/图_实验流程
    python tools/make_figures.py --kind frame  --out outputs/图_系统框图
    python tools/make_figures.py --kind curve  --csv outputs/xxx_data.csv --x 1 --y 2 --out outputs/图_曲线
"""
import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False
LW = 1.2


def _save(fig, path, caption):
    fig.text(0.5, 0.015, caption, ha="center", fontsize=10, weight="bold")
    fig.savefig(path, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def fig_beam(out, caption="图1　简支梁三点弯曲受力与尺寸示意"):
    """简支梁受力简图（含尺寸与支座标注）——代码绘制"""
    fig, ax = plt.subplots(figsize=(6.2, 2.8), dpi=300)
    L, hh = 100.0, 3.0
    ax.add_patch(Rectangle((0, 0), L, hh, fill=False, linewidth=LW, edgecolor="#222222"))
    # 左端固定铰支座（三角形）／右端活动铰支座（三角形+滚轮）
    for x, roller in ((0, False), (L, True)):
        ax.plot([x - 2.2, x + 2.2, x, x - 2.2], [-1.0, -1.0, 0, -1.0],
                color="#222222", linewidth=LW)
        ax.plot([x - 2.8, x + 2.8], [-1.6, -1.6], color="#222222", linewidth=LW)
        if roller:
            for dx in (-1.6, 0.0, 1.6):
                ax.plot([x + dx], [-1.3], marker="o", markersize=2.4, color="#222222")
    ax.annotate("", xy=(L / 2, hh + 0.4), xytext=(L / 2, hh + 3.6),
                arrowprops=dict(arrowstyle="-|>", linewidth=LW, color="#222222"))
    ax.text(L / 2 + 1.6, hh + 1.6, "F", fontsize=11)
    ax.annotate("", xy=(0, -2.0), xytext=(L, -2.0),
                arrowprops=dict(arrowstyle="<|-|>", linewidth=LW, color="#222222"))
    ax.text(L / 2 - 3, -2.9, "L = 800 mm", fontsize=10)
    ax.annotate("", xy=(L + 8, 0), xytext=(L + 8, hh),
                arrowprops=dict(arrowstyle="<|-|>", linewidth=LW, color="#222222"))
    ax.text(L + 10, hh / 2 - 0.4, "h = 20 mm", fontsize=10)
    ax.text(-3, -4.6, "支座 A（固定铰）", fontsize=9)
    ax.text(L - 8, -4.6, "支座 B（活动铰）", fontsize=9)
    ax.set_xlim(-8, L + 26)
    ax.set_ylim(-6.5, hh + 6.0)
    ax.axis("off")
    _save(fig, out + ".png", caption)
    return out + ".png"


def fig_shaft(out, caption="图2　阶梯轴结构与尺寸示意"):
    """阶梯轴示意图（含各段直径与长度）——代码绘制"""
    fig, ax = plt.subplots(figsize=(6.2, 2.6), dpi=300)
    segs = [(0, 30, 2.0), (30, 90, 3.2), (90, 130, 2.4)]   # (x0, x1, r)
    for x0, x1, r in segs:
        ax.add_patch(Rectangle((x0, -r), x1 - x0, 2 * r, fill=False,
                               linewidth=LW, edgecolor="#222222"))
        ax.plot([x0, x0], [-r, r], color="#222222", linewidth=LW)
    for x0, x1, r in segs:
        ax.annotate("", xy=(x0, 5.2), xytext=(x1, 5.2),
                    arrowprops=dict(arrowstyle="<|-|>", linewidth=1.0, color="#222222"))
        ax.text((x0 + x1) / 2 - 4, 5.6, f"{x1 - x0}", fontsize=9)
        ax.text((x0 + x1) / 2 - 5, -r - 2.2, f"φ{2 * r * 10:.0f}", fontsize=9)
    ax.text(60, 7.6, "各段长度（mm）", fontsize=9)
    ax.set_xlim(-10, 145)
    ax.set_ylim(-9, 10)
    ax.axis("off")
    _save(fig, out + ".png", caption)
    return out + ".png"


def fig_flow(out, caption="图3　虚拟实验流程"):
    """实验流程图——代码绘制"""
    steps = ["明确实验目的", "选择物理模型", "设定参数并注明来源",
             "运行仿真（固定种子）", "六项自洽检查", "输出数据表与图"]
    fig, ax = plt.subplots(figsize=(4.6, 6.0), dpi=300)
    y = 0
    for i, s in enumerate(steps):
        ax.add_patch(Rectangle((0, y), 62, 12, fill=False, linewidth=LW, edgecolor="#222222"))
        ax.text(31, y + 6, s, ha="center", va="center", fontsize=10)
        if i < len(steps) - 1:
            ax.add_patch(FancyArrowPatch((31, y), (31, y - 8),
                                         arrowstyle="-|>", mutation_scale=12,
                                         linewidth=LW, color="#222222"))
        y -= 20
    ax.set_xlim(-8, 70)
    ax.set_ylim(y + 12, 22)
    ax.axis("off")
    _save(fig, out + ".png", caption)
    return out + ".png"


def fig_frame(out, caption="图4　系统结构框图"):
    """系统框图——代码绘制"""
    boxes = [(6, 40, "数据层"), (60, 40, "算法层"), (114, 40, "应用层")]
    fig, ax = plt.subplots(figsize=(6.0, 2.4), dpi=300)
    for x, w, t in boxes:
        ax.add_patch(Rectangle((x, 0), w, 20, fill=False, linewidth=LW, edgecolor="#222222"))
        ax.text(x + w / 2, 10, t, ha="center", va="center", fontsize=11)
    for x in (46, 100):
        ax.add_patch(FancyArrowPatch((x, 10), (x + 14, 10), arrowstyle="-|>",
                                     mutation_scale=12, linewidth=LW, color="#222222"))
    ax.set_xlim(0, 160)
    ax.set_ylim(-6, 26)
    ax.axis("off")
    _save(fig, out + ".png", caption)
    return out + ".png"


def fig_curve(out, csv_path, xi, yi, caption="图5　实验数据曲线"):
    """从仿真/实验数据 CSV 直接出图——坐标轴自动带表头单位"""
    rows = list(csv.reader(open(csv_path, encoding="utf-8-sig")))
    header, data = rows[0], rows[1:]
    x = [float(r[xi - 1]) for r in data]
    y = [float(r[yi - 1]) for r in data]
    fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=300)
    ax.plot(x, y, marker="o", markersize=3.5, linewidth=LW, color="#1f3a93")
    ax.set_xlabel(header[xi - 1], fontsize=10)
    ax.set_ylabel(header[yi - 1], fontsize=10)
    ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    _save(fig, out + ".png", caption)
    return out + ".png"


KINDS = {
    "beam": ("简支梁受力与尺寸示意", fig_beam),
    "shaft": ("阶梯轴结构与尺寸示意", fig_shaft),
    "flow": ("虚拟实验流程", fig_flow),
    "frame": ("系统结构框图", fig_frame),
}


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--kind")
    ap.add_argument("--csv")
    ap.add_argument("--x", type=int, default=1)
    ap.add_argument("--y", type=int, default=2)
    ap.add_argument("--out", default="outputs/图")
    ap.add_argument("--caption")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args(argv[1:])

    if a.list or a.help or not a.kind:
        print(__doc__)
        print("可用图类型：")
        for k, (n, _) in KINDS.items():
            print(f"  {k:<7} {n}")
        print("  curve   从数据 CSV 出曲线（需 --csv --x --y）")
        return 0

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    if a.kind == "curve":
        if not a.csv:
            print("curve 需要 --csv 指定数据文件")
            return 2
        cap = a.caption or "图　实验数据曲线"
        p = fig_curve(a.out, a.csv, a.x, a.y, cap)
    elif a.kind in KINDS:
        name, fn = KINDS[a.kind]
        cap = a.caption or f"图　{name}"
        p = fn(a.out, cap)
    else:
        print("未知图类型：", a.kind)
        return 2
    print("已生成", p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
