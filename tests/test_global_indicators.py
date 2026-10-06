"""New public indicators must stay aligned from processed CSV to every notebook."""

import json
import runpy
import unittest

import pandas as pd

from ship_orders_forecasting.legacy import legacy_module
from ship_orders_forecasting.order_availability import (
    available_order_point_lags, publication_dates,
)


rules = legacy_module("마스터테이블_생성")
NEW = [
    *rules.CONTAINER_INDEX_COLUMNS,
    *rules.GLOBAL_ECONOMY_COLUMNS,
    *rules.SUPPLY_CHAIN_COLUMNS,
]


class GlobalIndicatorsTest(unittest.TestCase):
    def test_container_h6_runs_in_memory_without_report_file(self):
        script = (rules.PROJECT_ROOT / "scripts" / "분석"
                  / "공개시차_6개월_컨테이너선.py")
        module = runpy.run_path(str(script))
        full = module["full_candidate_set"](["외부1", "외부2"])
        self.assertEqual(list(full), ["전체 후보"])
        self.assertEqual(full["전체 후보"][-2:], ["외부1", "외부2"])
        source = script.read_text(encoding="utf-8")
        self.assertIn('first="2022-01", last="2024-12"', source)
        self.assertIn('if row["목표월"] <= pd.Timestamp("2025-03-01")', source)
        self.assertFalse((rules.PROJECT_ROOT / "reports"
                          / "공개시차_6개월_컨테이너선.json").exists())

    def test_container_h6_notebook_shows_same_rule_in_every_section(self):
        notebook_path = (rules.PROJECT_ROOT / "scripts" / "분석"
                         / "수주예측(컨테이너선).ipynb")
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        code = {cell["id"]: "".join(cell["source"]) for cell in notebook["cells"]
                if cell["cell_type"] == "code"}
        self.assertIn("run_analysis", code["operational-inputs"])
        self.assertIn("['전체 후보']", code["model-order-lags"])
        self.assertIn("['fold별기준월']", code["model-common-folds"])
        self.assertIn("연결월 = pd.date_range('2024-11-01', '2025-03-01'",
                      code["holdout-series"])
        self.assertNotIn("선택·진단 사이", code["holdout-series"])
        scatter = code["holdout-scatter"]
        self.assertIn("산점도자료['데이터마감월'].eq(기대마감월)", scatter)
        self.assertIn("산점도자료['목표월'].eq(산점도자료['데이터마감월']", scatter)
        self.assertIn("산점도자료['예측기준일'] < pd.Timestamp('2022-01-01')", scatter)
        self.assertIn("sns.regplot(data=산점도자료", scatter)
        self.assertIn("scatter=False, ci=None", scatter)
        self.assertNotIn("운영보고서", "\n".join(code.values()))
        self.assertNotIn("selection-single-addition", code)

    def test_all_master_tables_match_processed_values(self):
        sources = [
            (rules.CONTAINER_INDEX_PATH, rules.CONTAINER_INDEX_COLUMNS),
            (rules.GLOBAL_ECONOMY_PATH, rules.GLOBAL_ECONOMY_COLUMNS),
            (rules.SUPPLY_CHAIN_PATH, rules.SUPPLY_CHAIN_COLUMNS),
        ]
        for ship_type in rules.SHIP_TYPES:
            master = pd.read_csv(
                rules.MASTER_DIR / f"마스터테이블({ship_type}).csv",
                encoding="utf-8-sig",
            )
            self.assertTrue(master["기준월"].is_unique)
            orders, _ = rules.load_orders(ship_type)
            self.assertGreaterEqual(master["기준월"].max(), orders["기준월"].max())
            # Published sources may be incomplete in the newly retained 2026 tail.
            historical = master.loc[master["기준월"].lt("2026-01")]
            self.assertFalse(historical[NEW].isna().any().any())
            self.assertEqual(set(NEW).difference(rules.feature_columns_for(ship_type)), set())
            for path, columns in sources:
                source = pd.read_csv(path, encoding="utf-8-sig")
                self.assertTrue(source["기준월"].is_unique)
                joined = master[["기준월", *columns]].merge(
                    source[["기준월", *columns]], on="기준월", how="left",
                    validate="one_to_one", suffixes=("_master", "_source"),
                )
                self.assertEqual(len(joined), len(master))
                for column in columns:
                    pd.testing.assert_series_equal(
                        joined[f"{column}_master"], joined[f"{column}_source"],
                        check_names=False, check_exact=False,
                        rtol=1e-12, atol=1e-12,
                    )

    def test_five_notebooks_include_new_candidates(self):
        notebook_dir = rules.PROJECT_ROOT / "scripts" / "분석"
        notebooks = sorted(notebook_dir.glob("수주예측(*).ipynb"))
        self.assertEqual(len(notebooks), 5)
        for path in notebooks:
            notebook = json.loads(path.read_text(encoding="utf-8"))
            code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
            self.assertEqual(len(notebook["cells"]), 46, path.name)
            self.assertEqual(len(code_cells), 20, path.name)
            if path.name.startswith("수주예측("):
                code_by_id = {cell["id"]: "".join(cell["source"]) for cell in code_cells}
                introduction = "".join(notebook["cells"][0]["source"])
                for label in ("- 목표변수:", "- 예측 기준:", "- 설명변수:",
                              "- 개발 검증:", "- 모형·변수 선택:", "- 2025~2026년 개발 진단:"):
                    self.assertIn(label, introduction)
                self.assertNotIn("기존 ‘자료 기준 한 달 뒤’", introduction)
                self.assertNotIn("수주용량_최근확정6개월차", code_by_id["setup-features"])
                self.assertIn("run_analysis", code_by_id["operational-inputs"])
                self.assertIn("'변수조합비교'", code_by_id["model-comparison"])
                eda = code_by_id["eda-correlation"]
                self.assertIn("eligible_training(시점격자, 6, 첫검증시점, 그림후보)", eda)
                self.assertIn("select_correlated_features(초기학습, 그림후보)", eda)
                self.assertIn("상관관계 = 상관입력[상관열].corr(method='pearson')", eda)
                self.assertIn("초기학습['목표월'].max() > pd.Timestamp('2021-10-01')", eda)
                self.assertNotIn("탐색자료[[종속변수, *후보]]", eda)
                self.assertIn("박스플롯자료 = 상관입력[상관열].copy()",
                              code_by_id["eda-distribution"])
                for cell_id in ("model-external-lags", "model-order-lags",
                                "model-common-folds", "model-comparison",
                                "selection-single-removal",
                                "selection-model-choice", "selection-path"):
                    self.assertIn(cell_id, code_by_id)
                for cell_id in ("selection-fold-comparison",
                                "selection-independent-rank",
                                "selection-final-importance"):
                    self.assertNotIn(cell_id, code_by_id)
                self.assertIn("운영결과['선행개월'] != 6", code_by_id["operational-inputs"])
                self.assertIn("2026-10_6개월전망선", code_by_id["operational-inputs"])
                self.assertIn("운영끝다음월 = 운영전망선['목표월'].max()", code_by_id["holdout-series"])
                self.assertIn("배경구간 = [", code_by_id["holdout-series"])
                self.assertIn("축.axvspan(구간시작, 구간끝", code_by_id["holdout-series"])
                self.assertIn("운영전망선['목표월']", code_by_id["holdout-series"])
                self.assertIn("확보실제 = 자료.loc[자료.index <= 데이터마감월", code_by_id["holdout-series"])
                self.assertIn("선택참고['예측'].reindex(전체월)", code_by_id["holdout-series"])
                self.assertIn("보이는진단['예측'].reindex(전체월)", code_by_id["holdout-series"])
                self.assertIn("축.plot(운영전망선['목표월'], 운영전망선['예측']",
                              code_by_id["holdout-series"])
                self.assertNotIn("marker='o'", code_by_id["holdout-series"])
                self.assertNotIn("[확보실제.loc[데이터마감월]", code_by_id["holdout-series"])
                for cell_id in ("holdout-aggregate", "holdout-series",
                                "holdout-importance-plot", "holdout-scatter"):
                    self.assertIn(cell_id, code_by_id)
                self.assertNotIn("holdout-peak", code_by_id)
                self.assertNotIn("operational-future", code_by_id)
                self.assertNotIn("operational-scores", code_by_id)
                self.assertIn("annual_replay(", code_by_id["annual-replay-run"])
                self.assertIn("years=(2023, 2024, 2025, 2026)",
                              code_by_id["annual-replay-run"])
                self.assertIn("'평가월수'", code_by_id["annual-replay-report"])
                self.assertIn("'순차 제거 피처'", code_by_id["annual-replay-report"])

    def test_shared_analysis_cells_do_not_drift_between_ship_types(self):
        notebook_dir = rules.PROJECT_ROOT / "scripts" / "분석"
        notebooks = sorted(notebook_dir.glob("수주예측(*).ipynb"))
        shared_ids = {
            "setup-master", "eda-correlation", "eda-distribution",
            "model-monthly-rule", "model-external-lags", "model-order-lags",
            "model-common-folds", "model-comparison", "selection-single-removal",
            "selection-model-choice", "selection-path", "holdout-aggregate",
            "holdout-importance-plot", "holdout-scatter",
            "annual-replay-run", "annual-replay-report",
        }
        reference = None
        for path in notebooks:
            notebook = json.loads(path.read_text(encoding="utf-8"))
            by_id = {
                cell["id"]: "".join(cell["source"])
                for cell in notebook["cells"] if cell["cell_type"] == "code"
            }
            current = {cell_id: by_id[cell_id] for cell_id in shared_ids}
            if reference is None:
                reference = current
            else:
                self.assertEqual(current, reference, path.name)

    def test_order_windows_match_strict_calendar_rolls(self):
        for ship_type in rules.SHIP_TYPES:
            master = pd.read_csv(
                rules.MASTER_DIR / f"마스터테이블({ship_type}).csv",
                encoding="utf-8-sig",
            )
            raw = pd.read_csv(rules.RAW_ORDERS_PATH, encoding="utf-8-sig",
                              dtype=str, keep_default_na=False)
            published = publication_dates(raw, rules.RAW_VESSEL_TYPES[ship_type])
            expected = available_order_point_lags(
                master["기준월"], master[rules.TARGET_COLUMN], published,
            )
            for column in rules.order_feature_columns_for(ship_type).values():
                pd.testing.assert_series_equal(master[column], expected[column],
                                               check_names=False)
            self.assertFalse(set(rules.ORDER_WINDOW_COLUMNS.values()) & set(master.columns))


if __name__ == "__main__":
    unittest.main()
