from pathlib import Path

from comsol_plugin.search import search_features


def _completion(root: Path, body: str) -> None:
    win64 = root / "bin" / "win64"
    win64.mkdir(parents=True)
    for name in ("comsolbatch.exe", "comsolcompile.exe"):
        (win64 / name).write_text("", encoding="utf-8")
    folder = root / "data" / "completion"
    folder.mkdir(parents=True)
    (folder / "geom.xml").write_text(body, encoding="utf-8")


def test_search_returns_java_create_type(tmp_path: Path) -> None:
    _completion(
        tmp_path,
        """<?xml version="1.0"?>
        <COMSOLCompletionData>
          <Rectangle descr="Rectangle[geometry]" id="r">
            <description>Axis-aligned rectangle.</description>
          </Rectangle>
          <Block descr="Block" id="blk">
            <description>A box.</description>
          </Block>
        </COMSOLCompletionData>
        """,
    )
    result = search_features("rectangle", root=tmp_path, limit=5)
    assert result["ok"] is True
    assert result["matches"] == [
        {
            "file": "geom.xml",
            "create_type": "Rectangle",
            "label": "Rectangle[geometry]",
            "id": "r",
            "description": "Axis-aligned rectangle.",
        }
    ]


def test_hashed_tag_uses_name_attribute(tmp_path: Path) -> None:
    _completion(
        tmp_path,
        """<?xml version="1.0"?>
        <COMSOLCompletionData>
          <wqxxastx descr="Temperature" id="temp" name="TemperatureBoundary"/>
        </COMSOLCompletionData>
        """,
    )
    result = search_features("TemperatureBoundary", root=tmp_path)
    assert result["matches"][0]["create_type"] == "TemperatureBoundary"
    assert result["matches"][0]["id"] == "temp"


def test_short_keyword_matches_id_only(tmp_path: Path) -> None:
    _completion(
        tmp_path,
        """<?xml version="1.0"?>
        <COMSOLCompletionData>
          <HeatTransfer descr="Heat_transfer_in_solids" id="ht"/>
        </COMSOLCompletionData>
        """,
    )
    exact = search_features("ht", root=tmp_path)
    assert [item["create_type"] for item in exact["matches"]] == ["HeatTransfer"]
    assert search_features("h", root=tmp_path)["ok"] is False


def test_installed_completion_knows_block() -> None:
    result = search_features("Block", limit=5)
    assert result["ok"] is True
    create_types = {item["create_type"] for item in result["matches"]}
    assert "Block" in create_types
