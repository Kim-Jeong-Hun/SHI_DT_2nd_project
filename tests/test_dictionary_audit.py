"""The dictionary checker must follow rules, not a second feature list."""

import unittest

from ship_orders_forecasting.dictionary_audit import (
    audit_project, check_feature_rows, check_source_metadata, expected_flags,
)
from ship_orders_forecasting.legacy import legacy_module


class DictionaryAuditTest(unittest.TestCase):
    def test_ship_flags_are_derived_from_master_rules(self):
        rules = legacy_module("마스터테이블_생성")
        flags = expected_flags(rules)
        self.assertEqual(flags["수주용량"]["가스 운반선"], "Y")
        self.assertEqual(flags["수주용량_최근확정1개월차"]["유조선"], "O")
        self.assertEqual(flags["철광석 가격(USD/dmtu)"].get("벌크선"), "O")
        self.assertNotIn("가스 운반선", flags["철광석 가격(USD/dmtu)"])

    def test_unknown_feature_cannot_be_marked_as_active(self):
        row = ("후보", "후보", "새 변수", "설명", "O", "-", "-", "-", "-", "PINK", "메모")
        issues, candidates = check_feature_rows(
            [(6, row)], {"벌크선": 4, "컨테이너선": 5}, {}
        )
        self.assertEqual(candidates, 1)
        self.assertIn("feature.unimplemented_flag", {issue.code for issue in issues})
        self.assertIn("Feature_Dictionary!E6", {issue.location for issue in issues})

    def test_same_source_id_requires_consistent_metadata(self):
        prefix = ("후보", "후보", "새 변수", "설명", "-", "-", "-", "-", "-", "PINK", "메모")
        first = prefix + ("세계은행", "https://example.org", "raw/a.csv", "processed/a.csv", "설명")
        second = prefix + ("다른 기관", "https://example.org", "raw/a.csv", "processed/a.csv", "설명")
        issues, source_ids = check_source_metadata([(6, first), (7, second)])
        self.assertEqual(source_ids, {"PINK"})
        self.assertIn("source.metadata_conflict", {issue.code for issue in issues})

    def test_source_metadata_cannot_be_blank(self):
        row = ("후보", "후보", "새 변수", "설명", "-", "-", "-", "-", "-", "PINK", "메모",
               "세계은행", "https://example.org", "raw/a.csv", "", "설명")
        issues, _ = check_source_metadata([(6, row)])
        self.assertIn("Feature_Dictionary!O6", {issue.location for issue in issues})

    def test_current_workbook_matches_project_rules(self):
        report = audit_project()
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["summary"]["master_tables"], 5)
        self.assertEqual(report["summary"]["unintroduced_candidates"], 9)
        self.assertEqual(report["summary"]["code_order_mappings"], 29)
        self.assertEqual(report["summary"]["source_ids"], 19)


if __name__ == "__main__":
    unittest.main()
