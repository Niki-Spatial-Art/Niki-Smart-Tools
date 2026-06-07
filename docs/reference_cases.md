# 优秀案例借鉴

本项目不是要复制成熟平台，而是借鉴它们的结构，把个人 A股 / ETF 盘中交易工作台做得更清楚、更少架构、更可维护。

## OpenBB

借鉴点：把金融数据平台做成统一入口，服务分析师、量化研究和 AI Agent。

参考链接：

- <https://github.com/OpenBB-finance/OpenBB>
- <https://openbb.co/blog/why-we-are-building-the-openbb-platform/>

落地到本项目：

- 数据源状态集中展示。
- iFind、东方财富、券商截图、学习报告都进入同一个工作台。
- 页面不只显示信号，还显示数据来源、新鲜度和缺口。

## QuantConnect LEAN

借鉴点：研究、回测、实盘框架分层清楚，策略不是一句口号，而是可重复验证的流程。

参考链接：

- <https://github.com/QuantConnect/Lean>
- <https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine>

落地到本项目：

- 每张动作卡必须有假设、样本、买点、止损和复盘。
- 强势观察票不能只看涨幅，要回到历史样本和 T+1 风险。
- 每日维护记录沉淀“今天学到什么，明天怎么改”。

## Freqtrade

借鉴点：交易策略、配置、回测、模拟运行、风险保护有清晰边界。

参考链接：

- <https://github.com/freqtrade/freqtrade>

落地到本项目：

- 本项目只做本地决策支持和纸面日志，不自动下单。
- 没有真实成交时，不计算 PnL，只保留 no-trade 样本。
- 把“买不买”拆成数据闸门、风险闸门、仓位闸门。

## 组合风险与纸面交易参考

借鉴点：先把组合构建、压力测试、纸面仿真和期权风险说明做扎实，再决定哪些内容值得进入动作卡。

参考链接：

- <https://github.com/PyPortfolio/PyPortfolioOpt>
- <https://github.com/dcajasn/Riskfolio-Lib>
- <https://github.com/skfolio/skfolio>
- <https://github.com/mootdx/mootdx>
- <https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document>
- <https://docs.alpaca.markets/us/docs/paper-trading>

落地到本项目：

- ETF 组合不只看涨跌和主题叙事，还要补权重、相关性、回撤和风险预算。
- A 股公开数据兜底优先补“交叉校验”能力，不把公共连接器直接变成自动下单入口。
- 期权研究先对齐官方风险披露和术语，再做 Greeks、波动率和情景分析。
- 纸面交易文档优先吸收“仿真不等于实盘”的限制说明，用来约束复盘口径和动作卡置信度。

## MongoDB / AI Search 架构思路

借鉴点：AI 应用最好的架构往往是更少的架构。减少外部同步、减少手工 embedding、减少重复系统，能降低维护成本。

落地到本项目：

- 把每日维护记录、动作卡、回测摘要、数据缺口放进同一个本地工作台。
- 优先减少人工复制粘贴和多处口径不一致。
- 未来可考虑把复盘文本、动作卡、公告摘要做成统一检索层，但当前版本不引入新数据库，先保持轻量。
