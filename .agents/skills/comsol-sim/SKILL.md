---
name: comsol-sim
description: >
  驱动本机 COMSOL 6.4 建立模型、求解、扫描和寻优。用户提到 COMSOL、.mph、
  传热、参数扫描、寻优、仿真建议，或要求根据描述生成仿真时使用。
---

# COMSOL

工作目录是 `S:\Work\Grok Work\1113`。命令用 `.venv\Scripts\python.exe -m sim_plugin`。若当前会话已经有 `comsol_doctor`、`comsol_search`、`comsol_validate`、`comsol_run`、`comsol_sweep`、`comsol_optimize`、`comsol_advise`，优先调用这些工具，参数与下面的命令相同。

HFSS 和 FDTD 不在这些命令里。那两个软件仍用 `S:\simulation\FDTD\ai` 的旧插件。

## 新模型

1. 调用 `comsol doctor`。没有找到安装时停止。
2. 写 Java 前，用 `comsol search 关键词` 查 `create` 的类型名。使用返回的 `create_type`，不要凭记忆编造。completion 里的属性散列不是 Java 属性名。
3. Java 只能有一个 public class，类名与文件名相同。调用 `ModelUtil.initStandalone`。可扫描参数写成 `model.param().set("名字", "带单位的值")`。求解后先打印一行 `===RESULT===`，再按行打印 `名字=数值`。调用 `model.save`。不要使用 `Runtime.getRuntime`、`ProcessBuilder` 或反射。
4. 用 `comsol validate --java 文件 --spec 规格.json`。有 errors 时先改脚本。
5. 用 `comsol run` 求解。规格里的 `parameters.*.value` 会写进运行副本，不改用户给出的源文件。

稳态方板例子是 `comsol/examples/SteadyHeat.java`。左边 `T_cold`，右边 `T_hot`，另外两边绝热。恒定导热系数下，面积平均温度是两者的算术平均。`T_cold=300[K]`、`T_hot=400[K]` 时，`T_avg_K` 为 350，`T_max_K` 为 400，`T_min_K` 为 300。

光学加热例子是 `comsol/examples/OptoHeat.java`。它同时建立 `RadiativeBeamInAbsorbingMedia` 和 `HeatTransfer`，并用 `HeatTransferWithRadiativeBeamInAbsorbingMedia` 把吸收功率送进传热。默认参数下最高温度应约为 307.794 K，误差远小于 0.01 K。入射强度特征的 `beamProfile` 用 `userdef`，束流方向 `e` 是长度为 3 的矢量。

## 扫描和寻优

- `comsol sweep` 计算规格 `sweep` 里的全部组合。每个参数 2 到 8 个取值，组合总数不超过 8。
- `comsol optimize` 对一个参数做粗到细搜索。`optimize.max_runs` 为 2 到 8。先取区间两端和中点，再在当前最好点与相邻点的中点继续算。
- 目标导出值必须是纯数字。`goal.sense` 为 `min` 或 `max`。
- 向用户说明 `best` 只是已计算各次中的最好结果。返回里若有 `note`，要带到回答中。

## 建议

求解、扫描或寻优之后，对报告调用 `comsol advise --report 报告.json`。用返回的 `facts` 写建议，不要另造网格、收敛或许可证状态。事实说最好点在区间端点时，告诉用户扩大区间可能还有更好的点。单次求解的事实不能说成最优解。

## 不要做

- 不覆盖 `S:\COMSOL\Cursor` 里的模型，也不把运行目录指到那里。
- 不关闭用户已经打开的 COMSOL。
- 扫描或寻优超过 8 次时，先停下来，让用户决定是否提高上限。插件当前会直接拒绝。
