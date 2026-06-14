# 星耀工作台模块清单 v1

本页记录 2026-06 的工作台调整方向：项目从“iFind 优先的盘中决策工作台”升级为“星耀优先的 A股 / ETF / 期权投研工作台”。iFind 在到期前作为校准源使用；到期后不续费时，东方财富作为星耀的第一候补源。

## 目标定位

星耀不是只作为接口补充，而是工作台的主数据底座。工作台的核心目标是把实时、日频、事件频数据变成可复盘的动作卡、风险雷达和研究资产。

```text
星耀主源
  -> 东方财富候补
  -> 腾讯补充
  -> 新浪应急补价
  -> 缓存 / 观察模式
```

iFind 在 2026-06-22 左右到期前，主要承担校准角色：

- 对比星耀和东方财富的实时价、成交额、涨跌幅、时间戳。
- 检查 ETF、IOPV、期权快照、两融、龙虎榜、财务字段的缺口。
- 为后续不续费后的降级规则提供样本。

## 五层数据刷新

| 层级 | 刷新频率 | 星耀接口/数据 | 工作台用途 |
| --- | --- | --- | --- |
| 实时层 | 10-60 秒 | 指数、股票、ETF、ETF 期权实时快照，实时 K 线 | 盘中主屏、动作卡、观察池、期权第一页 |
| 历史/回测层 | 日频或按需 | 历史快照、历史 K 线、复权因子、交易日历、历史代码表 | 回测、复权切换、均线连续性、历史研究库 |
| 基本面层 | 收盘后或公告后 | 资产负债表、现金流量表、利润表、业绩快报、业绩预告、股东户数、股本结构、质押冻结、限售解禁 | 财务风险、股东风险、长期过滤器 |
| 热度/资金层 | 日内或收盘后 | 两融明细、两融汇总、龙虎榜、大宗交易 | 资金去向、异动观察、明日候选池 |
| ETF/专题层 | 日频，盘中引用 | ETF PCF、基金份额、NAV/IOPV、指数成分权重、行业成分权重和日行情 | ETF 折溢价、行业轮动、指数结构 |

规则：只有实时层进入高频刷新；财务、股东、分红、配股、两融、龙虎榜、ETF 份额、IOPV 等按定时任务写入缓存。

## 工作台页面

### 1. 盘中主屏：星耀实时层

目标：不要堆行情，直接服务“买、卖、等、减仓、继续观察”。

组件：

- 指数 / 股票 / ETF / ETF 期权快照。
- 实时 K 线 + 成交量。
- 盘口新鲜度：`source`、`timestamp`、`freshness`、`confidence`。
- 盘中动作卡：动作、触发条件、失效条件、仓位、风险、下次检查。

### 2. ETF 与行业结构

目标：放大星耀在 ETF 和行业专题数据上的价值。

组件：

- ETF 价格、IOPV、NAV、PCF、基金份额。
- 折溢价率、成交额、份额变化。
- 指数/行业成分、权重、日行情。
- 行业强弱排序和轮动观察池。

### 3. A股基本面与股东风险

目标：把财务和股东数据变成“能不能长期看”的过滤器。

组件：

- 利润、现金流、资产负债表质量。
- 业绩预告 / 快报风险。
- 股东户数变化。
- 股权质押/冻结、限售解禁。
- 基本面风险分和人工复核说明。

### 4. 两融 / 龙虎榜 / 大宗交易资金热度

目标：收盘后生成明日观察池，不做 10 秒轮询。

组件：

- 两融余额、融资买入、融券卖出。
- 龙虎榜上榜原因、买卖席位、净买入。
- 大宗交易价格、折溢价、成交额。
- 明日候选池：强资金、弱资金、噪音、禁追。

### 5. 历史研究库 / 回测 / 复权切换

目标：让星耀的历史代码表、复权因子、交易日历真正进入研究闭环。

组件：

- 历史 K 线和历史快照。
- 前复权 / 后复权 / 不复权切换。
- 历史代码表和退市/改名处理。
- 策略回放、买卖点标记、no-trade 样本。

## 图表内核：Lightweight Charts

采用 `tradingview/lightweight-charts` 作为前端图表标准。React 中不优先依赖老 wrapper，而是封装项目自己的 `XingyaoChartEngine`。

```text
XingyaoChartEngine
  - CandlestickSeries: 星耀历史 K 线 + 实时 K 线
  - HistogramSeries: 成交量、MACD 柱、溢价率柱
  - LineSeries: MA、VWAP、IOPV、NAV、成本线、止损线
  - Markers: 买点、卖点、止损、龙虎榜、财报、两融异动
  - PriceLine: 昨收、目标价、止损价、ETF IOPV/NAV
  - Crosshair Sync: 个股 / ETF / 行业 / 期权标的联动
  - Source Badge: 星耀 / 东财 / 缓存 / 延迟秒数
```

