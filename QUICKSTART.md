# 快速开始指南（5分钟快速部署）

## 前置要求

- GitHub账户（来自 https://github.com）
- QQ邮箱（或其他支持SMTP的邮箱）
- Git已安装在Windows上

## 第1步：获取QQ邮箱授权码（2分钟）

⚠️ **注意：这是邮箱授权码，不是你的邮箱登录密码！**

1. 登录 [QQ邮箱](https://mail.qq.com)
2. 点击左上角 **设置** → **账户**
3. 找到 **POP3/IMAP/SMTP** 服务，点击 **开启**
4. 用QQ号或手机验证
5. 系统会生成一个 **16位授权码**，例如：`xxxxxxxxxxxx`
6. **保存这个授权码**

## 第2步：在本地初始化项目（1分钟）

你已经有项目文件了，现在初始化为Git仓库：

```powershell
cd C:\Users\Niki_Spatial\bank-rate-monitor

git init
git config --global user.name "Your Name"
git config --global user.email "your-qq@qq.com"
git add .
git commit -m "Initial commit"
git branch -M main
```

## 第3步：在GitHub创建仓库（1分钟）

1. 登录 [GitHub](https://github.com)
2. 点击 **+** → **New repository**
3. 仓库名: `bank-rate-monitor`
4. 选择 **Private**（可选但推荐）
5. 点击 **Create repository**

你会看到如下页面，复制第二个命令框中的内容。

## 第4步：推送代码到GitHub（1分钟）

在PowerShell中运行（替换YOUR_USERNAME为你的GitHub用户名）：

```powershell
git remote add origin https://github.com/YOUR_USERNAME/bank-rate-monitor.git
git push -u origin main
```

可能要求输入GitHub账户/密码或Personal Access Token。

## 第5步：设置GitHub Secrets（1分钟）

1. 打开你的GitHub仓库页面
2. 点击 **Settings**
3. 左侧点击 **Secrets and variables** → **Actions**
4. 点击 **New repository secret**，添加以下三个变量：

### Secret 1: SENDER_EMAIL
```
Name: SENDER_EMAIL
Secret: your-qq@qq.com
```

### Secret 2: SENDER_PASSWORD
```
Name: SENDER_PASSWORD
Secret: xxxxxxxxxxxx  (你的16位授权码，不是邮箱密码)
```

### Secret 3: RECIPIENT_EMAIL
```
Name: RECIPIENT_EMAIL
Secret: receive@qq.com  (你要接收提醒的邮箱，可以相同)
```

## 完成！ 🎉

系统现在已经启动！

### 手动测试（可选）

进入 **Actions** 标签：
1. 选择 **Bank Rate Monitor**
2. 点击 **Run workflow**
3. 等待执行完成
4. 查看邮箱是否收到邮件

### 自动运行

系统已配置为 **每30分钟自动检查一次**。

当发现利差 > 15 个基点且支持实时到账时，你会收到邮件提醒。

## 常见问题快速解答

**Q: 没收到测试邮件？**
A: 
1. 检查SENDER_PASSWORD是否为授权码（不是密码）
2. 检查垃圾邮件文件夹
3. 查看GitHub Actions日志（Actions → run logs）

**Q: 如何修改检查频率？**
A: 编辑 `.github/workflows/monitor.yml`，改这一行：
```yaml
- cron: '*/30 * * * *'  # 改为 */15 (15分钟) 或 */60 (60分钟)
```

**Q: 如何修改利差阈值？**
A: 编辑 `.github/workflows/monitor.yml`，改这一行：
```yaml
env:
  RATE_DIFF_THRESHOLD: 0.10  # 改为0.10 (10基点) 或其他值
```

**Q: GitHub Actions免费吗？**
A: 完全免费。免费账户月度有1000分钟额度，足以运行几个月。

## 后续优化

部署完成后，可以尝试以下优化：

- [ ] 配置钉钉/企业微信通知替代邮件
- [ ] 添加更多银行产品监控
- [ ] 创建Web仪表板查看实时数据
- [ ] 记录历史利率数据用于分析

## 需要帮助？

- 查看 **README.md** - 完整功能说明
- 查看 **SETUP_SECRETS.md** - Secret配置详细指南
- 查看 **DEPLOYMENT.md** - 详细部署步骤
- 查看 **PROJECT_OVERVIEW.md** - 技术架构说明

---

**预计部署时间**: 5-10分钟  
**所需成本**: 0元  
**所需工具**: GitHub账户 + QQ邮箱  

**祝你使用愉快！** 💰
