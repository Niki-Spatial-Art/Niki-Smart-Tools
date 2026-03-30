#!/usr/bin/env python3
"""
本地测试脚本 - 在部署到GitHub Action前进行测试

使用方法:
    python test_local.py
    
环境变量设置:
    export SENDER_EMAIL="your-qq@qq.com"
    export SENDER_PASSWORD="xxxxxxxxxxxx"  # 16位授权码
    export RECIPIENT_EMAIL="receive@qq.com"
"""

import os
import sys
from scraper import RateMonitor
from emailer import EmailNotifier


def test_rate_monitoring():
    """测试利率监控功能"""
    print("\n" + "="*50)
    print("测试1: 利率监控功能")
    print("="*50)
    
    monitor = RateMonitor(rate_diff_threshold=0.15)
    result = monitor.check_arbitrage()
    
    print(f"✓ 监控执行完成")
    print(f"  招商银行7天大额存单转让率: {result['cmb_rate']}")
    print(f"  微众银行7天理财率: {result['webank_rate']}")
    print(f"  利差: {result['rate_diff']} 个基点")
    print(f"  是否触发提醒: {'是' if result['should_alert'] else '否'}")
    print(f"\n监控信息:\n{result['message']}")
    
    return result


def test_email_sending():
    """测试邮件发送功能"""
    print("\n" + "="*50)
    print("测试2: 邮件发送功能")
    print("="*50)
    
    # 从环境变量读取配置
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')
    recipient_email = os.getenv('RECIPIENT_EMAIL')
    
    # 验证环境变量
    if not sender_email or not sender_password or not recipient_email:
        print("✗ 错误: 缺少必要的环境变量")
        print("\n请设置以下环境变量:")
        print("  SENDER_EMAIL - 发件邮箱")
        print("  SENDER_PASSWORD - 邮箱授权码")
        print("  RECIPIENT_EMAIL - 收件邮箱")
        print("\n示例 (Windows PowerShell):")
        print("  $env:SENDER_EMAIL='your-email@qq.com'")
        print("  $env:SENDER_PASSWORD='xxxxxxxxxxxx'")
        print("  $env:RECIPIENT_EMAIL='receive@qq.com'")
        return False
    
    print(f"✓ 密钥信息已配置")
    print(f"  发件邮箱: {sender_email}")
    print(f"  收件邮箱: {recipient_email}")
    
    # 创建邮件通知对象
    notifier = EmailNotifier(
        sender_email=sender_email,
        sender_password=sender_password,
        smtp_server="smtp.qq.com",
        smtp_port=587
    )
    
    # 发送测试邮件
    print("\n正在发送测试邮件...")
    test_message = """测试邮件发送

这是来自银行利率监控系统的测试邮件。

【测试内容】
- 系统: 银行利率监控
- 测试时间: 本地测试运行
- 状态: ✓ 邮件发送功能正常

【说明】
如果你收到这封邮件，说明:
✓ SMTP配置正确
✓ 邮箱授权码有效
✓ 网络连接正常
✓ GitHub Action可以正常发送通知

请勿回复此邮件。
"""
    
    success = notifier.send_alert(
        recipient_email=recipient_email,
        subject="✓ 银行利率监控 - 测试邮件",
        message=test_message
    )
    
    if success:
        print(f"✓ 测试邮件已发送到 {recipient_email}")
        print("  请检查邮箱收件箱（或垃圾邮件夹）")
        return True
    else:
        print(f"✗ 邮件发送失败")
        print("  请检查以下内容:")
        print("  1. 邮箱授权码是否正确（不是邮箱密码）")
        print("  2. 邮箱SMTP服务是否开启")
        print("  3. 网络连接是否正常")
        return False


def main():
    """主测试函数"""
    print("\n" + "="*50)
    print("银行利率监控系统 - 本地测试")
    print("="*50)
    
    # 阶段1: 测试利率监控
    rate_result = test_rate_monitoring()
    
    # 阶段2: 测试邮件发送
    email_success = test_email_sending()
    
    # 总结
    print("\n" + "="*50)
    print("测试总结")
    print("="*50)
    
    if email_success:
        print("\n✓ 所有测试通过！")
        print("\n下一步:")
        print("  1. 确认邮件已正确接收")
        print("  2. 将代码上传到GitHub仓库")
        print("  3. 设置GitHub Secrets:")
        print("     - SENDER_EMAIL")
        print("     - SENDER_PASSWORD")
        print("     - RECIPIENT_EMAIL")
        print("  4. 启用GitHub Action")
        print("  5. 系统将每30分钟自动检查一次利率")
        return True
    else:
        print("\n✗ 邮件发送失败，请修复问题后重试")
        print("\n排查步骤:")
        print("  1. 确认SENDER_PASSWORD是邮箱授权码（不是密码）")
        print("  2. 进入邮箱设置确认SMTP服务已开启")
        print("  3. 查看防火墙/代理设置")
        print("  4. 试试用另一个邮箱账户测试")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