首批图表功能：

- 多周期切换：1m、5m、15m、30m、日 K、周 K。
- 实时 `update()`：星耀优先，东财候补。
- 历史懒加载：滚动到左侧时补历史 K 线。
- 事件标记：龙虎榜、财报、两融、解禁、动作卡。
- ETF 参考线：IOPV、NAV、折溢价阈值。
- 回测回放：逐根 K 线播放，复盘策略信号。

## 仪表盘组件层：ChartKit

ChartKit 可以作为工作台的 KPI 和小图组件层，但不替代 `lightweight-charts` 的金融主图。

分工：

| 层级 | 推荐库 | 用途 |
| --- | --- | --- |
| 金融主图 | `lightweight-charts` | K 线、成交量、价格线、事件标记、十字线联动、回测回放 |
| 仪表盘组件 | `@derpdaderp/chartkit` | KPI 卡、Sparkline、Gauge、Heatmap、ProgressRing、MiniArea、主题化小图 |

ChartKit 适合放在这些位置：

- 盘中主屏：`KpiCard` 显示实时涨跌、成交额、数据新鲜度、风险等级。
- ETF 折溢价页：`GaugeChart` 显示折溢价危险区，`Sparkline` 显示日内溢价轨迹。
- 行业轮动页：`Heatmap` 显示行业强弱，`BarChart` 显示权重和涨跌贡献。
- 资金热度页：`SpikeChart` / `MiniArea` 显示两融、龙虎榜、大宗交易热度变化。
- 风控页：`ProgressRing` 显示仓位、现金底线、单票风险预算。

采用原则：

- K 线、期权标的、ETF IOPV/NAV 参考线仍然由 `lightweight-charts` 负责。
- ChartKit 只做看板级小图和指标卡，服务“好看、快读、低配置”。
- 主题优先选 `midnight` 或深色专业风格，但避免让页面变成单一蓝紫色调。
- 若后续项目仍保持纯 Python 本地页面，可先按 ChartKit 的组件结构设计 UI，等切 React/Next.js 时再接入 npm 包。

## 数据源路由规则

| 场景 | 主源 | 第一候补 | 第二候补 | 降级规则 |
| --- | --- | --- | --- | --- |
| 盘中实时快照 | 星耀 | 东方财富 | 腾讯/新浪单票 | 降为观察，不输出高置信动作 |
| ETF/期权 | 星耀 | 东方财富局部补 | 缓存 | 标记字段缺口 |
| 历史 K 线/复权 | 星耀 | 东方财富/腾讯 | 缓存 | 禁止回测写入正式结论 |
| 行业/概念/热度 | 东方财富 | 星耀专题数据 | 缓存 | 只做候选池，不做买入触发 |
| 财务/股东/两融/龙虎榜 | 星耀 | 东方财富 | 缓存 | 收盘后刷新，不实时轮询 |

每个数据对象都必须携带：

```json
{
  "source": "xingyao",
  "timestamp": "2026-06-12 10:31:00",
  "freshness": "real_time",
  "confidence": "high"
}
```

当 `freshness` 不是 `real_time` 或 `close_verified` 时，动作卡默认降级为观察。

## 实时流层：WebSocket / 订阅池

如果星耀支持订阅式实时行情，应优先使用 WebSocket 或 SDK 订阅流；如果星耀只能查询快照，则用 10-60 秒低频轮询，并让东方财富承担候补。不要全市场高频轮询。

目标架构：

```text
订阅池
  -> WebSocket/SDK callback
  -> 内存队列
  -> 1 秒聚合快照
  -> 分钟 K 生成
  -> 前端 chart.update()
  -> 批量写入缓存/数据库
```

订阅分级：

| 等级 | 标的 | 刷新方式 | 用途 |
| --- | --- | --- | --- |
| L0 | 当前持仓、今日动作卡、ETF期权标的 | WebSocket/SDK 订阅优先；否则 10 秒轮询 | 盘中动作卡、止损/止盈、数据新鲜度 |
| L1 | ETF观察池、强势观察池、行业龙头 | 30-60 秒轮询或分组订阅 | 候选池和异动提醒 |
| L2 | 全市场扫描、行业/概念热度 | 盘前/盘中低频/收盘后批处理 | 研究和候选生成 |
| L3 | 财务、股东、两融、龙虎榜、ETF份额 | 日频/事件频 | 风控和明日计划 |

实时流规则：

- 只订阅必要标的，不全量订阅。
- 前端不要逐 tick 渲染，先聚合成最新快照或分钟 K。
- 存储不要逐 tick 同步写库，先缓存，按分钟或批次落盘。
- 清洗异常数据：成交量为 0、价格明显偏离、时间戳倒退、字段缺失。
- 断线自动重连，超过阈值后切东财候补；候补也失败时进入缓存观察模式。
- 每条行情保留 `source`、`timestamp`、`freshness`、`latency_ms`、`confidence`。

