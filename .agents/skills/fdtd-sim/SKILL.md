---
name: fdtd-sim
description: >
  驱动本机 Ansys Lumerical FDTD。用户提到 Lumerical、lumapi、.fsp、波长、监视器或透射时使用。
  本机若未安装求解器，doctor 会报未安装，此时不要尝试启动 FDTD。
---

# FDTD

工作目录是 `S:\Work\Grok Work\1113`。命令用 `.venv\Scripts\python.exe -m sim_plugin`。若已有 `fdtd_doctor`、`fdtd_validate`、`fdtd_prepare`、`fdtd_run`、`fdtd_sweep`、`fdtd_optimize`、`fdtd_advise`，优先用这些工具。

长度用米，时间用秒。先 `fdtd doctor`。`installed` 不是 true 时停止，不要调用 `run`、`sweep` 或 `optimize`。

规格例子在 `fdtd/examples`。`sweep` 对一个对象属性取 2 到 8 个值。`optimize` 最多 8 次。透射用 `goal: max`。求解后用 `fdtd advise` 取事实再写建议。`best` 只表示已计算各次中的最好结果。

源 `.fsp` 先复制到 `fdtd/runs`。不要覆盖用户原来的工程。
