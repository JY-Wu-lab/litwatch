# Bundled journal metrics / 内置期刊指标

Running `litwatch.py init` automatically imports these two snapshots into the
workspace database. Do not edit the CSV files: LitWatch checks their SHA-256
before import. To use another edition, import your own CSV with `metrics import`.

执行 `litwatch.py init` 时，这两份快照会自动导入工作目录中的数据库。请勿修改 CSV；
LitWatch 会在导入前核对 SHA-256。需要其它年份时，请使用 `metrics import` 导入自己的表。

| File / 文件 | Meaning / 含义 | Edition / 版本 | Source rows / 源行数 |
|---|---|---:|---:|
| `JCR2025-UTF8.csv` | JCR quartiles and JIF / JCR 分区与影响因子 | 2025 | 22,643 |
| `FQBJCR2025-UTF8.csv` | Historical CAS major/minor partitions / 历史中科院大类、小类分区 | 2025 | 21,772 |

Source / 来源: [hitfyd/ShowJCR](https://github.com/hitfyd/ShowJCR), specifically
the public `中科院分区表及JCR原始数据文件` directory. The upstream repository is
published under GPL-3.0. LitWatch code remains MIT licensed; these two CSV files
retain their upstream terms, reproduced in `COPYING.GPL-3.0`. A public mirror is
not an official certification, so verify important evaluations against
Clarivate or the historical CAS platform.

这两份文件来自公开的 [hitfyd/ShowJCR](https://github.com/hitfyd/ShowJCR)
仓库中“中科院分区表及JCR原始数据文件”目录，上游仓库标注为 GPL-3.0。LitWatch
程序代码仍采用 MIT；这两份 CSV 沿用上游条款，许可证全文见 `COPYING.GPL-3.0`。
公开镜像不等于官方认证，正式评价时仍应向 Clarivate 或历史中科院分区平台复核。

| File / 文件 | SHA-256 |
|---|---|
| `JCR2025-UTF8.csv` | `e9a0402f505264a796615bcec697f843af08dbce023ce67164c0f6f4709207c4` |
| `FQBJCR2025-UTF8.csv` | `481224dca2cacc1cce49afb44c968d734c834e498e5ff054f15efb5a548789fc` |
