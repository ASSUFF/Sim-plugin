import json
import unittest

from lumerical_fdtd.study import choose_best
from lumerical_fdtd.study import prepare_spec
from lumerical_fdtd.study import score_fdtd_payload
from lumerical_fdtd.validate import validate_spec


class PrepareTests(unittest.TestCase):
    def test_missing_wavelength_is_assumed(self):
        completed, assumptions = prepare_spec(
            {"commands": [{"op": "addrect", "properties": {"name": "core", "x span": 1e-6, "y span": 0.5e-6}}]}
        )
        self.assertEqual(completed["global_source"]["wavelength start"], 1.55e-6)
        self.assertTrue(assumptions)
        errors, _warnings = validate_spec(completed)
        self.assertEqual(errors, [])

    def test_explicit_wavelength_is_kept(self):
        completed, assumptions = prepare_spec(
            {
                "global_source": {"wavelength start": 1.31e-6, "wavelength stop": 1.31e-6},
                "simulation": {"dimension": "2D", "x": 0, "x span": 2e-6, "y": 0, "y span": 2e-6},
            }
        )
        self.assertEqual(completed["global_source"]["wavelength start"], 1.31e-6)
        self.assertFalse(any("1550" in item for item in assumptions))


class StudyScoreTests(unittest.TestCase):
    def test_best_transmission_is_the_maximum(self):
        payload = {
            "exports": [
                {
                    "name": "T",
                    "data": {
                        "fields": {
                            "lambda": {"values": [1.5e-6, 1.55e-6]},
                            "T": {"values": [0.2, 0.8]},
                        }
                    },
                }
            ]
        }
        score = score_fdtd_payload(payload, {"export": "T", "wavelength_m": 1.55e-6})
        self.assertEqual(score, 0.8)

    def test_transmission_array_uses_the_middle_sample(self):
        payload = {
            "exports": [
                {
                    "name": "T",
                    "data": {
                        "array": {
                            "values": [0.99979645, 0.9999903, 0.99963463],
                        }
                    },
                }
            ]
        }
        score = score_fdtd_payload(payload, {"export": "T", "wavelength_m": 1.55e-6})
        self.assertEqual(score, 0.9999903)
        best = choose_best(
            [{"value": 1, "score": 0.2}, {"value": 2, "score": 0.8}],
            "max",
        )
        self.assertEqual(best["value"], 2)


if __name__ == "__main__":
    unittest.main()
