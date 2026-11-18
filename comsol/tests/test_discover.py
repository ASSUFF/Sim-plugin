from pathlib import Path

from comsol_plugin.discover import doctor, find_install


def _fake_install(root: Path, version_line: str = "SOFTWARE COMPONENTS IN COMSOL 6.4") -> None:
    win64 = root / "bin" / "win64"
    win64.mkdir(parents=True)
    for name in ("comsol.exe", "comsolbatch.exe", "comsolcompile.exe"):
        (win64 / name).write_text("", encoding="utf-8")
    (root / "about.txt").write_text(version_line + "\n", encoding="utf-8")
    (root / "data" / "completion").mkdir(parents=True)


def test_explicit_root_reports_version_without_launching(tmp_path: Path) -> None:
    _fake_install(tmp_path)
    found = find_install(tmp_path)
    assert found.ok
    assert found.version == "6.4"
    assert found.comsolbatch is not None
    assert found.comsolbatch.name == "comsolbatch.exe"
    assert found.completion_dir == tmp_path / "data" / "completion"
    report = found.as_dict()
    report["launched_solver"] = False
    assert report["launched_solver"] is False


def test_missing_root_is_not_ok(tmp_path: Path) -> None:
    found = find_install(tmp_path / "absent")
    assert found.ok is False
    assert found.source == "argument"


def test_parent_directory_finds_multiphysics_child(tmp_path: Path) -> None:
    _fake_install(tmp_path / "COMSOL64" / "Multiphysics", "COMSOL 6.2")
    found = find_install(tmp_path)
    assert found.ok
    assert found.version == "6.2"
    assert found.root == (tmp_path / "COMSOL64" / "Multiphysics").resolve()


def test_this_machine_finds_installed_comsol() -> None:
    report = doctor()
    assert report["launched_solver"] is False
    assert report["ok"] is True
    assert report["version"] == "6.4"
    assert report["root"] == r"S:\COMSOL\COMSOL64\Multiphysics"
    assert str(report["comsolbatch"]).endswith(r"bin\win64\comsolbatch.exe")
    assert report["completion_dir"] == r"S:\COMSOL\COMSOL64\Multiphysics\data\completion"
