# 财周对照台业务与测试登记

- 规模：中型
- 使用者：连锁零售经营分析员
- 核心规则：自然日期映射四四五财周；提供两年同场促销日期时按促销进度对齐，否则按财周同周同星期对齐；只在双方营业的可比日计差额，孤立第53周单列。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 日销送报 | 检查编码、字段宽度和来源行 | `POST /api/intake` | `app/modules/intake/service.py` | `tests/test_intake.py` |
| M2 财年字段 | 归一修订、业务键和偏移时间 | `POST /api/contract` | `app/modules/contract/service.py` | `tests/test_contract.py` |
| M3 日历冲突 | 定位重复、被替代与矛盾来源 | `POST /api/quality` | `app/modules/quality/versions.py` | `tests/test_quality.py` |
| M4 可比财周 | 按规则复算并追溯证据 | `POST /api/domain` | `app/modules/domain/rule.py` | `tests/test_domain.py` |
| M4b 促销进度 | 提交两年同场促销日期并按活动进度重算 | `POST /api/domain`、`POST /api/runs` | `app/modules/domain/promotion.py` | `tests/test_promotion.py` |
| M5 经营清单 | 核对独立清单和各类差异 | `POST /api/reconcile` | `app/modules/reconcile/service.py` | `tests/test_reconcile.py` |
| M6 财周批次 | 打开历史批次并对原文件复跑 | `POST /api/runs` | `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 月结复核 | 登记复核结论并下载证据 | `POST /api/review/{run_id}` | `app/modules/review/decisions.py` | `tests/test_review.py` |

## 陷阱登记

| TRAP | 现象 | 样例 | 处理位置 | 测试 |
|---|---|---|---|---|
| TRAP-01 | GB18030 来源文件 | legacy.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_gb18030` |
| TRAP-02 | BOM 前缀 | shift.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_bom` |
| TRAP-03 | 备注含引号内换行 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_multiline` |
| TRAP-04 | 分段重复表头 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_repeated` |
| TRAP-05 | 列数不足 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_width` |
| TRAP-07 | 缺测哨兵 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_missing` |
| TRAP-08 | 前导零的单号 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_leading_zero` |
| TRAP-11 | 偏移时刻 UTC 归一 | shift.csv | `app/modules/domain/values.py` | `tests/test_contract.py::test_offsets` |
| TRAP-14 | 同版业务字段冲突 | shift.csv | `app/modules/quality/versions.py` | `tests/test_quality.py::test_conflicting` |
| TRAP-16 | 末行引号截断 | truncated.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_truncated_rejected` |
| TRAP-17 | 旧版列名映射 | legacy.csv | `app/modules/contract/schema.py` | `tests/test_contract.py::test_legacy_aliased` |
| TRAP-18 | 空文件、空白文件与仅表头 | 测试构造 | `app/modules/intake/service.py` | `tests/test_intake.py::test_empty_states` |
| TRAP-26 | 陈旧复核版本拒绝 | 测试构造 | `app/modules/review/decisions.py` | `tests/test_review.py::test_stale` |
| TRAP-23 | outside year | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_outside_year` |
| TRAP-107 | leap week | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_leap_week` |
| TRAP-31 | 促销挪周：财周同星期错配普通日 | 测试构造 | `app/modules/domain/rule.py` | `tests/test_promotion.py::test_promotion_progress_beats_fiscal_week` |
| TRAP-32 | 一边少办一天，普通营业日不得补缺 | 测试构造 | `app/modules/domain/rule.py` | `tests/test_promotion.py::test_short_promotion_does_not_borrow_ordinary_day` |
| TRAP-33 | 同一促销日重复登记，不得重复计入 | promotion.csv | `app/modules/domain/promotion.py` | `tests/test_promotion.py::test_same_date_twice_is_counted_once` |
| TRAP-34 | 促销日停业或无日销，落单并留原因 | 测试构造 | `app/modules/domain/rule.py` | `tests/test_promotion.py::test_closed_or_missing_day_stays_orphaned` |
| TRAP-35 | 促销日落在第53周，单列不配对 | 测试构造 | `app/modules/domain/rule.py` | `tests/test_promotion.py::test_leap_week_promotion_is_listed_not_paired` |
| TRAP-36 | 促销表写法不同但内容相同，重跑不得新增批次 | 测试构造 | `app/manifest.py` | `tests/test_promotion.py::test_batch_identity_uses_canonical_promotion_content` |

## 对账

输入 = 计入 + 隔离 + 重传及版本替换 + 空白记录 + 重复表头。按业务键全外连接，缺失一侧与数值为零分别登记。逐笔差值与总差一致。有促销日期时，本次复算值即促销进度可比差额，外部账与之对账；促销落单与促销表里无对应来源的键在月结复核可查。
