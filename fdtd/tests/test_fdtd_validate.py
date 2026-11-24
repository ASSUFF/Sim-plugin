import json
import unittest
from pathlib import Path

from lumerical_fdtd.validate import script_property_problems, validate_spec

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

    def test_addindex_rejects_monitor_type(self):
        errors, _warnings = validate_spec(
            {
                "simulation": {"dimension": "2D"},
                "commands": [{"op": "addindex", "properties": {"name": "n", "monitor type": "1D Z"}}],
            }
        )
        self.assertTrue(any("没有属性 monitor type" in error for error in errors))

    def test_power_monitor_rejects_an_unknown_type(self):
        errors, _warnings = validate_spec(
            {
                "simulation": {"dimension": "2D"},
                "commands": [{"op": "addpower", "properties": {"name": "m", "monitor type": "1D Z"}}],
            }
        )
        self.assertTrue(any("不能是 1D Z" in error for error in errors))

    def test_crossing_script_properties_are_known(self):
        script = (ROOT / "examples" / "crossing_sin.lsf").read_text(encoding="utf-8")
        errors, _warnings = script_property_problems(script)
        self.assertEqual(errors, [])

    def test_unknown_field_is_a_warning(self):
        errors, warnings = validate_spec({"simulation": {"dimension": "2D"}, "notes": "keep"})
        self.assertEqual(errors, [])
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
