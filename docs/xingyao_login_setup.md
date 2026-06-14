# 星耀 AmazingData 登录配置

所有星耀数据接口调用前，必须先登录 AmazingData SDK：

```python
import AmazingData as ad

ad.login(
    username="username",
    password="password",
    host="101.230.159.234",
    port=8600,
)
```

本项目统一通过 `monitor.xingyao_login()` 执行登录。业务代码不要直接绕过这个函数调用星耀接口。

## 本机环境变量

```powershell
$env:XINGYAO_ENABLED="true"
$env:XINGYAO_USER="your_xingyao_username"
$env:XINGYAO_PASSWORD="your_xingyao_password"
$env:XINGYAO_HOST="101.230.159.234"
$env:XINGYAO_PORT="8600"
$env:XINGYAO_SDK_PATHS="C:\path\to\amazingdata_sdk;C:\path\to\xingyao_sdk"
```

也兼容 `XINGYAO_USERNAME` 和星耀数智 skills 文档里的 `AD_USERNAME`。密码、host、port 也兼容 `AD_PASSWORD`、`AD_HOST`、`AD_PORT`。

如果按星耀数智 skills 的口令风格配置，可以使用：

```powershell
$env:AD_USERNAME="your_xingyao_username"
$env:AD_PASSWORD="your_xingyao_password"
$env:AD_HOST="101.230.159.234"
$env:AD_PORT="8600"
```

可选备用地址：

```powershell
$env:XINGYAO_HOST="140.206.44.234"
```

## 安全边界

- 不要把真实密码写进代码、README、报告或 GitHub。
- 推荐用 `run_xingyao_data_probe.ps1` 交互输入密码，脚本结束后会清理进程环境变量。
- 本地工作台只展示账号掩码、host、port、SDK 路径数量和接口状态，不展示密码。
- 登录未就绪时，星耀接口只能显示为计划/待联调，动作卡必须降级为观察。

## 探针命令

```powershell
cd C:\Users\Niki_Spatial\Documents\Codex\2026-06-11\files-mentioned-by-the-user-amazingdata\work\Niki-Smart-Tools
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_xingyao_data_probe.ps1 -WithKline
```

脚本会提示输入 SDK 根目录、账号和密码。host/port 默认使用 `101.230.159.234:8600`。

## 星耀数智 skills 与 AmazingData 的关系

星耀数智 skills 是上层 AI 技能编排，包含：

- 金融数据 skill：行情、财务、股东股本等数据。
- 技术面指标 skill：超买超卖、趋势、能量、成交量、均线、路径等指标。
- 基本面指标 skill：盈利、成长、运营效率、盈余质量、安全性、治理、估值、股东、规模等指标。
- 因子分析 skill：因子检验、有效性分析、因子合成、拥挤度、分层回测、IC、回归和报告。

AmazingData/TGW 是底层数据接口，负责登录、取数、缓存、探针和路由。工作台会把两层分开展示：先看登录和数据流是否可用，再看 skills 能力如何进入动作卡、图表、风控和研究库。
