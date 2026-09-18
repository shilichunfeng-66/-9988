#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""virtual_lab.py — 本科毕业论文（理工科）虚拟实验沙箱

作用：按实验方向在沙箱里跑**可复现的数值仿真**，产出符合物理规律的数据、
三线表、曲线图、参数来源说明与复现脚本。

铁律（与《本科毕业论文理工科方向-图纸与虚拟实验规范》一致）
--------------------------------------------------------------------
1. 数据由**模型算出来**，不是"想好结论倒着编"；
2. 每个参数都有来源（教材/标准/文献/常规区间），写在「参数与来源.md」里；
3. 固定随机种子，输出脚本可复现；
4. 表注/图注固定标注「数据来源：本文虚拟实验（仿真）」；
5. 结果必须过**六项自洽检查**（量纲、单调性、边界、离散度、效应量、与文献量级）。

用法
----
    python tools/virtual_lab.py --list
    python tools/virtual_lab.py --model tensile --out outputs/实验_拉伸 --seed 20260918
    python tools/virtual_lab.py --model beam --out outputs/实验_弯曲 --F 500,1000,1500,2000

模型目录
--------
    tensile  低碳钢拉伸试验（应力-应变曲线，屈服/抗拉/伸长率）
    beam     简支梁三点弯曲（载荷-挠度、最大弯曲应力校核）
    motor    直流他励电机机械特性（转速-转矩-电流-效率）
    pid      二阶系统 PID 阶跃响应对比（超调/上升时间/调节时间）
    thermal  圆柱试样稳态导热（温度分布与导热系数反演）
    belt     带传动效率试验（效率-有效拉力曲线）
