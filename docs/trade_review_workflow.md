# 真实交易复盘工作流

目标：把每一次真实交易都变成可复用样本，而不是盘中凭感觉翻篇。

## 文件分工

| 文件 | 用途 |
|---|---|
| `data/real_trade_journal.csv` | 逐笔真实成交事实台账，不急着评价，只记录发生了什么。 |
| `data/trade_review_samples.csv` | 可配对回合与未平仓样本复盘，记录盈亏、问题标签、下一次规则。 |
| `data/paper_trade_journal.csv` | 原有动作卡/纸面交易台账，用来比较“计划信号”和“真实执行”。 |
| `reviews/daily/*.md` | 每日人话复盘，保留当天核心教训和次日规则。 |

## 每笔交易必须补齐的字段

买入后当天补：

- `ai_context`：是否来自雷达、动作卡、AI 建议、自己临盘判断。
- `review_status`：`open_review`、`closed_review`、`needs_cost`、`partial_closed`。
- `notes`：买入理由、风险线、T+1 处理计划。

卖出后补：

- 是否按原计划卖出。
- 是否由 AI 建议触发。
- 若可配对，写入 `trade_review_samples.csv`。

## 复盘标签

常用 `problem_tag`：

- `profit_taking`：盈利分批兑现，正样本。
- `small_win`：小仓盈利，正样本。
- `late_stop`：止损偏慢。
- `overnight_weak`：尾盘弱仓隔夜。
- `chase_reentry`：刚卖出后高价买回。
- `weak_rebound`：弱反弹失败。
- `old_weak_position`：旧弱仓拖累。
- `small_etf_drag`：ETF 小仓拖累。

## AI 责任字段

`ai_responsibility` 不用于推卸责任，而用于改进辅助系统：

- `none`：主要是用户执行或历史仓位。
- `assistant_supported`：AI 参与了减仓/风控建议。
- `assistant_responsible_for_process`：AI 建议链条不完整，需要改流程。
- `shared_review`：用户执行和 AI 节奏都需要复盘。

## 每日固定流程

1. 收盘后导出成交或 OCR。
2. 更新 `real_trade_journal.csv`。
3. 对能配对的买卖做 FIFO 复盘，写入 `trade_review_samples.csv`。
4. 写一份 `reviews/daily/YYYY-MM-DD_trade_review.md`。
5. 把明日禁止项写清楚：哪些不能追、哪些只能减、哪些继续观察。

## 硬规则

- AI 建议卖出的强势票，次日不能无条件买回。
- 买回价高于昨日卖出价 3% 以上，默认进入追高区。
- 没有回踩、承接、放量三项确认，不允许把“卖飞焦虑”变成买入理由。
- 日内亏损接近 1200 元，只允许减仓和观察。
- 股票短线计划成交额低于 10,000 元，默认禁止开仓；这一档最容易被最低 5 元佣金、卖出印花税和过户费吃掉。
- 股票短线计划成交额在 10,000 到 20,000 元之间，默认不做；只有 A 级强确认、流动性充足、次日退出路径清楚时才允许例外。
- ETF 可以保留更小试错仓，但也要避免把几百几千元的碎单做成高频来回。
- 每笔交易如果没有复盘，就不能算系统进步。
