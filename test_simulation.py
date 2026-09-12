"""Scenario actions and missing-data guardrails on synthetic students only."""

import unittest

import numpy as np
import pandas as pd

from engine import CORE, simulate, simulation_guidance


class SimulationTests(unittest.TestCase):
    def test_risk_levels_have_different_workflows(self):
        self.assertIn("Pantau", simulation_guidance(.40, "Matematika"))
        self.assertIn("Penguatan terarah", simulation_guidance(.64, "Matematika"))
        self.assertIn("wali kelas", simulation_guidance(.75, "Matematika"))
        self.assertIn("Jaga rutinitas", simulation_guidance(.10, "Matematika"))
        self.assertIn("Data belum cukup", simulation_guidance(np.nan, "Matematika"))

    def test_no_probability_with_missing_subject_or_null_score(self):
        rows = []
        for subject in CORE[:2]:
            for number, score in enumerate((50, 55, 57), 1):
                rows.append({"student_id": "S1", "nama": "Contoh", "kelas": "12A",
                             "status_tka": "Ikut", "mapel": subject,
                             "assessment_order": number, "score": score})
        rows.append({"student_id": "S1", "nama": "Contoh", "kelas": "12A",
                     "status_tka": "Ikut", "mapel": CORE[2],
                     "assessment_order": None, "score": None})
        result, detail = simulate(pd.DataFrame(rows), 65, 3, 5000)
        self.assertEqual(result.iloc[0].status, "Data terbatas")
        self.assertTrue(pd.isna(result.iloc[0].peluang_belum_target))
        self.assertTrue(pd.isna(result.iloc[0].proyeksi))
        self.assertIsNone(detail["S1"]["distribution"])

    def test_fixed_seed_and_5000_sample_resolution(self):
        rows = [{"student_id": "S1", "nama": "Contoh", "kelas": "12A",
                 "status_tka": "Ikut", "mapel": subject,
                 "assessment_order": number, "score": score}
                for subject in CORE for number, score in enumerate((60, 62, 64), 1)]
        data = pd.DataFrame(rows)
        first, details = simulate(data, 65, 3, 5000)
        second, _ = simulate(data, 65, 3, 5000)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(len(details["S1"]["distribution"]), 5000)
        self.assertTrue(0 <= first.iloc[0].peluang_belum_target <= 1)


if __name__ == "__main__":
    unittest.main()