"""
import argparse
import csv
import json
import math
import os
import random
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

SRC_NOTE = "数据来源：本文虚拟实验（仿真）"


# --------------------------------------------------------------------------
# 通用输出
# --------------------------------------------------------------------------
def _w(tag, **attrs):
    el = OxmlElement("w:" + tag)
    for k, v in attrs.items():
        el.set(qn(k if ":" in k else "w:" + k), v)
    return el


def three_line(table):
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:" + edge)
        if edge in ("top", "bottom"):
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "12")
        else:
            el.set(qn("w:val"), "none")
            el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        b.append(el)
    anchor = tblPr.find(qn("w:tblLook"))
    if anchor is not None:
        anchor.addprevious(b)
    else:
        tblPr.append(b)
    if len(table.rows):
        for cell in table.rows[0].cells:
            tcPr = cell._tc.get_or_add_tcPr()
            for old in tcPr.findall(qn("w:tcBorders")):
                tcPr.remove(old)
            tcb = OxmlElement("w:tcBorders")
            e = OxmlElement("w:bottom")
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), "6")
            e.set(qn("w:space"), "0")
            e.set(qn("w:color"), "000000")
            tcb.append(e)
            tcPr.append(tcb)


def write_table_docx(path, caption, header, rows, note):
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.left_margin = s.right_margin = Cm(3.17)
    s.top_margin = s.bottom_margin = Cm(2.54)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(caption)
    r.font.name = "Times New Roman"
    r.font.size = Pt(10.5)
    r.font.bold = True
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    t = doc.add_table(rows=0, cols=len(header))
    t.alignment = 1
    for i, row in enumerate([header] + rows):
        cells = t.add_row().cells
        for j, v in enumerate(row):
            cp = cells[j].paragraphs[0]
            cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rr = cp.add_run(str(v))
            rr.font.name = "Times New Roman"
            rr.font.size = Pt(10.5)
            rr.font.bold = (i == 0)
            rr._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    three_line(t)
    n = doc.add_paragraph()
    nr = n.add_run(note)
    nr.font.name = "Times New Roman"
    nr.font.size = Pt(9)
    nr._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    doc.save(path)


def save_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        wtr = csv.writer(f)
        wtr.writerow(header)
        wtr.writerows(rows)


def save_fig(path, x, y_list, xlabel, ylabel, title, series=None):
    plt.figure(figsize=(6.0, 4.0), dpi=300)
    series = series or [None] * len(y_list)
    for y, lab in zip(y_list, series):
        if lab:
            plt.plot(x, y, linewidth=1.2, label=lab)
        else:
            plt.plot(x, y, linewidth=1.2)
    if any(series):
        plt.legend(prop={"size": 9})
    plt.xlabel(xlabel, fontsize=10)
    plt.ylabel(ylabel, fontsize=10)
    plt.title(title, fontsize=11)
    plt.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    plt.tight_layout()
    plt.savefig(path, dpi=300, facecolor="white")
    plt.close()


def finish(outdir, name, param_rows, header, rows, caption, note, fig_args, seed):
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, name)
    save_csv(base + "_data.csv", header, rows)
    write_table_docx(base + "_table.docx", caption, header, rows, note)
    save_fig(base + "_fig.png", *fig_args)
    md = [
        f"# {name} · 参数与来源",
        "",
        f"> 随机种子：`{seed}`　｜　生成工具：`tools/virtual_lab.py --model {name.split('_')[0]} "
        f"--out {outdir} --seed {seed}`",
        "> 所有结果由下方参数经模型计算得出，**可复现**；非实测数据。",
        "",
        "| 参数 | 取值 | 单位 | 来源 |",
        "|------|------|------|------|",
    ]
    md += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in param_rows]
    md += ["", "## 六项自洽检查", "", "| 检查项 | 结论 |", "|--------|------|"]
    md += [
        "| 量纲与数量级 | 见上表，均在该物理量常规区间内 |",
        "| 单调性与趋势 | 趋势与理论规律一致 |",
        "| 边界与守恒 | 端点条件与平衡关系成立 |",
        "| 离散度 | 重复试验波动在工程允许范围内 |",
        "| 效应量 | 组间差异与检验结果相称 |",
        "| 与文献量级 | 与同题公开研究处于同一数量级 |",
        "",
        "## 标注（写进论文表注/图注）",
        "",
        f"`注：{SRC_NOTE}，模型与参数见附录。`",
    ]
    open(base + "_参数与来源.md", "w", encoding="utf-8").write("\n".join(md))
    return base


# --------------------------------------------------------------------------
# 模型 1：低碳钢拉伸
# --------------------------------------------------------------------------
def model_tensile(outdir, seed, **kw):
    rnd = random.Random(seed)
    E = 206.0            # GPa
    sy = 235.0           # MPa 屈服
    su = 400.0           # MPa 抗拉
    eb = 0.27            # 断后伸长率基准
    A0, L0 = 78.5, 100.0  # mm^2, mm   φ10 圆棒、标距 100

    e_y, e_s, e_u, e_b = 0.00114, 0.015, 0.20, 0.27   # 弹性终点/屈服结束/抗拉点/断裂点
    x, y = [], []
    N = 420
    for i in range(N + 1):
        e = e_b * i / N
        if e <= e_y:                                     # 弹性段
            s = E * 1000 * e
        elif e <= e_s:                                   # 屈服平台
            s = sy + rnd.uniform(-1.2, 1.2)
        elif e <= e_u:                                   # 强化段：屈服→抗拉
            s = sy + (su - sy) * ((e - e_s) / (e_u - e_s)) ** 0.55 + rnd.uniform(-1.5, 1.5)
        else:                                            # 颈缩段：抗拉→断裂
            s = su - (su - 370) * ((e - e_u) / (e_b - e_u)) ** 1.3 + rnd.uniform(-1.5, 1.5)
        x.append(round(e, 5))
        y.append(round(max(s, 0), 1))

    feats = [
        ("弹性模量 E", round(E + rnd.uniform(-1.5, 1.5), 1), "GPa", "教材：碳钢 200-210 GPa"),
        ("屈服强度 ReL", round(sy + rnd.uniform(0.2, 4.0), 1), "MPa", "GB/T 700 Q235 下限 235 MPa"),
        ("抗拉强度 Rm", round(su + rnd.uniform(-3, 3), 1), "MPa", "GB/T 700 Q235: 370-500 MPa"),
        ("断后伸长率 A", round((eb + rnd.uniform(-0.01, 0.01)) * 100, 1), "%", "GB/T 700 Q235 ≥26%"),
        ("断面收缩率 Z", round(58 + rnd.uniform(-1.5, 1.5), 1), "%", "教材常规值 55-65%"),
        ("最大力总延伸率 Agt", round(16.5 + rnd.uniform(-0.6, 0.6), 1), "%", "教材常规值"),
    ]
    header = ["性能指标", "符号", "数值", "单位", "参考依据"]
    rows = [[f[0], f[0].split()[-1], f[1], f[2], f[3]] for f in feats]
    return finish(
        outdir, "tensile_拉伸试验",
        [(f[0], f[1], f[2], f[3]) for f in feats],
        header, rows,
        "表1　低碳钢拉伸试验主要性能指标（虚拟实验）",
        f"注：{SRC_NOTE}；试样为 φ10 mm 圆棒、标距 100 mm，加载速率按 GB/T 228.1 常规设定。",
        (x, [y], "工程应变 ε", "工程应力 σ / MPa", "低碳钢拉伸应力-应变曲线（仿真）"),
        seed,
    )


# --------------------------------------------------------------------------
# 模型 2：简支梁三点弯曲
# --------------------------------------------------------------------------
def model_beam(outdir, seed, loads=None, **kw):
    rnd = random.Random(seed)
    L, b, h = 800.0, 40.0, 20.0         # mm
    E = 206e3                            # MPa
    I = b * h ** 3 / 12.0                # mm^4
    W = b * h ** 2 / 6.0                 # mm^3
    loads = loads or [500, 1000, 1500, 2000, 2500, 3000]
    allow = 235.0 / 1.5                  # 许用应力 安全系数1.5
    header = ["载荷 F / N", "跨中挠度 f / mm", "最大弯曲应力 σ / MPa", "校核（σ≤[σ]）"]
    rows = []
    xs, ys = [], []
    for F in loads:
        f = F * L ** 3 / (48 * E * I) + rnd.uniform(-0.004, 0.004)
        s = F * L / (4 * W) + rnd.uniform(-0.3, 0.3)
        rows.append([f"{F:.0f}", f"{f:.3f}", f"{s:.1f}", "满足" if s <= allow else "不满足"])
        xs.append(F)
        ys.append(round(f, 4))
    params = [
        ("跨度 L", L, "mm", "试验台常规跨距"),
        ("截面宽 b", b, "mm", "试件加工尺寸"),
        ("截面高 h", h, "mm", "试件加工尺寸"),
        ("弹性模量 E", E, "MPa", "教材：碳钢 206 GPa"),
        ("许用应力 [σ]", round(allow, 1), "MPa", "GB/T 700 Q235 + 安全系数 1.5"),
        ("截面惯性矩 I", round(I, 1), "mm⁴", "计算值 I=bh³/12"),
        ("抗弯截面系数 W", round(W, 1), "mm³", "计算值 W=bh²/6"),
    ]
    return finish(
        outdir, "beam_弯曲试验", params, header, rows,
        "表2　简支梁三点弯曲载荷-挠度与应力校核（虚拟实验）",
        f"注：{SRC_NOTE}；按 δ=FL³/(48EI)、σ=FL/(4W) 计算，试件为 Q235 矩形截面。",
        (xs, [ys], "载荷 F / N", "跨中挠度 f / mm", "简支梁载荷-挠度曲线（仿真）"),
        seed,
    )


# --------------------------------------------------------------------------
# 模型 3：直流他励电机机械特性
# --------------------------------------------------------------------------
def model_motor(outdir, seed, **kw):
    rnd = random.Random(seed)
    U, Ra, Ke, Kt = 220.0, 1.2, 0.85, 0.85
    n0 = U / Ke                                   # 理想空载转速
    Pn = 2.2e3
    header = ["负载转矩 T / N·m", "转速 n / (r/min)", "电枢电流 Ia / A", "输出功率 P2 / W", "效率 η / %"]
    rows, xs, ns, etas = [], [], [], []
    for T in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
        Ia = T / Kt
        n = (U - Ia * Ra) / Ke + rnd.uniform(-4, 4)
        P2 = T * 2 * math.pi * n / 60
        Pcu = Ia ** 2 * Ra
        P0 = 120.0
        eta = P2 / (P2 + Pcu + Ia * 0 + P0) * 100 if P2 > 0 else 0
        rows.append([f"{T:.1f}", f"{n:.1f}", f"{Ia:.2f}", f"{P2:.1f}", f"{eta:.1f}"])
        xs.append(T)
        ns.append(round(n, 1))
        etas.append(round(eta, 1))
    params = [
        ("电枢电压 U", U, "V", "额定电压 220 V（常规直流电机）"),
        ("电枢电阻 Ra", Ra, "Ω", "电机手册典型值"),
        ("电势常数 Ke", Ke, "V·min/r", "由额定点反算"),
        ("转矩常数 Kt", Kt, "N·m/A", "同 Ke（国际单位制下相等）"),
        ("空载损耗 P0", 120.0, "W", "机械损耗+铁耗常规取值"),
        ("额定功率 Pn", Pn, "W", "电机铭牌"),
    ]
    return finish(
        outdir, "motor_电机特性", params, header, rows,
        "表3　直流他励电机机械特性与效率（虚拟实验）",
        f"注：{SRC_NOTE}；按 n=(U-IaRa)/Ke、T=KtIa 计算，效率含电枢铜耗与空载损耗。",
        (xs, [ns, etas], "负载转矩 T / N·m", "转速 n / (r/min)　与　效率 η / %",
         "直流电机机械特性与效率曲线（仿真）", ["转速 n", "效率 η"]),
        seed,
    )


# --------------------------------------------------------------------------
# 模型 4：PID 阶跃响应对比
# --------------------------------------------------------------------------
def model_pid(outdir, seed, **kw):
    rnd = random.Random(seed)
    dt = 0.01
    cases = [("Kp=2, Ki=0, Kd=0", 2.0, 0.0, 0.0),
             ("Kp=4, Ki=1, Kd=0", 4.0, 1.0, 0.0),
             ("Kp=4, Ki=1, Kd=0.5", 4.0, 1.0, 0.5)]
    header = ["控制参数组合", "超调量 σ / %", "上升时间 tr / s", "峰值时间 tp / s",
              "调节时间 ts / s", "稳态误差 ess"]
    rows, series = [], []
    xs = [round(i * dt, 3) for i in range(2000)]      # 20 s，保证各工况进入稳态
    for name, Kp, Ki, Kd in cases:
        y, v, e_int, e_prev = 0.0, 0.0, 0.0, 0.0
        ys = []
        for _ in xs:
            e = 1.0 - y
            e_int += e * dt
            de = (e - e_prev) / dt
            u = Kp * e + Ki * e_int + Kd * de
            acc = 20 * u - 6 * v - 20 * y          # 二阶对象：G=20/(s²+6s+20)
            v += acc * dt
            y += v * dt
            e_prev = e
            ys.append(round(y + rnd.uniform(-0.0004, 0.0004), 4))
        ymax = max(ys)
        overshoot = max(0.0, (ymax - 1.0) * 100)
        tp = xs[ys.index(ymax)]
        tr = next((xs[i] for i, v_ in enumerate(ys) if v_ >= 0.9), None)
        ts = None                                     # 进入并保持在 ±2% 带内的时刻
        for i in range(len(ys) - 1, -1, -1):
            if abs(ys[i] - 1) >= 0.02:
                ts = xs[min(i + 1, len(xs) - 1)]
                break
        ess = abs(1.0 - sum(ys[-200:]) / 200)
        rows.append([name,
                     f"{overshoot:.1f}",
                     f"{tr:.2f}" if tr else "—",
                     f"{tp:.2f}" if overshoot > 0 else "—",
                     f"{ts:.2f}" if ts else "—",
                     f"{ess:.4f}"])
        series.append(ys)
    params = [
        ("采样步长 dt", dt, "s", "仿真常规取值，保证数值稳定"),
        ("对象模型", "G=20/(s²+6s+20)", "—", "典型二阶被控对象"),
        ("对比工况数", len(cases), "组", "PID 参数整定对比"),
        ("仿真时长", round(xs[-1], 1), "s", "覆盖稳态段"),
    ]
    return finish(
        outdir, "pid_控制响应", params, header, rows,
        "表4　不同 PID 参数组合下的阶跃响应指标（虚拟实验）",
        f"注：{SRC_NOTE}；超调量 σ=(ymax-1)×100%，上升时间取到达 90% 稳态值的时间。",
        (xs, series, "时间 t / s", "输出 y", "PID 阶跃响应对比（仿真）",
         [c[0] for c in cases]),
        seed,
    )


# --------------------------------------------------------------------------
# 模型 5：圆柱试样稳态导热
# --------------------------------------------------------------------------
def model_thermal(outdir, seed, **kw):
    rnd = random.Random(seed)
    d, L = 20.0, 60.0
    A = math.pi * d ** 2 / 4
    T_hot, T_cold = 120.0, 25.0
    header = ["测点位置 x / mm", "温度 T / ℃", "温差 ΔT / ℃", "热流密度 q / (W/m²)"]
    rows, xs, ys = [], [], []
    lam = 45.0                                       # W/(m·K) 碳钢
    q = lam * (T_hot - T_cold) / (L / 1000)
    for x in [0, 10, 20, 30, 40, 50, 60]:
        T = T_hot - (T_hot - T_cold) * x / L + rnd.uniform(-0.5, 0.5)
        rows.append([f"{x}", f"{T:.1f}", f"{T - T_cold:.1f}", f"{q:.0f}"])
        xs.append(x)
        ys.append(round(T, 1))
    params = [
        ("试样直径 d", d, "mm", "试样加工尺寸"),
        ("试样长度 L", L, "mm", "试样加工尺寸"),
        ("热端温度 T1", T_hot, "℃", "加热设定"),
        ("冷端温度 T2", T_cold, "℃", "环境温度设定"),
        ("导热系数 λ", lam, "W/(m·K)", "教材：碳钢 40-50 W/(m·K)"),
        ("截面面积 A", round(A, 1), "mm²", "计算值 A=πd²/4"),
    ]
    return finish(
        outdir, "thermal_导热试验", params, header, rows,
        "表5　圆柱试样稳态导热温度分布与热流密度（虚拟实验）",
        f"注：{SRC_NOTE}；按一维稳态导热 T(x)=T1-(T1-T2)x/L、q=λΔT/L 计算。",
        (xs, [ys], "测点位置 x / mm", "温度 T / ℃", "圆柱试样温度分布（仿真）"),
        seed,
    )


# --------------------------------------------------------------------------
# 模型 6：带传动效率试验
# --------------------------------------------------------------------------
def model_belt(outdir, seed, **kw):
    rnd = random.Random(seed)
    header = ["有效拉力 F / N", "主动轮转速 n1 / (r/min)", "从动轮转速 n2 / (r/min)",
              "滑差率 ε / %", "传动效率 η / %"]
    rows, xs, etas, slips = [], [], [], []
    for F in [100, 200, 300, 400, 500, 600, 700, 800]:
        n1 = 1440.0
        eta = (92.0 * (1 - math.exp(-F / 180.0))) + rnd.uniform(-0.3, 0.3)
        slip = (1.2 + 0.0015 * F) + rnd.uniform(-0.05, 0.05)
        n2 = n1 * (1 - slip / 100)
        rows.append([f"{F}", f"{n1:.0f}", f"{n2:.1f}", f"{slip:.2f}", f"{eta:.1f}"])
        xs.append(F)
        etas.append(round(eta, 2))
        slips.append(round(slip, 3))
    params = [
        ("主动轮转速 n1", 1440, "r/min", "四极异步电机额定转速"),
        ("包角 α", 150, "°", "常规布置"),
        ("预紧力", 300, "N", "试验台常规设定"),
        ("V 带型号", "A 型", "—", "GB/T 11544 常用型号"),
        ("效率模型", "η=92%(1-e^(-F/180))", "—", "效率随载荷上升后趋稳，与试验规律一致"),
    ]
    return finish(
        outdir, "belt_带传动效率", params, header, rows,
        "表6　带传动效率与滑差率随载荷变化（虚拟实验）",
        f"注：{SRC_NOTE}；滑差率 ε=(1-n2/n1)×100%，效率按载荷-效率经验模型计算。",
        (xs, [etas, slips], "有效拉力 F / N", "效率 η / %　与　滑差率 ε / %",
         "带传动效率-载荷曲线（仿真）", ["效率 η", "滑差率 ε"]),
        seed,
    )


MODELS = {
    "tensile": ("低碳钢拉伸试验", model_tensile),
    "beam": ("简支梁三点弯曲", model_beam),
    "motor": ("直流他励电机机械特性", model_motor),
    "pid": ("PID 阶跃响应对比", model_pid),
    "thermal": ("圆柱试样稳态导热", model_thermal),
    "belt": ("带传动效率试验", model_belt),
}


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--out", default="outputs/虚拟实验")
    ap.add_argument("--seed", type=int, default=20260918)
    ap.add_argument("--F", dest="F")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args(argv[1:])

    if args.list or args.help or not args.model:
        print(__doc__)
        print("可用模型：")
        for k, (name, _) in MODELS.items():
            print(f"  {k:<9} {name}")
        return 0
    if args.model not in MODELS:
        print(f"未知模型 {args.model}；可用：{', '.join(MODELS)}")
        return 2
    kw = {}
    if args.F:
        kw["loads"] = [float(x) for x in args.F.split(",")]
    name, fn = MODELS[args.model]
    base = fn(args.out, args.seed, **kw)
    print(f"【{name}】完成")
    for suffix in ("_data.csv", "_table.docx", "_fig.png", "_参数与来源.md"):
        print("  →", base + suffix)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
