import json
import unittest
from pathlib import Path

from lumerical_fdtd.validate import validate_spec

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "examples" / "smoke_2d.json"


class ValidateTests(unittest.TestCase):
    def test_wrong_object_dielectric_spelling_is_rejected(self):
        errors, _warnings = validate_spec(
            {
                "simulation": {"dimension": "2D"},
                "commands": [
                    {
                        "op": "addrect",
                        "properties": {"name": "core", "material": "<Object Defined Dielectric>"},
                    }
                ],
            }
        )
        self.assertTrue(any("Object defined dielectric" in error for error in errors))

    def test_smoke_example(self):
        errors, warnings = validate_spec(json.loads(SMOKE.read_text(encoding="utf-8")))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_rejects_command_injection(self):
        errors, _warnings = validate_spec(
            {"simulation": {"dimension": "2D"}, "commands": [{"op": "addrect; deleteall"}]}
        )
        self.assertTrue(errors)

    def test_rejects_bad_monitor_name(self):
        errors, _warnings = validate_spec(
            {
                "simulation": {"dimension": "2D"},
                "exports": [{"monitor": 'mon"); deleteall;'}],
            }
        )
        self.assertTrue(any("monitor" in item for item in errors))

    def test_empty_spec(self):
        errors, _warnings = validate_spec({})
        self.assertTrue(errors)

    def test_unknown_field_is_a_warning(self):
        errors, warnings = validate_spec({"simulation": {"dimension": "2D"}, "notes": "keep"})
        self.assertEqual(errors, [])
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