## 纸面交易与交易日记层

借鉴 Backtest Homie 这类产品时，重点不是复制页面，而是吸收它的闭环：

```text
动作卡
  -> 纸面交易计划
  -> 模拟成交 / 真实成交手动记录
  -> 交易日记
  -> 表现统计
  -> K线回放
  -> 规则修正
```

工作台应新增/强化：

| 模块 | 功能 | 星耀数据配合 |
| --- | --- | --- |
| Paper Trading Dashboard | 计划买入、计划卖出、模拟成交、T+1退出计划 | 实时快照、实时K线、动作卡 |
| Trade Diary | 入场理由、风险闸门、计划仓位、实际成交、退出理由、复盘评分 | K线标记、财务/事件风险、资金热度 |
| Performance Analytics | 胜率、盈亏比、平均持仓天数、最大回撤、规则遵守率 | 历史K线、复权因子、交易日历 |
| Pattern Review | 追高、早卖、迟止损、仓位过大、数据过期等错误分类 | 动作卡和实际成交对比 |
| Replay Mode | 历史K线逐根播放，叠加买卖点、no-trade样本和事件 | Lightweight Charts 回放 |

原则：

- 纸面交易不等于自动交易，真实下单仍由人工确认。
- 没买的票也保留 no-trade 样本，用来判断过滤条件是否太严。
- 每笔计划必须回答：为什么做、哪里失效、亏多少、T+1怎么处理。
- 表现分析优先看规则遵守率和亏损控制，不只看赚钱与否。

## 阿里云百炼 / DashScope 用法

百炼不参与价格计算和下单，只做解释层、知识库层和工作流层。

| 能力 | 工作台用途 |
| --- | --- |
| Qwen Flash | 低成本标签、异动一句话解释 |
| Qwen Plus | 盘中动作卡、ETF/行业解释、复盘摘要 |
| Qwen Max | 多步骤风险归因、追高/不追的推理说明 |
| 知识库 RAG | 星耀手册、字段说明、个人交易规则问答 |
| 工作流 | 收盘后自动跑两融、龙虎榜、财务风险、明日观察池 |
| 插件/MCP | 让模型调用星耀、东财、回测、数据库工具 |

落地原则：

- AI 只解释证据，不生成不带数据来源的买卖结论。
- AI 输出必须引用数据新鲜度和风险闸门。
- 没有实时数据或字段缺口时，AI 必须提示降级。

## GitHub 搜索关键词

### 图表与前端

```text
lightweight-charts react v5 example
lightweight-charts candlestick volume markers
lightweight-charts price line markers
lightweight-charts crosshair sync multiple charts
lightweight-charts websocket realtime update
lightweight-charts backtesting replay
financial dashboard react lightweight-charts
chartkit react dashboard kpi sparkline gauge heatmap
@derpdaderp/chartkit financial dashboard
stock screener react fastapi
```

### 数据管道

```text
akshare stock dashboard fastapi
efinance 东方财富 Python dashboard
market monitor websocket redis
duckdb parquet market data
timescaledb market data
apscheduler stock data pipeline
```

### ETF/期权/行业

```text
ETF premium discount dashboard
ETF IOPV NAV price line
ETF PCF arbitrage dashboard
options chain implied volatility python
options greeks dashboard
put call ratio dashboard
sector rotation dashboard
china ETF options dashboard
```

### 星耀专项

```text
AmazingData Python SDK ETF options
AmazingData real time snapshot kline
星耀 实时行情工作台
星耀 ETF IOPV 折溢价
星耀 ETF期权快照
星耀 两融 龙虎榜 大宗交易
星耀 复权因子 历史代码表 回测
星耀 股东户数 股权质押 限售解禁
```

## 首批实施清单

1. 新增数据源路由器：星耀主源、东财候补、腾讯/新浪应急、缓存观察模式。
2. 新增 `latest_xingyao_workbench_probe.json`，汇总实时层、历史层、基本面层、资金层、ETF 专题层状态。
3. 本地工作台增加“星耀五层状态”页。
4. 前端升级计划中锁定 `lightweight-charts` 为图表内核。
5. 收盘后任务新增：两融、龙虎榜、大宗交易、财务/股东风险、ETF 专题缓存。
6. 百炼知识库准备：星耀手册、字段映射、个人交易规则、动作卡模板。
7. 维护 `docs/xingyao_interface_utilization_audit.md`，逐项核对星耀目录是否进入工作台、是否有刷新频率和动作边界。

## 密钥边界

需要联调星耀或 iFind 时再临时询问账号、密码或 token。密钥只放本地 `.env` 或 GitHub Secrets，不写入 README、报告、日志和提交历史。
