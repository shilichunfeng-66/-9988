#!/usr/bin/env python3
"""Regression test suite for academic-figures scripts.

Runs on stdlib `unittest` only (no pytest dependency).
Coverage:
  1. Smoke test — all 14 chart types generate via the real CLI (exit 0 + file exists)
  2. validate_data() — fatal/warning detection per chart family
  3. load_data() — CSV edge cases (mixed numeric/text, scatter/box long format)
  4. has_cjk() — CJK detection
  5. legend_audit() — empty-legend detection via real matplotlib axes
  6. audit_pdf.py — PDF font-size audit behavior
  7. gen_legend.py — journal legend text for all chart types

Usage:
    python3 tests/run_tests.py            # run all
    python3 tests/run_tests.py -v         # verbose
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPT_DIR)

import gen_figure  # noqa: E402
import gen_legend  # noqa: E402
import audit_pdf  # noqa: E402

GEN = os.path.join(SCRIPT_DIR, "gen_figure.py")


# ── minimal valid sample data per chart family ─────────────────────────

SAMPLE = {
    "bar": {"labels": ["A", "B", "C"], "series": {"Ctrl": [1.0, 2.0, 3.0], "Treated": [2.5, 1.5, 4.0]}},
    "hbar": {"labels": ["A", "B"], "series": {"Ctrl": [1.0, 2.0], "Treated": [2.5, 1.5]}},
    "stacked_bar": {"labels": ["A", "B"], "series": {"x": [1.0, 2.0], "y": [0.5, 1.0]}},
    "heatmap": {"matrix": [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]},
    "scatter": {"x": [1.0, 2.0, 3.0, 4.0], "y": [2.0, 4.0, 3.5, 5.0],
                "groups": ["a", "a", "b", "b"]},
    "line": {"labels": ["t0", "t1", "t2"], "series": {"S1": [1.0, 2.0, 3.0], "S2": [3.0, 2.5, 2.0]}},
    "dual_axis": {"labels": ["A", "B"], "left": {"Temp": [20.0, 30.0]}, "right": {"Count": [5, 8]}},
    "box": {"labels": ["G1", "G2"], "series": {"G1": [1.0, 2.0, 3.0], "G2": [2.0, 3.0, 4.0]}},
    "forest": {"labels": ["Study1", "Study2"], "estimates": [1.2, 0.8],
               "ci_low": [0.9, 0.5], "ci_high": [1.5, 1.1]},
    "km": {"groups": {"Placebo": [[0.0, 1.0], [5.0, 0.8], [10.0, 0.6]],
                      "Drug": [[0.0, 1.0], [5.0, 0.9], [10.0, 0.8]]}},
    "roc": {"curves": [{"fpr": [0.0, 0.5, 1.0], "tpr": [0.0, 0.7, 1.0], "label": "Model A",
                        "auc": 0.85}]},
    "violin": {"labels": ["G1", "G2"], "series": {"G1": [1.0, 2.0, 3.0, 2.5],
                                                  "G2": [2.0, 3.0, 4.0, 3.5]}},
    "composite": {"layout": [1, 2], "panels": [
        {"type": "bar", "data": {"labels": ["A", "B"], "series": {"S": [1.0, 2.0]}},
         "title": "Panel A", "pos": [0, 0]},
        {"type": "line", "data": {"labels": ["t0", "t1"], "series": {"S": [1.0, 2.0]}},
         "title": "Panel B", "pos": [0, 1]}]},
    "diagram": {"blocks": [
        {"id": "A", "label": "Input", "x": 0, "y": 0, "w": 2, "h": 1},
        {"id": "B", "label": "Output", "x": 3, "y": 0, "w": 2, "h": 1}],
        "arrows": [{"from": "A", "to": "B"}]},
}

# Canonical type names (aliases resolved) — the 14 distinct chart families
SMOKE_TYPES = ["bar", "hbar", "stacked_bar", "heatmap", "scatter", "line", "dual_axis",
               "box", "forest", "km", "roc", "violin", "composite", "diagram"]


# ── 1. CLI smoke tests ─────────────────────────────────────────────────

class TestSmokeCLI(unittest.TestCase):
    """Every chart type renders through the real CLI."""

    maxDiff = None

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="af_smoke_")

    def _run(self, chart_type, extra=None):
        data_path = os.path.join(self.tmp, f"{chart_type}.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE[chart_type], f)
        out = os.path.join(self.tmp, f"{chart_type}.png")
        cmd = [sys.executable, GEN, "--type", chart_type, "--data", data_path,
               "--out", out, "--dpi", "150"]
        if extra:
            cmd += extra
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return proc, out

    def test_all_14_chart_types_render(self):
        for ct in SMOKE_TYPES:
            with self.subTest(chart_type=ct):
                proc, out = self._run(ct)
                self.assertEqual(proc.returncode, 0,
                                 f"{ct} failed: rc={proc.returncode}\n"
                                 f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")
                self.assertTrue(os.path.exists(out), f"{ct}: output file missing")
                self.assertGreater(os.path.getsize(out), 0, f"{ct}: empty output")

    def test_fatal_data_exits_1(self):
        """Missing required field -> exit code 1, ERROR printed."""
        data_path = os.path.join(self.tmp, "bad.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump({"labels": ["A", "B"]}, f)  # no 'series'
        out = os.path.join(self.tmp, "bad.png")
        proc = subprocess.run(
            [sys.executable, GEN, "--type", "bar", "--data", data_path, "--out", out],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ERROR", proc.stderr)
        self.assertFalse(os.path.exists(out))

    def test_verify_pdf_exit_0_clean(self):
        """--verify on a clean PDF -> exit 0 + VERIFY OK."""
        data_path = os.path.join(self.tmp, "v.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE["bar"], f)
        out = os.path.join(self.tmp, "v.pdf")
        proc = subprocess.run(
            [sys.executable, GEN, "--type", "bar", "--data", data_path, "--out", out,
             "--verify"],
            capture_output=True, text=True, timeout=180)
        self.assertEqual(proc.returncode, 0,
                         f"verify failed: rc={proc.returncode}\nSTDERR: {proc.stderr}")
        self.assertIn("VERIFY OK", proc.stderr)

    def test_journal_preset_applies(self):
        """--journal nature --column double -> narrower figure (89mm double column)."""
        data_path = os.path.join(self.tmp, "j.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE["bar"], f)
        out = os.path.join(self.tmp, "j.png")
        proc = subprocess.run(
            [sys.executable, GEN, "--type", "bar", "--data", data_path, "--out", out,
             "--journal", "nature", "--column", "double"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Journal preset: nature (double-column", proc.stderr)

    def test_cjk_auto_detection_in_series_keys(self):
        """CJK in series names (dict keys) must trigger font loading, not tofu."""
        data_path = os.path.join(self.tmp, "cjk.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump({"labels": ["A", "B"],
                       "series": {"对照": [1.0, 2.0], "处理": [2.5, 1.5]}}, f)
        out = os.path.join(self.tmp, "cjk.png")
        proc = subprocess.run(
            [sys.executable, GEN, "--type", "bar", "--data", data_path, "--out", out],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CJK font loaded", proc.stderr,
                      "CJK in series dict keys must auto-load a CJK font")
        self.assertNotIn("Glyph", proc.stderr, "no missing-glyph tofu warnings expected")


# ── 2. validate_data() unit tests ──────────────────────────────────────

class TestValidateData(unittest.TestCase):
    """(fatal, warn) split per chart family."""

    def _fatal(self, data, ct):
        return validate_fatal(data, ct)

    def test_bar_missing_series_fatal(self):
        f, w = gen_figure.validate_data({"labels": ["A", "B"]}, "bar")
        self.assertTrue(any("series" in m for m in f))

    def test_bar_length_mismatch_fatal(self):
        f, _ = gen_figure.validate_data(
            {"labels": ["A", "B", "C"], "series": {"S": [1.0, 2.0]}}, "bar")
        self.assertTrue(any("length" in m.lower() for m in f))

    def test_bar_all_equal_warning(self):
        _, w = gen_figure.validate_data(
            {"labels": ["A", "B"], "series": {"S": [5.0, 5.0]}}, "bar")
        self.assertTrue(any("flat" in m for m in w))

    def test_bar_empty_series_fatal(self):
        f, _ = gen_figure.validate_data(
            {"labels": ["A", "B"], "series": {"S": []}}, "bar")
        self.assertTrue(any("empty" in m for m in f))

    def test_heatmap_missing_matrix_fatal(self):
        f, _ = gen_figure.validate_data({"labels": ["A"]}, "heatmap")
        self.assertTrue(any("matrix" in m for m in f))

    def test_heatmap_ragged_rows_fatal(self):
        f, _ = gen_figure.validate_data({"matrix": [[1.0, 2.0], [3.0]]}, "heatmap")
        self.assertTrue(any("ragged" in m.lower() or "unequal" in m.lower() for m in f))

    def test_heatmap_all_equal_warning(self):
        _, w = gen_figure.validate_data({"matrix": [[2.0, 2.0], [2.0, 2.0]]}, "heatmap")
        self.assertTrue(any("identical" in m for m in w))

    def test_scatter_missing_x_fatal(self):
        f, _ = gen_figure.validate_data({"y": [1.0, 2.0]}, "scatter")
        self.assertTrue(any("x" in m for m in f))

    def test_scatter_length_mismatch_fatal(self):
        f, _ = gen_figure.validate_data({"x": [1.0, 2.0], "y": [1.0]}, "scatter")
        self.assertTrue(any("length" in m.lower() for m in f))

    def test_scatter_all_x_equal_warning(self):
        _, w = gen_figure.validate_data(
            {"x": [3.0, 3.0, 3.0], "y": [1.0, 2.0, 3.0]}, "scatter")
        self.assertTrue(any("identical" in m for m in w))

    def test_forest_estimate_outside_ci_warning(self):
        _, w = gen_figure.validate_data(
            {"estimates": [5.0], "ci_low": [0.0], "ci_high": [1.0]}, "forest")
        self.assertTrue(any("outside CI" in m for m in w))

    def test_forest_length_mismatch_fatal(self):
        f, _ = gen_figure.validate_data(
            {"estimates": [1.0, 2.0], "ci_low": [0.0], "ci_high": [1.0, 2.0]}, "forest")
        self.assertTrue(any("differ" in m for m in f))

    def test_km_non_monotonic_time_warning(self):
        _, w = gen_figure.validate_data(
            {"groups": {"G": [[0.0, 1.0], [10.0, 0.5], [5.0, 0.8]]}}, "km")
        self.assertTrue(any("chronological" in m or "non-increasing" in m for m in w))

    def test_km_missing_groups_fatal(self):
        f, _ = gen_figure.validate_data({"labels": ["A"]}, "km")
        self.assertTrue(any("km requires" in m for m in f))

    def test_roc_non_monotonic_fpr_warning(self):
        _, w = gen_figure.validate_data(
            {"curves": [{"fpr": [0.0, 0.9, 0.3], "tpr": [0.0, 0.7, 1.0]}]}, "roc")
        self.assertTrue(any("monotonic" in m for m in w))

    def test_roc_auc_out_of_range_warning(self):
        _, w = gen_figure.validate_data(
            {"curves": [{"fpr": [0.0, 1.0], "tpr": [0.0, 1.0], "auc": 1.5}]}, "roc")
        self.assertTrue(any("auc" in m.lower() for m in w))

    def test_roc_missing_data_fatal(self):
        f, _ = gen_figure.validate_data({"labels": ["A"]}, "roc")
        self.assertTrue(any("curves" in m or "fpr" in m for m in f))

    def test_dual_axis_missing_left_fatal(self):
        f, _ = gen_figure.validate_data(
            {"labels": ["A", "B"], "right": {"R": [1.0, 2.0]}}, "dual_axis")
        self.assertTrue(any("left" in m for m in f))

    def test_composite_missing_panels_fatal(self):
        f, _ = gen_figure.validate_data({"layout": [1, 1]}, "composite")
        self.assertTrue(any("panels" in m for m in f))

    def test_composite_panel_missing_type_fatal(self):
        f, _ = gen_figure.validate_data(
            {"panels": [{"data": {"labels": ["A"], "series": {"S": [1.0]}}}]}, "composite")
        self.assertTrue(any("type" in m for m in f))

    def test_diagram_missing_blocks_fatal(self):
        f, _ = gen_figure.validate_data({"background": "light"}, "diagram")
        self.assertTrue(any("blocks" in m for m in f))

    def test_not_a_dict_fatal(self):
        f, _ = gen_figure.validate_data([1, 2, 3], "bar")
        self.assertTrue(any("dict" in m for m in f))


# ── 3. load_data() CSV edge cases ──────────────────────────────────────

class TestLoadDataCSV(unittest.TestCase):
    """CSV parsing: long-format scatter/box, mixed numeric/text, TSV."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="af_csv_")
        self._n = 0

    def _csv(self, content, name="data.csv"):
        self._n += 1
        p = os.path.join(self.tmp, f"{self._n}_{name}")
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def test_scatter_long_format_groups(self):
        p = self._csv("x,y,group\n1,2,A\n2,4,A\n3,6,B\n4,8,B\n")
        d = gen_figure.load_data(p, chart_type="scatter")
        self.assertEqual(d["x"], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(d["y"], [2.0, 4.0, 6.0, 8.0])
        self.assertEqual(d["groups"], ["A", "A", "B", "B"])

    def test_box_long_format(self):
        p = self._csv("group,value\nCtrl,1\nCtrl,2\nCtrl,3\nDrug,4\nDrug,5\nDrug,6\n")
        d = gen_figure.load_data(p, chart_type="box")
        self.assertEqual(list(d["labels"]), ["Ctrl", "Drug"])
        self.assertEqual(d["series"]["Ctrl"], [1.0, 2.0, 3.0])
        self.assertEqual(d["series"]["Drug"], [4.0, 5.0, 6.0])

    def test_mixed_numeric_text_rows_skipped(self):
        """Non-numeric cells in numeric columns -> those rows dropped, rest parsed."""
        p = self._csv("label,value\nA,1\nB,NA\nC,3\n")
        d = gen_figure.load_data(p, chart_type="bar")
        self.assertEqual(d["labels"], ["A", "C"])
        self.assertEqual(d["series"]["value"], [1.0, 3.0])

    def test_tsv_delimiter(self):
        p = self._csv("label\tvalue\nA\t1\nB\t2\n", name="data.tsv")
        d = gen_figure.load_data(p, chart_type="bar")
        self.assertEqual(d["labels"], ["A", "B"])
        self.assertEqual(d["series"]["value"], [1.0, 2.0])

    def test_unsupported_format_raises(self):
        p = self._csv("a\n1\n", name="data.xlsx")
        with self.assertRaises(ValueError):
            gen_figure.load_data(p)

    def test_json_load(self):
        p = os.path.join(self.tmp, "d.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"labels": ["A"], "series": {"S": [1.0]}}, f)
        d = gen_figure.load_data(p)
        self.assertEqual(d["series"]["S"], [1.0])


# ── 4. has_cjk() ───────────────────────────────────────────────────────

class TestHasCJK(unittest.TestCase):
    def test_chinese_true(self):
        self.assertTrue(gen_figure.has_cjk("细胞因子"))
        self.assertTrue(gen_figure.has_cjk("IL-6 信号通路"))
        self.assertTrue(gen_figure.has_cjk("𠀀"))  # CJK Ext-B (U+20000) via \U00020000

    def test_ascii_false(self):
        self.assertFalse(gen_figure.has_cjk("IL-6 signaling"))
        self.assertFalse(gen_figure.has_cjk(""))

    def test_japanese_kanji_true(self):
        self.assertTrue(gen_figure.has_cjk("免疫応答"))


# ── 5. legend_audit() ──────────────────────────────────────────────────

class TestLegendAudit(unittest.TestCase):
    """Multi-series without labels must warn; exemptions respected."""

    def _ax(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        self.addCleanup(plt.close, fig)
        return ax

    def test_multi_series_no_labels_warns(self):
        ax = self._ax()
        ax.bar([0, 1], [1.0, 2.0])          # no label
        ax.bar([0.5, 1.5], [2.0, 1.0])      # no label
        msg = gen_figure.legend_audit(ax, "bar", no_legend=False, n_series=2)
        self.assertIsNotNone(msg)
        self.assertIn("legend", msg)

    def test_multi_series_with_labels_ok(self):
        ax = self._ax()
        ax.bar([0, 1], [1.0, 2.0], label="A")
        ax.bar([0.5, 1.5], [2.0, 1.0], label="B")
        self.assertIsNone(gen_figure.legend_audit(ax, "bar", no_legend=False, n_series=2))

    def test_no_legend_flag_skips(self):
        ax = self._ax()
        ax.bar([0, 1], [1.0, 2.0])
        self.assertIsNone(gen_figure.legend_audit(ax, "bar", no_legend=True, n_series=2))

    def test_single_series_ok(self):
        ax = self._ax()
        ax.bar([0, 1], [1.0, 2.0])
        self.assertIsNone(gen_figure.legend_audit(ax, "bar", no_legend=False, n_series=1))

    def test_exempt_types_ok(self):
        ax = self._ax()
        ax.bar([0, 1], [1.0, 2.0])
        ax.bar([0.5, 1.5], [2.0, 1.0])
        for ct in ("box", "boxplot", "violin", "heatmap", "forest",
                   "composite", "diagram", "dual_axis"):
            with self.subTest(chart_type=ct):
                self.assertIsNone(gen_figure.legend_audit(ax, ct, no_legend=False, n_series=2))


# ── 6. audit_pdf.py ────────────────────────────────────────────────────

class TestAuditPdf(unittest.TestCase):
    """Audit finds undersized spans; thresholds work."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="af_audit_")

    def _gen_pdf(self, journal=None):
        """Render a small bar PDF via the CLI; return its path."""
        data_path = os.path.join(self.tmp, "d.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE["bar"], f)
        out = os.path.join(self.tmp, "fig.pdf")
        cmd = [sys.executable, GEN, "--type", "bar", "--data", data_path, "--out", out]
        if journal:
            cmd += ["--journal", journal, "--column", "double"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return out

    def test_default_7pt_audit_clean(self):
        pdf = self._gen_pdf()
        offenders = audit_pdf.audit(pdf, min_size=7.0)
        self.assertEqual(offenders, [])

    def test_strict_threshold_finds_small_text(self):
        pdf = self._gen_pdf()
        offenders = audit_pdf.audit(pdf, min_size=12.0)
        self.assertGreater(len(offenders), 0)

    def test_journal_nature_6pt_clean(self):
        pdf = self._gen_pdf(journal="nature")
        offenders = audit_pdf.audit(pdf, min_size=6.0)
        self.assertEqual(offenders, [])


# ── 7. gen_legend.py ───────────────────────────────────────────────────

class TestGenLegend(unittest.TestCase):
    """Journal-format legend for every chart type."""

    def test_all_types_return_figure_text(self):
        for ct in SMOKE_TYPES:
            with self.subTest(chart_type=ct):
                txt = gen_legend.legend_for(SAMPLE[ct], ct, title="Main result")
                self.assertIn("Figure:", txt)
                self.assertNotIn("..", txt, f"{ct}: double period")
                self.assertTrue(txt.endswith("."))

    def test_km_log_rank_note(self):
        data = dict(SAMPLE["km"])
        data["log_rank"] = {"p": 0.03}
        txt = gen_legend.legend_for(data, "km", title="Survival")
        self.assertIn("Log-rank P = 0.03", txt)

    def test_forest_heterogeneity_note(self):
        data = dict(SAMPLE["forest"])
        data["heterogeneity"] = {"I2": 0.42}
        txt = gen_legend.legend_for(data, "forest", title="Meta")
        self.assertIn("I² = 42%", txt)

    def test_error_bars_note(self):
        data = dict(SAMPLE["bar"])
        data["errors"] = {"Ctrl": [0.1, 0.2, 0.1], "Treated": [0.2, 0.1, 0.2]}
        txt = gen_legend.legend_for(data, "bar", title="Bars")
        self.assertIn("Error bars indicate s.e.m.", txt)

    def test_composite_panel_letters(self):
        txt = gen_legend.legend_for(SAMPLE["composite"], "composite", title="Comp")
        self.assertIn("a, Panel A", txt)
        self.assertIn("b, Panel B", txt)

    def test_roc_auc_note(self):
        txt = gen_legend.legend_for(SAMPLE["roc"], "roc", title="ROC")
        self.assertIn("AUC values: 0.850", txt)


# ── v2.0.1: theme system, style presets, demo/explain, setup_env ───────

class TestV201ThemeSystem(unittest.TestCase):
    def test_default_theme_is_glm(self):
        self.assertEqual(gen_figure.resolve_theme(None), "glm")
        self.assertEqual(gen_figure.resolve_theme(""), "glm")

    def test_classic_alias_kept(self):
        self.assertEqual(gen_figure.resolve_theme("default"), "glm")
        self.assertEqual(gen_figure.resolve_theme("classic"), "classic")
        self.assertIn("classic", gen_figure.THEMES)

    def test_aliases_resolve(self):
        cases = {"okabe": "okabe-ito", "colorblind": "okabe-ito",
                 "glm-blog": "glm", "glmblog": "glm", "npg": "nature",
                 "matplotlib": "classic"}
        for alias, canonical in cases.items():
            with self.subTest(alias=alias):
                self.assertEqual(gen_figure.resolve_theme(alias), canonical)

    def test_case_insensitive_and_prefix(self):
        self.assertEqual(gen_figure.resolve_theme("OKABE"), "okabe-ito")
        self.assertEqual(gen_figure.resolve_theme("Nat"), "nature")
        self.assertEqual(gen_figure.resolve_theme("Conserv"), "conservative")

    def test_unknown_theme_none(self):
        self.assertIsNone(gen_figure.resolve_theme("nope"))

    def test_all_themes_have_colors(self):
        for key, theme in gen_figure.THEMES.items():
            with self.subTest(theme=key):
                self.assertTrue(theme["colors"])
                self.assertGreaterEqual(len(theme["colors"]), 2)


class TestV201StylePreset(unittest.TestCase):
    def _render(self, chart_type, extra=None):
        data_path = os.path.join(tempfile.gettempdir(), f"v201_{chart_type}.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE[chart_type], f)
        out = os.path.join(tempfile.gettempdir(), f"v201_{chart_type}.png")
        cmd = [sys.executable, GEN, "-t", chart_type, "-d", data_path, "-o", out]
        if extra:
            cmd += extra
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        exists = os.path.exists(out)
        if exists:
            os.remove(out)
        os.remove(data_path)
        return r, exists

    def test_style_glm_hatch_bar(self):
        r, ok = self._render("bar", ["--style", "glm-hatch"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(ok)
        self.assertIn("colorblind-safe", r.stderr)

    def test_style_glm_hatch_stacked(self):
        r, ok = self._render("stacked_bar", ["--style", "glm-hatch"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(ok)

    def test_style_glm_hatch_forest(self):
        r, ok = self._render("forest", ["--style", "glm-hatch"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(ok)

    def test_hatch_flag_alone(self):
        r, ok = self._render("bar", ["--hatch"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(ok)

    def test_theme_glm_explicit(self):
        r, ok = self._render("bar", ["--theme", "glm"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(ok)

    def test_theme_alias_okabe(self):
        r, ok = self._render("bar", ["--theme", "okabe"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(ok)


class TestV201MetaCommands(unittest.TestCase):
    def test_list_themes_exits_0(self):
        r = subprocess.run([sys.executable, GEN, "--list-themes"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("glm", r.stdout)

    def test_explain_bar(self):
        r = subprocess.run([sys.executable, GEN, "--explain", "bar"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("CSV", r.stdout)

    def test_explain_unknown_exits_1(self):
        r = subprocess.run([sys.executable, GEN, "--explain", "nope"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)

    def test_theme_swatch_renders(self):
        out = os.path.join(tempfile.gettempdir(), "v201_swatch.png")
        r = subprocess.run([sys.executable, GEN, "--theme-swatch", "glm", "-o", out],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(out))
        os.remove(out)

    def test_demo_menu_default(self):
        r = subprocess.run([sys.executable, GEN, "--demo"],
                           input="1\n", capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Saved:", r.stderr)

    def test_missing_required_exits_2(self):
        r = subprocess.run([sys.executable, GEN], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)


class TestSetupEnv(unittest.TestCase):
    def test_setup_env_runs(self):
        r = subprocess.run([sys.executable, os.path.join(SCRIPT_DIR, "setup_env.py")],
                           capture_output=True, text=True, timeout=300)
        self.assertIn("环境自检", r.stdout)
        self.assertIn("环境就绪", r.stdout)


# ── Overlap mechanism regression: inverted axes must not nuke tick labels ──

class TestInvertedAxisTickPreservation(unittest.TestCase):
    """Regression: fix_tick_overlaps used to compute y-gaps as b[i+1].y0 -
    b[i].y1, which is always negative on inverted axes (heatmap/forest/km),
    so overlap was never cleared and labels got thinned to the first one.
    Also, hidden labels' boxes kept feeding the overlap check, so thinning
    never converged. Verify inverted-axis charts keep ALL tick labels."""

    def _render_and_count_labels(self, chart_type, data):
        fig, ax = plt.subplots(figsize=(9, 6))
        gen = gen_figure.GENERATORS[chart_type]
        gen(data, ax, gen_figure.THEMES["glm"], None)
        gen_figure.apply_base_style(ax, gen_figure.THEMES["glm"])
        plt.tight_layout()
        gen_figure.fix_tick_overlaps(fig)
        xl = [l for l in ax.get_xticklabels() if l.get_visible() and l.get_text().strip()]
        yl = [l for l in ax.get_yticklabels() if l.get_visible() and l.get_text().strip()]
        plt.close(fig)
        return xl, yl

    def test_heatmap_keeps_all_6_x_labels(self):
        data = {"rows": ["IL-6", "TNF-a", "CRP", "ESR", "DAS28", "SLEDAI"],
                "cols": ["IL-6", "TNF-a", "CRP", "ESR", "DAS28", "SLEDAI"],
                "matrix": [[1.0, 0.7, 0.8, 0.7, 0.8, 0.5],
                           [0.7, 1.0, 0.7, 0.6, 0.7, 0.3],
                           [0.8, 0.7, 1.0, 0.8, 0.8, 0.5],
                           [0.7, 0.6, 0.8, 1.0, 0.7, 0.4],
                           [0.8, 0.7, 0.8, 0.7, 1.0, 0.6],
                           [0.5, 0.3, 0.5, 0.4, 0.6, 1.0]]}
        xl, yl = self._render_and_count_labels("heatmap", data)
        self.assertEqual(len(xl), 6, f"heatmap x labels thinned: {[l.get_text() for l in xl]}")
        self.assertEqual(len(yl), 6)

    def test_forest_keeps_x_numeric_ticks(self):
        data = {"labels": ["S1", "S2", "S3", "S4"], "estimates": [0.72, 0.80, 0.75, 0.65],
                "ci_low": [0.55, 0.62, 0.56, 0.48], "ci_high": [0.94, 1.03, 1.00, 0.84],
                "overall": {"estimate": 0.73, "ci_low": 0.60, "ci_high": 0.88}}
        xl, yl = self._render_and_count_labels("forest", data)
        self.assertGreaterEqual(len(xl), 3, f"forest x ticks thinned: {[l.get_text() for l in xl]}")
        self.assertEqual(len(yl), 5)  # 4 studies + Overall

    def test_km_keeps_axis_labels(self):
        data = {"groups": {"A": [[0.0, 1.0], [5.0, 0.8]], "B": [[0.0, 1.0], [5.0, 0.9]]}}
        xl, yl = self._render_and_count_labels("km", data)
        self.assertGreaterEqual(len(xl), 2)
        self.assertGreaterEqual(len(yl), 2)


# ── Heatmap default colormap regression ────────────────────────────────

class TestHeatmapDefaultCmap(unittest.TestCase):
    """Regression: kwargs.get("cmap", "RdBu_r") never applied its default
    because main() always passes "cmap": args.cmap (None) — the key exists,
    so .get() returned None and imshow fell through to matplotlib's default
    viridis (yellow-green). The default must be RdBu_r unless overridden."""

    def test_default_cmap_is_rdbu_r(self):
        fig, ax = plt.subplots(figsize=(8, 6))
        data = {"rows": ["A", "B"], "cols": ["A", "B"],
                "matrix": [[1.0, -0.5], [-0.5, 1.0]]}
        kwargs = {"cmap": None}  # simulate main() always passing the key
        gen_figure.gen_heatmap(data, ax, gen_figure.THEMES["glm"], None, **kwargs)
        im = ax.images[0]
        self.assertEqual(im.get_cmap().name, "RdBu_r",
                         f"default cmap should be RdBu_r, got {im.get_cmap().name}")
        plt.close(fig)

    def test_explicit_cmap_still_overrides(self):
        fig, ax = plt.subplots(figsize=(8, 6))
        data = {"rows": ["A", "B"], "cols": ["A", "B"],
                "matrix": [[1.0, 0.5], [0.5, 1.0]]}
        kwargs = {"cmap": "YlOrRd"}
        gen_figure.gen_heatmap(data, ax, gen_figure.THEMES["glm"], None, **kwargs)
        im = ax.images[0]
        self.assertEqual(im.get_cmap().name, "YlOrRd")
        plt.close(fig)

    def test_all_positive_data_uses_warm_cmap_not_rdbu(self):
        """All-positive data must not render with RdBu_r — its white midpoint
        makes low positive values look like a broken band (断层). The default
        cmap switches to a warm sequential colormap for all-positive data."""
        fig, ax = plt.subplots(figsize=(8, 6))
        data = {"rows": ["A", "B"], "cols": ["A", "B"],
                "matrix": [[1.0, 0.5], [0.5, 0.3]]}
        kwargs = {"cmap": None}  # default path
        gen_figure.gen_heatmap(data, ax, gen_figure.THEMES["glm"], None, **kwargs)
        im = ax.images[0]
        self.assertEqual(im.get_cmap().name, "YlOrRd",
                         f"all-positive default should be YlOrRd, got {im.get_cmap().name}")
        plt.close(fig)

    def test_negative_data_keeps_diverging_rdbu(self):
        fig, ax = plt.subplots(figsize=(8, 6))
        data = {"rows": ["A", "B"], "cols": ["A", "B"],
                "matrix": [[1.0, -0.5], [-0.5, 1.0]]}
        kwargs = {"cmap": None}
        gen_figure.gen_heatmap(data, ax, gen_figure.THEMES["glm"], None, **kwargs)
        im = ax.images[0]
        self.assertEqual(im.get_cmap().name, "RdBu_r")
        plt.close(fig)


# ── Demo/example datasets must match the official data schemas ─────────

class TestDemoAndExampleSchemas(unittest.TestCase):
    """Every chart type reachable via --demo and every examples/*.json must
    pass validate_data() and render without raising. This catches schema
    drift between DEMO_DATA / example files and the generator functions
    (e.g. dual_axis used {"name","values"} objects instead of series dicts,
    km used object lists instead of {group: [[t,s],...]}, scatter/roc used
    unsupported formats — all crashed at render time)."""

    def _render(self, chart, data):
        fig, ax = plt.subplots(figsize=(8, 6))
        cjk_fp, _ = gen_figure.load_cjk_font()
        gen = gen_figure.GENERATORS[chart]
        extra = gen(data, ax, gen_figure.THEMES["glm"], cjk_fp)
        if chart not in ("dual_axis",) and extra not in ("composite", "diagram"):
            gen_figure.apply_base_style(ax, gen_figure.THEMES["glm"])
        plt.close(fig)

    def test_all_demo_datasets_valid_and_renderable(self):
        demo = gen_figure.DEMO_DATA
        self.assertTrue(demo, "DEMO_DATA must not be empty")
        for chart, data in demo.items():
            with self.subTest(demo_chart=chart):
                fatal, _warn = gen_figure.validate_data(data, chart)
                self.assertEqual(fatal, [], f"demo {chart} schema invalid: {fatal}")
                self._render(chart, data)

    def test_all_example_files_valid_and_renderable(self):
        examples_dir = os.path.join(os.path.dirname(__file__), "..", "examples")
        if not os.path.isdir(examples_dir):
            self.skipTest("no examples dir")
        canonical = {"dual": "dual_axis", "stacked": "stacked_bar",
                     "box": "box", "roc": "roc", "km": "km"}
        for fname in sorted(os.listdir(examples_dir)):
            if not fname.endswith(".json"):
                continue
            with self.subTest(example=fname):
                data = json.load(open(os.path.join(examples_dir, fname)))
                chart = fname.replace("example_", "").replace(".json", "")
                chart = canonical.get(chart, chart)
                if chart not in gen_figure.GENERATORS:
                    self.fail(f"example file {fname} maps to unknown chart '{chart}'")
                fatal, _warn = gen_figure.validate_data(data, chart)
                self.assertEqual(fatal, [], f"{fname} schema invalid: {fatal}")
                self._render(chart, data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
