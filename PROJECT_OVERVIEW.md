# 项目概览

## 整体介绍

这是一个**实时银行利率监控系统**，专门监控：
- 招商银行(CMB)大额存单转让区 7 天利率
- 微众银行(WeBank) 7 天理财利率

当两者利差 > 15 个基点且招商银行支持实时到账时，自动发邮件通知。

## 项目优势

✅ **完全免费** - 基于GitHub Actions，无需购买服务器  
✅ **自动化** - 每30分钟自动检查，无需人工干预  
✅ **安全可靠** - 使用GitHub Secrets保护敏感信息  
✅ **易于定制** - 支持修改检查频率、利差阈值等参数  
✅ **实时通知** - 发现套利机会立即邮件提醒  

## 项目结构

```
bank-rate-monitor/
│
├── 核心脚本
│   ├── monitor.py              # 主监控脚本（GitHub Action调用）
│   ├── scraper.py              # 爬虫模块（获取利率数据）
│   └── emailer.py              # 邮件模块（发送通知）
│
├── 配置和依赖
│   ├── requirements.txt         # Python依赖列表
│   └── .gitignore             # Git忽略文件
│
├── 调试和测试
│   └── test_local.py          # 本地测试脚本
│
├── GitHub自动化
│   └── .github/
│       └── workflows/
│           └── monitor.yml    # GitHub Action工作流配置
│
└── 文档
    ├── README.md              # 完整功能说明和使用指南
    ├── SETUP_SECRETS.md       # GitHub Secrets配置指南
    ├── DEPLOYMENT.md          # 一步步部署指南
    └── PROJECT_OVERVIEW.md    # 此文件
```

## 工作流程

```
GitHub Action触发
    ↓
解析environment variables
    ↓
运行monitor.py
    ├─→ CMBScraper: 获取招商银行利率
    ├─→ WEBankScraper: 获取微众银行利率
    └─→ RateMonitor: 计算利差，判断是否触发
         ↓
      利差 > 15BP?
      且支持实时到账?
         ↓
        YES
         ├─→ EmailNotifier: 构建邮件
         └─→ 发送提醒邮件
        
        NO
         └─→ 继续监控
```

## 关键特性说明

### 1. 利率爬虫（scraper.py）

**CMBScraper类：**
- 调用招商银行API获取大额存单转让区数据
- 提取7天期产品利率
- 检查是否支持T+0实时到账

**WEBankScraper类：**
- 调用微众银行API获取理财产品数据
- 提取7天期理财产品利率
- 返回产品名称和利率

**RateMonitor类：**
- 综合两个爬虫的数据
- 计算利差（百分点转换为基点）
- 判断是否满足触发条件
- 生成监控报告

### 2. 邮件通知（emailer.py）

**EmailNotifier类：**
- 支持SMTP协议，配置QQ邮箱SMTP服务
- 使用TLS加密连接
- 支持HTML和纯文本两种格式
- 优雅处理邮件发送异常

### 3. 主监控脚本（monitor.py）

- 读取GitHub Secrets中的配置
- 调用RateMonitor进行监控
- 如果发现机会，调用EmailNotifier发送邮件
- 记录执行日志到GitHub Actions console

### 4. GitHub Action工作流（monitor.yml）

```yaml
trigger: 每30分钟（cron表达式: */30 * * * *）
steps:
  - 检出代码
  - 设置Python环境
  - 安装依赖
  - 运行monitor.py
  - 记录执行日志
```

## 配置参数

| 参数 | 默认值 | 说明 | 位置 |
|-----|-------|------|------|
| 检查频率 | 30分钟 | 两次检查间隔 | `.github/workflows/monitor.yml` |
| 利差阈值 | 15基点 | 触发邮件的最小利差 | `RATE_DIFF_THRESHOLD` |
| SMTP服务器 | smtp.qq.com | 邮件服务器 | `emailer.py` |
| SMTP端口 | 587 | SMTP端口号 | `emailer.py` |
| 超时时间 | 10秒 | API请求超时 | `scraper.py` |

## 使用场景

