"""Check a COMSOL Java model before compile or solve.

The check reads the source only. It does not call comsolcompile or comsolbatch.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_PUBLIC_CLASS = re.compile(r"\bpublic\s+class\s+([A-Za-z_]\w*)")
_PARAM_SET = re.compile(r"""param\(\)\.set\(\s*"([^"]+)"\s*,""", re.MULTILINE)
_FORBIDDEN = (
    (re.compile(r"Runtime\s*\.\s*getRuntime"), "Java 里不要启动外部进程。"),
    (re.compile(r"\bProcessBuilder\b"), "Java 里不要启动外部进程。"),
    (re.compile(r"java\s*\.\s*lang\s*\.\s*reflect"), "Java 里不要用反射。"),
)
_EXPORT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_job(java: str | Path, spec: str | Path | None = None) -> dict:
    java_path = Path(java)
    errors: list[str] = []
    warnings: list[str] = []
    source = ""
    class_name = None
    parameters: list[str] = []

    if not java_path.is_file():
        errors.append(f"找不到 Java 文件：{java_path}")
    elif java_path.suffix.lower() != ".java":
        errors.append("模型文件需要是 .java。")
    else:
        source = java_path.read_text(encoding="utf-8")
        class_names = _PUBLIC_CLASS.findall(source)
        if len(class_names) != 1:
            errors.append("Java 文件里需要恰好一个 public class。")
        else:
            class_name = class_names[0]
            if class_name != java_path.stem:
                errors.append(f"公开类名 {class_name} 需要与文件名 {java_path.stem} 相同。")
        if "com.comsol.model" not in source:
            errors.append("Java 文件需要导入 com.comsol.model。")
        if "ModelUtil.initStandalone" not in source:
            errors.append("Java 文件需要调用 ModelUtil.initStandalone，批处理才会自行启动 COMSOL。")
        if "model.save" not in source:
            warnings.append("Java 文件没有 model.save，运行后不会留下 .mph。")
        if "===RESULT===" not in source:
            warnings.append("Java 文件没有打印 ===RESULT===，后续无法从输出里读取结果。")
        for pattern, message in _FORBIDDEN:
            if pattern.search(source):
                errors.append(message)
        parameters = _PARAM_SET.findall(source)

    spec_data = None
    if spec is not None:
        spec_path = Path(spec)
        if not spec_path.is_file():
            errors.append(f"找不到规格文件：{spec_path}")
        else:
            try:
                spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"规格不是合法 JSON：{exc.lineno} 行。")
            else:
                if not isinstance(spec_data, dict):
                    errors.append("规格的顶层需要是 JSON 对象。")
                    spec_data = None

    exports: list[str] = []
    goal = None
    if isinstance(spec_data, dict):
        exports, goal, spec_parameters = _check_spec(spec_data, errors)
        if source:
            for name in spec_parameters:
                if name not in parameters:
                    errors.append(f"规格里的参数 {name} 没有出现在 model.param().set 中。")
            for name in exports:
                if f"{name}=" not in source:
                    errors.append(f"Java 需要在 ===RESULT=== 后打印 {name}=数值。")

    return {
        "ok": not errors,
        "launched_solver": False,
        "java": str(java_path),
        "class_name": class_name,
        "parameters": parameters,
        "exports": exports,
        "goal": goal,
        "errors": errors,
        "warnings": warnings,
    }


def _check_spec(spec: dict, errors: list[str]) -> tuple[list[str], dict | None, list[str]]:
    raw_parameters = spec.get("parameters", {})
    names: list[str] = []
    if raw_parameters is None:
        raw_parameters = {}
    if not isinstance(raw_parameters, dict):
        errors.append("parameters 需要是对象，键是参数名。")
    else:
        for name, value in raw_parameters.items():
            if not isinstance(name, str) or not _EXPORT_NAME.match(name):
                errors.append(f"参数名不合法：{name}")
                continue
            names.append(name)
            if isinstance(value, dict):
                if "value" not in value:
                    errors.append(f"参数 {name} 需要包含 value。")
                for bound in ("min", "max"):
                    if bound in value and not isinstance(value[bound], (int, float)):
                        errors.append(f"参数 {name} 的 {bound} 需要是数字。")
            elif not isinstance(value, (str, int, float)):
                errors.append(f"参数 {name} 的值需要是字符串、数字，或带 value 的对象。")

    exports = spec.get("exports", [])
    if exports is None:
        exports = []
    if not isinstance(exports, list) or not all(isinstance(item, str) and _EXPORT_NAME.match(item) for item in exports):
        errors.append("exports 需要是结果名称组成的数组。")
        exports = []

    goal = spec.get("goal")
    checked_goal = None
    if goal is not None:
        if not isinstance(goal, dict):
            errors.append("goal 需要是对象。")
        else:
            expression = goal.get("expression")
            sense = goal.get("sense")
            if not isinstance(expression, str) or expression not in exports:
                errors.append("goal.expression 需要是 exports 里的一个结果名。")
            if sense not in ("min", "max"):
                errors.append("goal.sense 只能是 min 或 max。")
            checked_goal = {"expression": expression, "sense": sense}

    return exports, checked_goal, names
