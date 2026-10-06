"""두 히트맵 모드의 색상·강조 표시 회귀 검사."""

from pathlib import Path
import runpy
import unittest

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DRAW = runpy.run_path(str(
    Path(__file__).resolve().parents[1] / "scripts" / "분석" / "상관관계_회전히트맵.py"
))["draw_rotated_correlation"]


class RotatedHeatmapTest(unittest.TestCase):
    def test_full_color_and_target_highlight_modes(self):
        names = ["A", "B", "수주용량"]
        correlation = pd.DataFrame(
            [[1.0, 0.4, -0.6], [0.4, 1.0, 0.2], [-0.6, 0.2, 1.0]],
            index=names, columns=names,
        )
        figures = []
        try:
            for emphasize in (False, True):
                figure, axis = DRAW(correlation, highlight_target=emphasize)
                figures.append(figure)
                cells = {patch.get_gid(): patch for patch in axis.patches}
                self.assertEqual(sum(gid.startswith("cell:") for gid in cells), 3)
                self.assertEqual("target-outline" in cells, emphasize)
                background_rgb = cells["cell:1:0"].get_facecolor()[:3]
                if emphasize:
                    self.assertTrue(np.allclose(background_rgb, background_rgb[0]))
                else:
                    self.assertFalse(np.allclose(background_rgb, background_rgb[0]))
        finally:
            for figure in figures:
                plt.close(figure)

    def test_processed_target_column_name_is_only_a_display_label(self):
        names = ["원유 평균 가격(USD/bbl)", "수주용량"]
        correlation = pd.DataFrame(
            [[1.0, 0.3], [0.3, 1.0]], index=names, columns=names,
        )
        figure, axis = DRAW(correlation, target_label="수주용량(TEU)")
        try:
            labels = {text.get_gid(): text.get_text() for text in axis.texts
                      if text.get_gid() is not None}
            self.assertEqual(labels["left:1"], "수주용량(TEU)")
            self.assertEqual(labels["right:0"], "원유 평균 가격(USD/bbl)")
            self.assertEqual(correlation.columns.tolist(), names)
        finally:
            plt.close(figure)


if __name__ == "__main__":
    unittest.main()