### 场景1：日常监控
- 系统每30分钟自动检查一次利率
- 在后台静默运行，不产生干扰
- 发现机会才会邮件通知

### 场景2：活期存款理财
- 有部分闲置资金可随时支配
- 高利差出现时可立即投资
- 利用T+0到账快速套利

### 场景3：多产品比较
- 可扩展监控更多银行产品
- 建立产品利率数据库
- 制定最优投资策略

## 扩展方向

### 简单扩展
1. **修改检查频率** - 改 cron 表达式
2. **调整利差阈值** - 改 RATE_DIFF_THRESHOLD
3. **修改邮箱** - 改 GitHub Secrets
4. **更换邮箱服务商** - 改 SMTP 配置

### 中等扩展
1. **添加WebHook通知** - 支持钉钉、企业微信
2. **增加通知渠道** - 短信、企业微信、Slack
3. **数据持久化** - GitHub Gist 或 云数据库
4. **历史数据分析** - 记录利率变化趋势

### 高级扩展
1. **Web仪表板** - GitHub Pages 展示实时数据
2. **多账户管理** - 支持多个投资账户
3. **智能预测** - 机器学习预测利率变化
4. **交易自动化** - 自动下单投资

## 成本分析

| 项目 | 成本 | 说明 |
|-----|------|------|
| GitHub | 免费 | GitHub Actions免费,Pro账户更多额度 |
| 服务器 | 免费 | GitHub Action提供的虚拟机 |
| 邮箱 | 免费 | 使用个人QQ邮箱 |
| API | 免费 | 使用公开API,无需认证 |
| **总成本** | **0** | **完全免费** |

## 技术栈

| 技术 | 用途 | 版本 |
|-----|------|------|
| Python | 编程语言 | 3.11 |
| requests | HTTP请求 | 2.31.0 |
| BeautifulSoup4 | HTML解析 | 4.12.2 |
| lxml | XML处理 | 4.9.3 |
| smtplib | 邮件发送 | Python内置 |
| GitHub Actions | CI/CD平台 | v4 |
| PowerShell | 本地测试 | 原生支持 |

## 安全性考虑

✓ **Secrets管理** - 敏感信息存储在GitHub Secrets中  
✓ **代码权限** - 使用Personal Access Token进行认证  
✓ **日志安全** - GitHub自动掩盖Secrets输出  
✓ **仓库隐私** - 建议设为Private仓库  
✓ **定期更新** - 定期更换邮箱授权码  

## 性能指标

- **API响应时间** - 通常 < 2秒
- **邮件发送时间** - 通常 < 3秒
- **GitHub Action执行时间** - 通常 < 30秒
- **总执行时间** - < 1分钟
- **网络资源消耗** - 每次 ~5KB
- **GitHub Action额度消耗** - 每次 ~10秒（月额度：10,000分钟）

## 故障排查

### 常见问题

| 问题 | 可能原因 | 解决方案 |
|-----|---------|---------|
| 工作流显示失败 | Secrets配置错误 | 检查Secrets拼写和值 |
| 收不到邮件 | 邮箱授权码错误 | 使用QQ邮箱生成新授权码 |
| API超时 | 网络问题或API异常 | 查看详细日志,稍后重试 |
| 日志中有密钥 | 代码中硬编码密钥 | 使用Secrets替代 |

## 学习资源

- [GitHub Actions文档](https://docs.github.com/en/actions)
- [Python requests库](https://requests.readthedocs.io/)
- [BeautifulSoup文档](https://www.crummy.com/software/BeautifulSoup/)
- [Python SMTP邮件](https://docs.python.org/3/library/smtplib.html)

## 许可和免责

- **许可证** - MIT License
- **免责声明** - 本系统仅用于学习和参考,使用者自行承担使用风险
- **市场风险** - 利率变化遵循市场规律,系统仅提供监控和通知

## 联系和反馈

- 有问题/改进建议? 提出Issue
- 想要贡献代码? 提交Pull Request
- 需要帮助? 查看详细文档或提出Issue

---

**最后更新**: 2026年3月30日  
**维护者**: Your Name  
**版本**: 1.0.0
