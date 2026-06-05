# iFind 授权与隐私说明

本项目公开后，别人不能、也不应该使用你的 iFind 接口。iFind token、券商截图、真实持仓、成交记录都属于个人敏感信息，只能保存在本机或自己的私有环境里。

## 谁来提供 iFind

每个使用者必须配置自己的 iFind 账号和接口权限。

项目只提供连接器、探针、动作卡和回测框架，不提供任何公共 iFind token，也不会把你的 token 写进 GitHub。

## 本地 token 放哪里

推荐只放在本机 `.env`：

```text
IFIND_REFRESH_TOKEN=your_ifind_refresh_token
IFIND_API_BASE_URL=https://quantapi.51ifind.com/api/v1
IFIND_TIMEOUT=30
```

也可以临时使用环境变量，但不要写进文档、聊天记录、提交记录或截图。

## 绝对不要提交的内容

- `.env`
- `portfolio.local.json`
- `data/latest_ifind_http_probe.json`
- `data/broker_account_snapshots.json`
- 券商截图、成交明细、真实持仓、真实现金
- 任何 `IFIND_ACCESS_TOKEN` / `IFIND_REFRESH_TOKEN`

## 没有 iFind 怎么用

没有 iFind 的用户仍然可以把本项目作为 A股 / ETF 交易纪律工作台模板使用：

- 可以使用公开行情源做基础观察。
- 可以使用纸面交易日志、动作卡模板、盘后复盘模板。
- 可以使用本地工作台查看计划、日志、维护记录。
- iFind 实时行情、历史行情、公告、智能选股、基础数据会显示“未配置 / 未接通 / 本轮未运行”。

没有 iFind 时，项目不应给出“高置信买入动作卡”，只能降级为观察和复盘。

## iFind 功能依赖表

| 功能 | 是否依赖 iFind | 没有 iFind 时 |
| --- | --- | --- |
| 实时行情复核 | 强依赖 | 用公开行情源降级，只做观察 |
| 历史回测 | 强依赖 | 可用本地 CSV 或公开日线替代，但置信度下降 |
| 公告风险闸门 | 强依赖 | 需要人工查公告或跳过该闸门 |
| 智能选股 | 强依赖 | 不运行该模块 |
| 纸面交易日志 | 不依赖 | 正常使用 |
| 每日维护记录 | 不依赖 | 正常使用 |
| 本地工作台 | 不依赖 | 正常打开，但显示数据缺口 |

## 对外介绍口径

推荐这样介绍：

> 本项目以 iFind 为高质量数据源设计；如无 iFind 权限，可作为 A股 / ETF 交易纪律工作台模板使用，并通过公开行情源降级运行。使用者必须配置自己的数据源凭证，项目不会共享或托管任何 iFind token。

