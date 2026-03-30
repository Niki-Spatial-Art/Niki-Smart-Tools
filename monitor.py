#!/usr/bin/env python3
"""主监控脚本 - 用于本地测试和GitHub Action调用"""

import os
import json
from datetime import datetime
from scraper import RateMonitor
from emailer import EmailNotifier
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    
    # 从环境变量读取配置
    SENDER_EMAIL = os.getenv('SENDER_EMAIL', '')
    SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', '')  # GitHub Secrets
    RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL', '')
    RATE_DIFF_THRESHOLD = float(os.getenv('RATE_DIFF_THRESHOLD', '0.15'))
    
    logger.info("=== 银行利率监控系统启动 ===")
    logger.info(f"监控开始时间: {datetime.now().isoformat()}")
    
    # 验证必要的环境变量
    if not SENDER_EMAIL or not SENDER_PASSWORD or not RECIPIENT_EMAIL:
        logger.error("缺少必要的环境变量 (SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL)")
        logger.error("请在 GitHub Secrets 中设置以下变量:")
        logger.error("  - SENDER_EMAIL: 发件邮箱地址")
        logger.error("  - SENDER_PASSWORD: 邮箱授权码")
        logger.error("  - RECIPIENT_EMAIL: 收件邮箱地址")
        return False
    
    # 初始化监控和邮件通知
    monitor = RateMonitor(rate_diff_threshold=RATE_DIFF_THRESHOLD)
    notifier = EmailNotifier(
        sender_email=SENDER_EMAIL,
        sender_password=SENDER_PASSWORD,
        smtp_server="smtp.qq.com",
        smtp_port=587
    )
    
    # 执行利率检查
    result = monitor.check_arbitrage()
    
    logger.info(f"招商银行7天大额存单转让率: {result['cmb_rate']}%")
    logger.info(f"微众银行7天理财率: {result['webank_rate']}%")
    logger.info(f"利差: {result['rate_diff']} 个基点")
    logger.info(f"监控信息:\n{result['message']}")
    
    # 如果发现套利机会，发送提醒邮件
    if result['should_alert']:
        logger.info("发现套利机会！准备发送提醒邮件...")
        
        subject = "🎯 银行利率套利机会提醒！"
        send_success = notifier.send_alert(
            recipient_email=RECIPIENT_EMAIL,
            subject=subject,
            message=result['message']
        )
        
        if send_success:
            logger.info("提醒邮件发送成功！")
            return True
        else:
            logger.error("提醒邮件发送失败！")
            return False
    else:
        logger.info("暂未发现套利机会，继续监控...")
        # 可选：发送定期报告（注释掉）
        # notifier.send_status_report(RECIPIENT_EMAIL, result)
        return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
