import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "src" / "lumerical_fdtd" / "engine.py"
SMOKE = ROOT / "examples" / "smoke_2d.json"


class IntegrationTests(unittest.TestCase):
    def test_smoke_2d(self):
        if os.environ.get("LUMERICAL_FDTD_INTEGRATION") != "1":
            raise unittest.SkipTest("set LUMERICAL_FDTD_INTEGRATION=1 to run a licensed smoke simulation")
        src = str(ROOT / "src")
        env = os.environ.copy()
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
        sys.path.insert(0, src)
        from lumerical_fdtd.discover import find_install

        install = find_install()
        program = install.python or Path(sys.executable)
        with tempfile.TemporaryDirectory() as tmp:
            env["LUMERICAL_FDTD_RUNS"] = tmp
            proc = subprocess.run(
                [str(program), str(ENGINE), "run", "--spec", str(SMOKE)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        self.assertIn("FDTD_RESULT ", proc.stdout, proc.stderr)
        line = proc.stdout[proc.stdout.rfind("FDTD_RESULT ") + len("FDTD_RESULT ") :].strip().splitlines()[0]
        payload = json.loads(line)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(payload["solver"]["dimension"], "2D")
        values = payload["exports"][0]["data"]["fields"]["T"].get("values")
        self.assertTrue(values)


if __name__ == "__main__":
    unittest.main()
