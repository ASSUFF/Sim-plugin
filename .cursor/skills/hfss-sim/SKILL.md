---
name: hfss-sim
description: >
  驱动本机 Ansys HFSS 2024.2 求解、扫描和寻优。用户提到 HFSS、Electronics Desktop、
  .aedt、S 参数、WR-90 或波导时使用。
---

# HFSS

工作目录是 `S:\Work\Grok Work\1113`。命令用 `.venv\Scripts\python.exe -m sim_plugin`。若已有 `hfss_doctor`、`hfss_validate`、`hfss_prepare`、`hfss_run`、`hfss_sweep`、`hfss_optimize`、`hfss_advise`，优先用这些工具。

长度用米，频率用赫兹。S21 用 `dB(S(P2,P1))` 和 `goal: max`。S11 用 `dB(S(P1,P1))` 和 `goal: min`。

先 `hfss doctor`。端口 `1055@localhost` 不通时不要启动求解。`hfss run` 求解一份规格。`hfss sweep` 对一个参数比较 2 到 8 个值。`hfss optimize` 对一个数值路径做最多 8 次粗到细搜索。求解后用 `hfss advise` 取事实，再写成建议。

WR-90 例子是 `S:\simulation\FDTD\ai\hfss-aedt\examples\wr90.json`。10 GHz、长度 0.03 m 时 S21 为 0.0 dB，S11 为 -64.084 dB。长度搜索例子是 `hfss\examples\wr90_length_optimize.json`。

`best` 只表示已计算各次中的最好结果。最好点在区间端点时，说明扩大区间可能还有更好的点。

不要打开或复制 `S:\simulation\HFSS\4mm.aedt`。不要关闭已经打开的 Electronics Desktop。
