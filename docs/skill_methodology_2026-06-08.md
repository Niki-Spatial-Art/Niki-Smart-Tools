# Skill Methodology Intake - 2026-06-08

> 用途：把 Anthropic/Perplexity/CICC 等 Skill 实践沉淀成 Niki-Smart-Tools 的可复用设计规则。
> 边界：本文改进系统工程和工作流，不生成任何买卖信号。

## 今日结论

Skill 的价值不是“多写提示词”，而是把可复用经验、脚本、参考资料和模板拆成可路由、可渐进加载、可验证的能力包。

对 Niki-Smart-Tools 来说，后续所有交易辅助 Skill 都按这个原则设计：

- `SKILL.md` 只放路由、核心纪律、读取顺序和关键 Gotchas。
- `references/` 放详细规则、数据源说明、历史案例、风险边界。
- `scripts/` 放 clean radar、回测、老师消息解析、日报生成等确定性流程。
- `examples/` 放好/坏动作卡样例，用来校准输出。
- `assets/` 放动作卡模板、日报模板、报告模板。

## Anthropic/Perplexity 方法论吸收

| 方法 | 对我们的意义 | 落地方式 |
| --- | --- | --- |
| Description 是路由规则 | Skill 能不能被正确调用，首先看描述是否覆盖用户真实说法 | 描述里写“盘前/盘中/复盘/老师消息/雷达漏扫”等触发场景，不写泛泛功能介绍 |
| SKILL.md 是导航页 | 避免每次加载几千字上下文 | 只保留最小必要规则，详细材料拆到 references |
| Gotchas 最值钱 | 记录模型不知道、但我们反复踩坑的经验 | 建 `references/gotchas.md`：强势观察不是买入、缓存不做买入依据、北交所未验证不进早盘池 |
| 重复流程用 scripts | 不让模型每次重新实现同一套流程 | clean radar、position backtest、teacher news parser 全部脚本化 |
| Skill 要做评估 | 不能只看写得顺不顺，要看真实任务是否稳定 | 用固定样例测试：漏扫、涨停禁追、旧仓优先、买入数量为 0 |
| Marketplace 思路 | Skill 先小范围试用，再正式沉淀 | 本地先做 `docs/` + `scripts/`，稳定后再升级为正式 Codex Skill |

## 中金分析师 Skill 分类

中金点睛里的分析师 Skill 对我们有借鉴意义，但它属于“券商认证投研 Skill”，不是可直接复制的开源 Skill。它的核心价值在于：把券商研究、分析师观点、产品服务和客户权限整合到一个受控入口。

| 分类 | 中金形态 | 我们可借鉴 | 我们不做 |
| --- | --- | --- | --- |
| 券商认证投研 Skill | 打开中金点睛，输入 `/` 调用分析师 Skill | 建立“研报/老师消息/官方数据”的统一入口和来源分级 | 不绕过认证，不抓取受限内容 |
| 分析师问答 Skill | 向特定分析师/团队问观点 | 把外部观点拆成主题、代码、验证项、风险项 | 不把分析师观点直接转成买入 |
| 市场策略 Skill | 汇总中期策略、风格判断、行业比较 | 服务盘前“市场状态/风格闸门” | 不用单篇策略覆盖实时风控 |
| 行业研究 Skill | 行业链条、景气度、估值和催化 | 接入 sector rotation 和主题观察池 | 不因行业标题开仓 |
| 产品/配置 Skill | 面向客户做产品解释、配置建议 | 借鉴报告结构：适配人群、风险、配置比例 | 不做销售话术和收益承诺 |
| 合规边界 Skill | 权限、适当性、免责声明 | 强化“不是投资建议、不自动下单、需人工确认” | 不替代投顾/合规流程 |

结论：中金 Skill 更像“机构投研工作台”，Anthropic Skill 更像“工程化能力包”。我们要把两者结合：前者给金融分类，后者给工程结构。

## Niki-Smart-Tools Skill 分类草案

| 层级 | Skill/模块 | 作用 | 当前状态 |
| --- | --- | --- | --- |
| 数据源 | Xingyao/iFind/Eastmoney routing | 行情、K线、缓存回退 | 星耀已接入，iFind fallback 保留 |
| 市场状态 | market regime / sector rotation | 判断宽基、行业、风格是否允许进攻 | 需要继续沉淀周度市场宽度规则 |
| 观察池 | teacher/news/theme intake | 老师消息、财联社、研报标题结构化 | 已人工处理，待脚本化 |
| 动作卡 | action card generator | 持仓、卖出、等待、买入候选、禁买 | 已运行，需补 examples |
| 回测 | position backtest / sequence test | 验证强势观察、回踩买点、胜率中位数 | 已有脚本，星耀优先待完善 |
| 风控 | risk rules / gotchas | 禁追、止损、T+1、仓位、缓存降级 | 已有规则，待拆 references |
| 学习 | learning intake | 每日资料吸收、评级、落地层级 | 已有每日文档 |
| 报告 | daily/weekly report | 复盘、日报、周报、GitHub 沉淀 | 已有 docs/reports 流程 |

## 必须写进 Gotchas 的规则

1. 强势观察不是买入。
2. 涨停、急拉、离 MA20 过远、20 日涨幅过大，默认禁追。
3. 只剩缓存时，所有买入数量写 `0`。
4. 星耀快照/K线可用，不等于期权实时盘口可用。
5. 北交所/京市代码在路由未验证前，不进早盘交易池。
6. 老师消息、券商 Skill、研报标题只进入观察和验证，不直接生成交易。
7. 旧仓风险优先于新题材机会。
8. 任何买入候选必须写明风控状态、数量、触发价、止损价、下一次检查条件。

## 下一步

1. 新建或升级正式 Codex Skill：`niki-trading-command-center`。
2. 把当前长规则拆成 `references/risk_rules.md`、`references/source_map.md`、`references/gotchas.md`。
3. 把老师消息结构化入口做成脚本：输入原文，输出 `code/theme/evidence/ban_reason/next_check`。
4. 给动作卡建立 `examples/good_action_card.md` 和 `examples/bad_chasing_card.md`。
5. 用 10 个历史会话样例做 Skill 路由测试：盘前、盘中、收盘、老师消息、文档学习、雷达漏扫、星耀异常、iFind 超额、期权风险、GitHub 同步。
