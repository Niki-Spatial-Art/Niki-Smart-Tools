# 部署步骤指南

本指南将引导你完整部署银行利率监控系统到GitHub。

## 部署前检查清单

- [ ] 已准备好QQ邮箱及授权码
- [ ] 已安装Git（Windows版本）
- [ ] 拥有GitHub账户
- [ ] 仓库名称计划好（例如：bank-rate-monitor）

## 部署步骤

### 步骤1: 本地测试（可选但强烈推荐）

在将代码上传到GitHub前，先在本地测试邮件功能。

```powershell
# 1. 进入项目目录
cd C:\Users\Niki_Spatial\bank-rate-monitor

# 2. 安装依赖
pip install -r requirements.txt

# 3. 设置环境变量（用你自己的邮箱）
$env:SENDER_EMAIL='your-qq@qq.com'
$env:SENDER_PASSWORD='xxxxxxxxxxxx'  # 16位授权码
$env:RECIPIENT_EMAIL='receive@qq.com'

# 4. 运行本地测试
python test_local.py
```

**预期输出：**
- ✓ 利率监控功能正常
- ✓ 邮件发送成功
- 收到测试邮件

如果任何一步失败，查看错误信息并修复，再继续。

### 步骤2: 初始化Git仓库

```powershell
# 进入项目目录
cd C:\Users\Niki_Spatial\bank-rate-monitor

# 初始化Git仓库
git init

# 设置Git用户信息（如果还没设置过）
git config --global user.name "Your Name"
git config --global user.email "your-email@qq.com"

# 添加所有文件到Git
git add .

# 创建初始提交
git commit -m "Initial commit: Bank rate monitoring system"

# 重命名分支为main（GitHub默认分支）
git branch -M main
```

### 步骤3: 在GitHub创建仓库

