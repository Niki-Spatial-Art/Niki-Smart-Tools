#!/usr/bin/env python3
"""主监控脚本 V2.0 - 理财雷达性能升级版"""

import os
import json
import pytz
from datetime import datetime, time
from scraper import RateMonitor
from emailer import EmailNotifier
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def is_sleep_time():
    """
    检查当前是否为休眠时间（北京时间 23:30 - 08:30）
    返回 True 表示在休眠期间
    """
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(beijing_tz)
    current_time = now.time()
    
    # 休眠时段：23:30 - 次日 08:30
    sleep_start = time(23, 30)
    sleep_end = time(8, 30)
    
    if sleep_start <= current_time or current_time <= sleep_end:
        return True
    return False


def generate_html_email(result):
    """
    生成 HTML 格式的邮件正文
    """
    cmb_data = result.get('cmb_detail', {})
    webank_data = result.get('webank_detail', {})
    rate_diff = result.get('rate_diff', 0)
    
    # 提取数据
    cmb_rate = cmb_data.get('rate', 0) if cmb_data else 0
    cmb_term = cmb_data.get('term', '7天') if cmb_data else '7天'
    cmb_remaining_days = cmb_data.get('remaining_days', '--') if cmb_data else '--'
    cmb_converted_rate = cmb_data.get('converted_rate', cmb_rate) if cmb_data else cmb_rate
    cmb_auto_trade = '✅ 支持' if cmb_data.get('support_real_time', False) else '❌ 不支持' if cmb_data else '--'
    
    webank_rate = webank_data.get('rate', 0) if webank_data else 0
    webank_product = webank_data.get('product_name', '微众银行7天理财') if webank_data else '微众银行7天理财'
    
    # 判断是否需要行动建议
    action_advice = ""
    if rate_diff > 15:
        action_advice = """
        <div style="margin-top: 20px; padding: 15px; background-color: #fff3cd; border-left: 4px solid #ffc107; border-radius: 4px;">
            <p style="margin: 0; font-size: 16px; font-weight: bold; color: #856404;">
                💡 建议操作：请立即打开招行 App -&gt; 理财 -&gt; 大额存单转让区
            </p>
        </div>
        """
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            h2 {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #f8f9fa; font-weight: bold; color: #555; }}
            .highlight {{ background-color: #e8f5e9; font-weight: bold; color: #2e7d32; }}
            .rate-diff {{ font-size: 24px; font-weight: bold; color: #d32f2f; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #999; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🏦 理财雷达 V2.0 - 实时利差监控</h2>
            
            <table>
                <tr>
                    <th colspan="2" style="background-color: #e3f2fd; color: #1565c0;">📊 招商银行大额存单转让</th>
                </tr>
                <tr>
                    <td>预期年化收益率</td>
                    <td class="highlight">{cmb_rate:.3%}</td>
                </tr>
                <tr>
                    <td>产品期限</td>
                    <td>{cmb_term}</td>
                </tr>
                <tr>
                    <td>剩余天数</td>
                    <td>{cmb_remaining_days} 天</td>
                </tr>
                <tr>
                    <td>折算后年化</td>
                    <td class="highlight">{cmb_converted_rate:.3%}</td>
                </tr>
                <tr>
                    <td>是否支持实时到账（自动成交）</td>
                    <td>{cmb_auto_trade}</td>
                </tr>
            </table>
            
            <table>
                <tr>
                    <th colspan="2" style="background-color: #e8f5e9; color: #2e7d32;">📊 微众银行7天理财</th>
                </tr>
                <tr>
                    <td>产品名称</td>
                    <td>{webank_product}</td>
                </tr>
                <tr>
                    <td>7日年化收益率</td>
                    <td class="highlight">{webank_rate:.3%}</td>
                </tr>
            </table>
            
            <table>
                <tr>
                    <th colspan="2" style="background-color: #fff3e0; color: #e65100;">📈 利差分析</th>
                </tr>
                <tr>
                    <td>实时利差</td>
                    <td class="rate-diff">{rate_diff:.1f} bps</td>
                </tr>
                <tr>
                    <td>阈值判断</td>
                    <td>{'✅ 超过15bps阈值，存在套利机会！' if rate_diff > 15 else '⏳ 未超过15bps阈值，继续观望'}</td>
                </tr>
            </table>
            
            {action_advice}
            
            <div class="footer">
                <p>监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (北京时间)</p>
                <p>理财雷达 V2.0 | 自动监控，智能提醒</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_content


def main():
    """主函数"""
    
    # 检查是否在休眠时间
    if is_sleep_time():
        beijing_tz = pytz.timezone('Asia/Shanghai')
        now = datetime.now(beijing_tz)
        logger.info(f"🌙 当前北京时间 {now.strftime('%H:%M')}，处于休眠时段 (23:30-08:30)，跳过本次执行")
        return True
    
    # 从环境变量读取配置
    SENDER_EMAIL = os.getenv('SENDER_EMAIL', '')
    SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', '')  # GitHub Secrets
    RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL', '')
    RATE_DIFF_THRESHOLD = float(os.getenv('RATE_DIFF_THRESHOLD', '0.15'))
    
    beijing_tz = pytz.timezone('Asia/Shanghai')
    logger.info("=== 🏦 理财雷达 V2.0 启动 ===")
    logger.info(f"监控开始时间: {datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    
    # 验证必要的环境变量
    if not SENDER_EMAIL or not SENDER_PASSWORD or not RECIPIENT_EMAIL:
        logger.error("❌ 缺少必要的环境变量 (SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL)")
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
    
    if result.get('cmb_rate') is not None:
        logger.info(f"招商银行7天大额存单转让率: {result['cmb_rate']}%")
    if result.get('webank_rate') is not None:
        logger.info(f"微众银行7天理财率: {result['webank_rate']}%")
    if result.get('rate_diff') is not None:
        logger.info(f"利差: {result['rate_diff']} 个基点")
    
    # 如果获取数据失败
    if not result.get('cmb_rate') or not result.get('webank_rate'):
        logger.error("❌ 无法获取完整的利率数据，跳过本次邮件通知")
        return False
    
    # 生成邮件标题和正文
    rate_diff = result.get('rate_diff', 0)
    subject = f"【利差预警】当前利差：{rate_diff:.1f} bps"
    html_message = generate_html_email(result)
    
    # 发送邮件（无论是否有套利机会都发送报告）
    logger.info("📧 准备发送监控邮件...")
    
    send_success = notifier.send_html_alert(
        recipient_email=RECIPIENT_EMAIL,
        subject=subject,
        html_content=html_message
    )
    
    if send_success:
        if result.get('should_alert'):
            logger.info("✅ 套利机会提醒邮件发送成功！")
        else:
            logger.info("✅ 常规监控报告发送成功！")
        return True
    else:
        logger.error("❌ 邮件发送失败！")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
