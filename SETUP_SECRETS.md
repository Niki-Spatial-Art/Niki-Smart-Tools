# GitHub Secrets 设置指南

本项目需要在GitHub中设置以下Secrets来正常运行。

## 必需的Secrets

### 1. SENDER_EMAIL
- **说明**: 发件人邮箱地址（用来发送通知的邮箱）
- **示例**: `your-email@qq.com`
- **获取方式**: 使用你的QQ邮箱或其他邮箱

### 2. SENDER_PASSWORD  
- **说明**: 邮箱授权码（不是邮箱登录密码，而是授权码！）
- **示例**: `xxxxxxxxxxxx` (16位字符)
- **获取方式**:
  - QQ邮箱: 登录邮箱 → 设置 → 账户 → POP3/IMAP服务 → 生成授权码
  - 163邮箱: 设置 → POP3/SMTP/IMAP → 生成授权密码
  - 其他邮箱: 查看相应邮箱的"应用专用密码"功能

### 3. RECIPIENT_EMAIL
- **说明**: 收件人邮箱地址（接收提醒的邮箱）
- **示例**: `receive@qq.com` 或 `your-phone@qq.com`
- **获取方式**: 你想要接收通知的任何邮箱地址

## 设置步骤

### 方法1: 网页界面（推荐）

1. 进入GitHub仓库主页
2. 点击 **Settings** （仓库设置）
3. 左侧菜单选择 **Secrets and variables** → **Actions**
4. 点击 **New repository secret** 按钮
5. 按照以下步骤添加3个Secrets：

#### 添加 SENDER_EMAIL
```
Name: SENDER_EMAIL
Secret: 你的邮箱地址
```
点击 **Add secret**

#### 添加 SENDER_PASSWORD
```
Name: SENDER_PASSWORD
Secret: 你的邮箱授权码
```
点击 **Add secret**

#### 添加 RECIPIENT_EMAIL
```
Name: RECIPIENT_EMAIL
Secret: 收件人邮箱地址
```
点击 **Add secret**

### 方法2: GitHub CLI

如果已安装GitHub CLI，可以用命令行添加：

```bash
gh secret set SENDER_EMAIL -b "your-email@qq.com"
gh secret set SENDER_PASSWORD -b "xxxxxxxxxxxx"
gh secret set RECIPIENT_EMAIL -b "receive@qq.com"
```

## 验证设置

1. 进入仓库的 **Actions** 标签
2. 选择 **Bank Rate Monitor** 工作流
3. 点击 **Run workflow** → **Run workflow** 按钮
4. 等待执行完成，检查：
   - 是否有错误日志
   - 是否成功发送邮件

## 常见错误

### ❌ "邮箱认证失败"
- 检查 SENDER_PASSWORD 是否为授权码（不是邮箱密码）
- QQ邮箱授权码必须是16位
- 确认邮箱账户未被锁定

### ❌ "SMTP连接失败"
- 检查邮箱SMTP是否开启
- 确认网络连接正常
- 确认SMTP服务器地址正确

### ❌ "无法识别的Secrets"
- 确保Secrets名称完全匹配（区分大小写）
- 重新检查是否正确保存

## 更新Secrets

如需修改已有的Secrets：

1. 进入 **Settings** → **Secrets and variables** → **Actions**
2. 找到要修改的Secret
3. 点击 **Update secret**
4. 输入新值
5. 点击 **Update secret**

## 安全建议

⚠️ **重要安全事项：**

1. **永远不要在代码中硬编码密码或授权码**
   - 即使仓库是私有的也不要这样做
   - GitHub会自动扫描并禁用泄露的令牌

2. **定期更新授权码**
   - 每3-6个月更换一次授权码
   - 如果怀疑泄露，立即重新生成

3. **限制仓库访问**
   - 将仓库设为私有
   - 只邀请信任的合作者

4. **监控Action执行日志**
   - 提取日志时确保不显示Secrets
   - GitHub会自动掩盖Secrets输出

## 获取QQ邮箱授权码详细步骤

1. 打开 [QQ邮箱](https://mail.qq.com)
2. 点击左上角 **设置** → **账户**
3. 找到 **POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务**
4. 确保IMAP/SMTP已开启，点击 **开启**
5. 系统会弹出授权请求，使用QQ或手机号验证
6. 验证成功后会显示 **授权码（16位字符）**
7. 保管好这个授权码，作为 SENDER_PASSWORD 使用

## 获取163邮箱授权码详细步骤

1. 打开 [163邮箱](https://mail.163.com)
2. 点击 **设置** → **POP3/SMTP/IMAP**
3. 点击 **开启服务**
4. 用手机验证邮箱
5. 会自动生成 **授权密码**
6. 用这个授权密码作为 SENDER_PASSWORD

## 帮助

如果遇到问题：
- 查看GitHub Actions执行日志
- 确认所有Secrets都已正确设置
- 检查邮箱设置中SMTP/IMAP是否开启
- 尝试手动运行一次工作流进行测试
