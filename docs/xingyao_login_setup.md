# 星耀 AmazingData 登录配置

> **状态：✅ 已打通 (2026-06-18 验证)**
> 
> SDK tgw-1.0.8.7 + AmazingData-1.1.6-cp313 已安装到隔离 Python venv。
> Windows 用户级环境变量已配置，可直接登录使用。

所有星耀数据接口调用前，必须先登录 AmazingData SDK：

```python
import AmazingData as ad

ad.login(
    username="username",
    password="password",
    host="101.230.159.234",   # 电信
    # host="140.206.44.234",  # 联通备用
    port=8600,
)
```

## 当前配置环境

| 项目 | 状态 |
|------|------|
| SDK 版本 | AmazingData 1.1.6 + tgw 1.0.8.7 |
| Python | 3.13.12 (隔离 venv) |
| 安装路径 | `~/.workbuddy/binaries/python/envs/default/` |
| 服务器 | 101.230.159.234:8600 (电信) |
| 有效期 | 2026-05-21 ~ 2027-05-21 |
| 交易日历 | ✅ 8664 个，最新 2026-06-18 |
| A 股列表 | ✅ 5528 只 |
| ETF 列表 | ✅ 1563 只 |
| K 线查询 | ✅ 正常 |
| 财务报表 | ✅ 利润表/资产负债表/现金流量表 |
| 实时快照 | ⚠️ 接口可调用，需验证盘中延迟 |
| 本地缓存 | ⚠️ D:\AmazingData_local_data\ 需创建并授权 |

## 环境变量

### 方式一：AD_* 命名（推荐，与星耀官方一致）

```powershell
[System.Environment]::SetEnvironmentVariable('AD_USERNAME', '你的账号', 'User')
[System.Environment]::SetEnvironmentVariable('AD_PASSWORD', '你的密码', 'User')
[System.Environment]::SetEnvironmentVariable('AD_HOST', '101.230.159.234', 'User')
[System.Environment]::SetEnvironmentVariable('AD_PORT', '8600', 'User')
```

### 方式二：XINGYAO_* 命名（与 Niki-Smart-Tools 兼容）

```powershell
$env:XINGYAO_ENABLED="true"
$env:XINGYAO_USER="你的账号"
$env:XINGYAO_PASSWORD="你的密码"
$env:XINGYAO_HOST="101.230.159.234"
$env:XINGYAO_PORT="8600"
```

### 方式三：GitHub Actions Secrets

在仓库 Settings → Secrets and variables → Actions 中添加：
- `XINGYAO_ENABLED` = `true`
- `XINGYAO_USER` = 你的账号
- `XINGYAO_PASSWORD` = 你的密码
- `XINGYAO_HOST` = `101.230.159.234`
- `XINGYAO_PORT` = `8600`

## 代码调用

### 通过 connectors/xingyao.py（推荐）

```python
from connectors.xingyao import login, get_kline, get_calendar, diagnostics

# 诊断
print(diagnostics())

# 获取 K 线
kline = get_kline(["510050.SH"], 20260601, 20260618, period="day")
```

### 通过 monitor.py（兼容旧代码）

```python
import monitor

monitor.add_xingyao_sdk_paths()
monitor.xingyao_login()

# 获取快照
rows = monitor.fetch_xingyao_snapshot_rows(["510050.SH", "588000.SH"])
```

## 安全边界

- ❌ 不要把真实密码写进代码、README、报告或 GitHub
- ✅ 使用 Windows 用户级环境变量（永久，不随终端关闭消失）
- ✅ 密码在日志中自动掩码（仅显示前 3 位）
- ✅ `.env` 文件在 `.gitignore` 中已排除
- ⚠️ `D:\AmazingData_local_data\` 缓存目录需手动创建并给予 WorkBuddy 沙箱写入权限

## 快速测试

```bash
# 在 WorkBuddy 隔离 venv 中测试
"C:/Users/Niki_Spatial/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -c "
from connectors.xingyao import diagnostics
import json
print(json.dumps(diagnostics(), ensure_ascii=False, indent=2))
"
```

## 常见问题

**Q: ImportError: No module named 'AmazingData'**
A: 需要安装 tgw 和 AmazingData wheel 包到 Python 环境。

**Q: TGW Logon failed / Permission denied**
A: 需要在 WorkBuddy 沙箱中授予 `C:\Users\Public\Documents\mdga_file\` 读写权限。

**Q: 财务数据报 pytables 错误**
A: `pip install tables` 安装 HDF5 支持。

**Q: 本地缓存写入失败**
A: 手动创建 `D:\AmazingData_local_data\`，并授予 WorkBuddy 沙箱写入权限。
