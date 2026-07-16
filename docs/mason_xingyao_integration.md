# 梅森 + 星耀综合体

> 更新于 2026-06-19

这个模块把星耀数智的行情数据、你的持仓文件、梅森交易知识库合成一条可复用的盘中决策链。它只做研究和动作卡，不自动交易。

## 数据流

```text
portfolio.local.json / --portfolio
        |
        v
run_portfolio_radar.py
        |
        v
tools/portfolio_radar_engine.py
        |-- 星耀 AmazingData: 快照 / K线 / MA20 / 涨跌幅
        |-- tools/mason_signal_engine.py: 主线 / 乖离 / 双跌 / 同方向风险 / 止损线
        v
data/portfolio_radar.html
data/portfolio_radar.json
```

## 模块分工

| 文件 | 职责 |
|---|---|
| `tools/portfolio_radar_engine.py` | 登录星耀、取行情、组合数据、生成 HTML/JSON |
| `tools/mason_signal_engine.py` | 生成梅森动作卡：持有、不加、可低吸、减仓、清仓 |
| `skills/mason-trading-knowledge/SKILL.md` | Codex 盘中/盘后问答的梅森知识库入口 |
| `tools/index_mason_library.py` | 扫描 `D:\梅森`，生成本地资料索引 |
| `monitor.py` | 主流程调度，运行 ETF 雷达后自动跑持仓雷达 |

## 当前优化点

- 梅森规则层已从雷达引擎抽离，后续可以独立接 DeepSeek 或其他 LLM。
- 雷达会把实际加载的 portfolio 传给梅森分析，不再偷偷读取示例 `portfolio.json`。
- 主题映射已覆盖 ETF 和常见个股：`515050`、`600487`、`600460`、`605376`、`600549`、`000725`、`603678` 等。
- 动作卡对“已持有”和“未持有”做区分：持仓行默认偏向“持有/不加”，候选行才偏向“买/不买”。

## 推荐提问

```text
用梅森+星耀综合体，基于我最新 portfolio.local.json，输出今天盘中动作卡。
```

```text
用星耀拉最新行情，再用梅森同方向风险过滤，告诉我 515050 和 600487 今天只能留哪一个加仓观察。
```

```text
基于上周交易表现和当前持仓，做一次复盘回测模拟：哪些交易符合双跌买点，哪些是追高。
```

```text
用 45 万本金、月目标 6 万做压力测试：需要多少收益率、最大回撤能不能承受、下周只能关注哪 3 条主线。
```
