import json
import os
import tempfile
import unittest
from pathlib import Path

import jsonschema

from lumerical_fdtd.validate import validate_spec

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "src" / "lumerical_fdtd" / "schemas" / "fdtd-spec.schema.json").read_text(encoding="utf-8")
)
SMOKE = json.loads((ROOT / "examples" / "smoke_2d.json").read_text(encoding="utf-8"))


class SchemaTests(unittest.TestCase):
    def test_smoke_matches_schema(self):
        jsonschema.validate(SMOKE, SCHEMA)

    def test_bad_command_rejected_by_schema_and_validator(self):
        spec = {"simulation": {"dimension": "2D"}, "commands": [{"op": "addrect;"}]}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(spec, SCHEMA)
        errors, _warnings = validate_spec(spec)
        self.assertTrue(errors)


class DiscoverTests(unittest.TestCase):
    def test_env_root_and_bundled_python(self):
        from lumerical_fdtd.discover import find_install

        previous_root = os.environ.get("LUMERICAL_ROOT")
        previous_python = os.environ.get("LUMERICAL_PYTHON")
        os.environ.pop("LUMERICAL_PYTHON", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "v241"
                (root / "api" / "python").mkdir(parents=True)
                (root / "api" / "python" / "lumapi.py").write_text("# fixture\n", encoding="utf-8")
                (root / "bin").mkdir()
                (root / "bin" / "fdtd-solutions.exe").write_text("", encoding="utf-8")
                bundled = root / "python-3.9.9-embed-amd64"
                bundled.mkdir()
                (bundled / "python.exe").write_text("", encoding="utf-8")
                os.environ["LUMERICAL_ROOT"] = str(root)
                install = find_install()
                self.assertEqual(install.root, root.resolve())
                self.assertEqual(install.python, (bundled / "python.exe").resolve())
                self.assertTrue(install.solver_path().is_file())
        finally:
            if previous_root is None:
                os.environ.pop("LUMERICAL_ROOT", None)
            else:
                os.environ["LUMERICAL_ROOT"] = previous_root
            if previous_python is None:
                os.environ.pop("LUMERICAL_PYTHON", None)
            else:
                os.environ["LUMERICAL_PYTHON"] = previous_python

    def test_invalid_root_is_an_error(self):
        from lumerical_fdtd.discover import find_install

        previous = os.environ.get("LUMERICAL_ROOT")
        os.environ["LUMERICAL_ROOT"] = str(Path(tempfile.gettempdir()) / "missing-lumerical")
        try:
            with self.assertRaises(FileNotFoundError):
                find_install()
        finally:
            if previous is None:
                os.environ.pop("LUMERICAL_ROOT", None)
            else:
                os.environ["LUMERICAL_ROOT"] = previous

    def test_real_install_when_present(self):
        from lumerical_fdtd.discover import find_install

        previous = os.environ.get("LUMERICAL_ROOT")
        os.environ.pop("LUMERICAL_ROOT", None)
        try:
            try:
                install = find_install()
            except FileNotFoundError:
                raise unittest.SkipTest("Lumerical is not installed")
        finally:
            if previous is None:
                os.environ.pop("LUMERICAL_ROOT", None)
            else:
                os.environ["LUMERICAL_ROOT"] = previous
        self.assertTrue(install.lumapi.is_file())


if __name__ == "__main__":
    unittest.main()
