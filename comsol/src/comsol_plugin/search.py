"""Search COMSOL completion XML for Java create() type names.

The files live in the local COMSOL install. Property hashes in those files are
not Java property names. The Java create() type is the element tag when that
tag is a type name, and the name attribute when the tag itself is hashed.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from comsol_plugin.discover import find_install

_FILES = (
    "geom.xml",
    "physics.xml",
    "material.xml",
    "mesh.xml",
    "study.xml",
    "common.xml",
    "selection.xml",
    "numerical.xml",
    "cpl.xml",
)


def search_features(
    keyword: str,
    root: Path | str | None = None,
    limit: int = 20,
) -> dict:
    keyword = keyword.strip()
    if len(keyword) < 2:
        return {"ok": False, "error": "检索词至少两个字符。", "matches": []}
    install = find_install(root)
    if install.completion_dir is None:
        return {
            "ok": False,
            "error": "没有找到 COMSOL 的 data/completion 目录，无法检索接口名称。",
            "matches": [],
            "install": install.as_dict(),
        }

    needle = _norm(keyword)
    exact_matches: list[dict] = []
    fuzzy_matches: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for file_name in _FILES:
        path = install.completion_dir / file_name
        if not path.is_file():
            continue
        for item in _scan(path, file_name, needle):
            key = (item["file"], item["create_type"], item["label"], item["id"])
            if key in seen:
                continue
            seen.add(key)
            exact = item.pop("exact")
            if exact:
                exact_matches.append(item)
            else:
                fuzzy_matches.append(item)
            if len(exact_matches) >= limit:
                break
        if len(exact_matches) >= limit:
            break
    matches = (exact_matches + fuzzy_matches)[:limit]
    return {"ok": True, "keyword": keyword, "matches": matches}


def _scan(path: Path, file_name: str, needle: str):
    for _event, elem in ET.iterparse(path, events=("end",)):
        tag = elem.tag
        if tag == "description":
            continue
        name = elem.attrib.get("name", "")
        if _CREATE_TYPE.fullmatch(name):
            create_type = name
        elif _CREATE_TYPE.fullmatch(tag):
            create_type = tag
        else:
            elem.clear()
            continue
        descr = elem.attrib.get("descr", "")
        ident = elem.attrib.get("id", "")
        description = _description(elem)
        elem.clear()
        if not descr and not ident and not name:
            continue
        exact = needle in {_norm(create_type), _norm(ident)}
        fuzzy = len(needle) >= 3 and needle in _norm(" ".join((descr, description)))
        if not exact and not fuzzy:
            continue
        yield {
            "file": file_name,
            "create_type": create_type,
            "label": descr.replace("_", " "),
            "id": ident,
            "description": description,
            "exact": exact,
        }


def _description(elem: ET.Element) -> str:
    for child in elem:
        if child.tag == "description" and child.text:
            return " ".join(child.text.split())
    return ""


def _norm(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


_CREATE_TYPE = re.compile(r"[A-Z][A-Za-z0-9]*")