1. 打开 [GitHub](https://github.com)
2. 点击右上角 **+** → **New repository**
3. 填写仓库信息：
   - **Repository name**: `bank-rate-monitor`
   - **Description**: `Real-time bank rate monitoring system (CMB vs WeBank)`
   - **Public/Private**: 建议选择 **Private**（私有）以避免暴露邮箱信息
   - **Create repository** 不用初始化README（我们已有）

4. 仓库创建成功后，你会看到一个页面，显示将本地仓库推送到GitHub的命令

### 步骤4: 推送代码到GitHub

将本地代码推送到你刚创建的GitHub仓库：

```powershell
# 添加远程仓库地址（替换YOUR_USERNAME为你的GitHub用户名）
git remote add origin https://github.com/YOUR_USERNAME/bank-rate-monitor.git

# 推送代码到GitHub
git push -u origin main
```

**提示：** 可能需要输入GitHub账户信息或使用Personal Access Token。

如果使用HTTPS遇到认证问题，可以改用SSH或配置Personal Access Token：
1. 进入 Settings → Developer settings → Personal access tokens
2. 点击 "Generate new token"
3. 勾选 `repo` 权限
4. 生成token后用作密码登录

### 步骤5: 配置GitHub Secrets

这一步至关重要，决定了邮件能否正常发送。

1. 打开你的GitHub仓库页面
2. 点击 **Settings** （仓库设置）
3. 左侧菜单点击 **Secrets and variables** → **Actions**
4. 点击 **New repository secret** 按钮

#### 添加第一个Secret: SENDER_EMAIL

```
Name: SENDER_EMAIL
Secret: your-qq@qq.com  (你的发件邮箱)
```
点击 **Add secret**

#### 添加第二个Secret: SENDER_PASSWORD

```
Name: SENDER_PASSWORD
Secret: xxxxxxxxxxxx  (16位授权码，NOT 邮箱密码)
```
点击 **Add secret**

**⚠️ 重要：这必须是邮箱授权码，不是邮箱登录密码！**

#### 添加第三个Secret: RECIPIENT_EMAIL

```
Name: RECIPIENT_EMAIL
Secret: receive@qq.com  (收件邮箱，可以和SENDER_EMAIL相同)
```
点击 **Add secret**

验证三个Secrets都显示在列表中。

### 步骤6: 启用GitHub Actions

1. 进入仓库的 **Actions** 标签
2. 如果这是第一次，可能会看到提示"I understand my workflows, go ahead and enable them"
3. 点击按钮启用Actions
4. 你应该看到 **Bank Rate Monitor** 工作流列在左侧

### 步骤7: 测试工作流

#### 手动运行测试

1. 进入 **Actions** 标签
2. 左侧选择 **Bank Rate Monitor** 工作流
3. 右侧点击 **Run workflow** → 选择 **main** 分支 → **Run workflow**
4. 等待3-5分钟执行完成

#### 查看执行日志

1. 点击刚刚运行的工作流
2. 点击 **monitor** job
3. 展开各个步骤查看日志
4. 查看是否有错误信息

#### 检查邮件

- 查看你的收件箱是否收到邮件
- 检查垃圾邮件/促销文件夹
- 如果没收到，查看GitHub Actions日志寻找错误

### 步骤8: 定期监控设置

工作流现在已设置为每30分钟自动运行一次。

可选优化：
- 进入仓库 → **Settings** → **Actions** → **General**
- 配置Actions的访问权限和默认行为

## 验证部署成功

✓ 仓库已在GitHub上创建  
✓ 代码已推送到GitHub  
✓ Secrets已正确配置（3个）  
✓ GitHub Actions可以手动触发  
✓ 经过手动测试，邮件正常发送  
✓ 自动工作流每30分钟运行一次  

如果所有项都勾选，部署完成！

## 部署后管理

### 监控工作流执行

```powershell
# 进入GitHub仓库
# 点击 Actions 标签
# 查看最近的运行记录
```

### 查看执行结果

每次工作流运行时，GitHub会：
1. 获取最新代码
2. 安装依赖
3. 运行监控脚本
4. 如果发现套利机会，自动发邮件

### 手动运行工作流

任何时候都可以进入Actions标签手动运行：
1. 选择 **Bank Rate Monitor** 工作流
2. 点击 **Run workflow**
3. 检查执行结果

### 更新代码

如果需要修改阈值或添加新功能：

```powershell
# 修改本地文件后
git add .
git commit -m "Updated rate threshold to 0.10"
git push origin main

# GitHub Actions会自动使用新代码
```

### 停用/删除工作流

- 禁用：进入 **Actions** → 工作流右侧 → **...** → Disable
- 删除：删除 `.github/workflows/monitor.yml` 文件并推送

## 常见问题

### Q: 工作流显示"待机中"怎么办？
A: 这是正常的。工作流在指定时间（每30分钟）自动运行，无需人工干预。

### Q: 如何修改检查频率？
A: 编辑 `.github/workflows/monitor.yml` 文件，修改 `cron` 表达式。

### Q: 邮件发送失败怎么办？
A: 检查GitHub Secrets是否正确，尤其是SENDER_PASSWORD必须是授权码。

### Q: 能否禁用邮件只做监控？
A: 可以，注释掉 `monitor.py` 中的 `notifier.send_alert()` 调用。

### Q: GitHub Actions免费吗？
A: 是的，免费账户每月有足够的免费额度（1000分钟+）。

## 获取帮助

遇到问题时：

1. 检查GitHub Actions日志（最详细的信息来源）
2. 查看README.md中的常见问题部分
3. 查看SETUP_SECRETS.md中的Secret设置指南
4. 确认本地测试可正常运行

## 下一步

部署完成后，你可以：

1. **优化阈值** - 根据实际利率调整15个基点的阈值
2. **添加通知方式** - 钉钉、企业微信、Slack等
3. **记录历史数据** - 使用GitHub作为数据存储
4. **监控更多产品** - 添加其他银行或理财产品
5. **创建仪表板** - 使用GitHub Pages展示数据

祝部署顺利！
