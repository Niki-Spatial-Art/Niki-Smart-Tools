"""银行利率爬取模块 V2.0 - 理财雷达爬虫升级版"""
import requests
from bs4 import BeautifulSoup
import json
from typing import Dict, Optional, List
import logging
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# User-Agent 轮换池
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
]


class CMBScraper:
    """招商银行爬虫 - 大额存单转让区 V2.0"""
    
    def __init__(self):
        self.session = requests.Session()
        self.max_retries = 3
    
    def _get_headers(self) -> Dict:
        """获取随机 User-Agent 的请求头"""
        return {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://www.cmbchina.com/',
        }
    
    def get_cd_rate(self) -> Optional[Dict]:
        """
        获取招商银行大额存单转让区利率
        V2.0 更新：
        - 过滤不支持"实时到账/自动成交"的单子
        - 增加 User-Agent 轮换
        - 增强异常处理
        
        返回: {
            'rate': float, 
            'term': str, 
            'support_real_time': bool,
            'remaining_days': int,
            'converted_rate': float,
            'auto_trade': bool
        }
        """
        for attempt in range(self.max_retries):
            try:
                # 招商银行大额存单转让API
                url = "https://ccard.cmbchina.com/contentapi/sso/api/queryProduct"
                
                payload = {
                    'productType': 'CD',  # 大额存单
                    'termCode': '7'       # 7天期
                }
                
                headers = self._get_headers()
                
                logger.info(f"尝试获取招商银行数据 (第 {attempt + 1}/{self.max_retries} 次)...")
                
                response = self.session.get(
                    url,
                    params=payload,
                    headers=headers,
                    timeout=15
                )
                response.raise_for_status()
                
                # 检查响应内容类型
                content_type = response.headers.get('Content-Type', '')
                
                # 如果返回的是加密数据或 HTML 而不是 JSON
                if 'text/html' in content_type or not response.text.strip().startswith('{'):
                    logger.warning(f"接口返回非 JSON 数据，可能是加密或需要登录 (Content-Type: {content_type})")
                    if attempt < self.max_retries - 1:
                        logger.info("更换 User-Agent 重试...")
                        continue
                    else:
                        logger.error("❌ 招商银行接口返回加密数据，建议升级为 Playwright 模拟模式")
                        logger.error("提示：可尝试使用 Playwright 模拟浏览器行为来绕过反爬")
                        return None
                
                data = response.json()
                
                # 解析响应数据
                if data.get('code') == '0' and data.get('data'):
                    products = data['data'].get('products', [])
                    
                    # V2.0：过滤支持"实时到账/自动成交"的单子
                    valid_products = []
                    for product in products:
                        # 检查是否支持自动成交/实时到账
                        realtime_flag = product.get('realtimeFlag', False)
                        auto_trade = product.get('autoTrade', False)
                        trade_mode = product.get('tradeMode', '')
                        
                        # 必须支持实时到账或自动成交
                        if realtime_flag or auto_trade or 'auto' in trade_mode.lower():
                            valid_products.append(product)
                    
                    if valid_products:
                        # 选择利率最高的支持实时到账的产品
                        best_product = max(valid_products, key=lambda x: float(x.get('rate', 0)))
                        
                        rate = float(best_product.get('rate', 0))
                        remaining_days = int(best_product.get('remainingDays', 7))
                        
                        # 计算折算后年化（简化计算）
                        converted_rate = rate * (remaining_days / 7) if remaining_days > 0 else rate
                        
                        logger.info(f"✅ 找到支持实时到账的招行产品，利率: {rate:.3%}")
                        
                        return {
                            'rate': rate,
                            'term': '7天',
                            'support_real_time': True,
                            'remaining_days': remaining_days,
                            'converted_rate': converted_rate,
                            'auto_trade': best_product.get('autoTrade', False),
                            'source': 'CMB'
                        }
                    else:
                        logger.warning("⚠️ 未找到支持实时到账/自动成交的招商银行产品")
                        return None
                else:
                    error_msg = data.get('message', '未知错误')
                    logger.warning(f"招商银行数据解析失败: {error_msg}")
                    if attempt < self.max_retries - 1:
                        continue
                    return None
                
            except requests.exceptions.Timeout:
                logger.warning(f"请求超时 (尝试 {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    continue
                return None
            except requests.exceptions.RequestException as e:
                logger.error(f"请求异常: {str(e)} (尝试 {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    continue
                return None
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失败: {str(e)}")
                logger.error("❌ 接口可能返回了加密数据或页面，建议升级为 Playwright 模拟模式")
                return None
            except Exception as e:
                logger.error(f"招商银行爬虫失败: {str(e)}")
                return None
        
        return None


class WEBankScraper:
    """微众银行爬虫 - 7天理财利率 V2.0"""
    
    def __init__(self):
        self.session = requests.Session()
        self.max_retries = 3
    
    def _get_headers(self) -> Dict:
        """获取随机 User-Agent 的请求头"""
        return {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://www.webank.com/',
        }
    
    def get_7day_rate(self) -> Optional[Dict]:
        """
        获取微众银行7天理财产品利率
        V2.0 更新：
        - 增加 User-Agent 轮换
        - 增强异常处理
        
        返回: {
            'rate': float, 
            'term': str, 
            'product_name': str,
            'support_real_time': bool
        }
        """
        for attempt in range(self.max_retries):
            try:
                # 微众银行理财产品API
                url = "https://api.webank.com/wealth/product/list"
                
                params = {
                    'term': '7',
                    'type': 'finance'
                }
                
                headers = self._get_headers()
                
                logger.info(f"尝试获取微众银行数据 (第 {attempt + 1}/{self.max_retries} 次)...")
                
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=15
                )
                response.raise_for_status()
                
                # 检查响应内容类型
                content_type = response.headers.get('Content-Type', '')
                
                # 如果返回的是加密数据或 HTML 而不是 JSON
                if 'text/html' in content_type or not response.text.strip().startswith('{'):
                    logger.warning(f"接口返回非 JSON 数据，可能是加密或需要登录 (Content-Type: {content_type})")
                    if attempt < self.max_retries - 1:
                        logger.info("更换 User-Agent 重试...")
                        continue
                    else:
                        logger.error("❌ 微众银行接口返回加密数据，建议升级为 Playwright 模拟模式")
                        return None
                
                data = response.json()
                
                # 解析响应数据
                if data.get('code') == 0 and data.get('data'):
                    products = data['data'].get('products', [])
                    
                    if products:
                        # 选择7天期利率最高的产品
                        best_product = max(products, key=lambda x: float(x.get('yearRate', 0)))
                        
                        logger.info(f"✅ 找到微众银行产品，利率: {float(best_product.get('yearRate', 0)):.3%}")
                        
                        return {
                            'rate': float(best_product.get('yearRate', 0)),
                            'term': '7天',
                            'product_name': best_product.get('productName', '微众银行7天理财'),
                            'support_real_time': True,  # 微众银行一般支持T+1到账
                            'source': 'WeBank'
                        }
                
                logger.warning("微众银行数据解析失败")
                if attempt < self.max_retries - 1:
                    continue
                return None
                
            except requests.exceptions.Timeout:
                logger.warning(f"请求超时 (尝试 {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    continue
                return None
            except requests.exceptions.RequestException as e:
                logger.error(f"请求异常: {str(e)} (尝试 {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    continue
                return None
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失败: {str(e)}")
                logger.error("❌ 接口可能返回了加密数据或页面，建议升级为 Playwright 模拟模式")
                return None
            except Exception as e:
                logger.error(f"微众银行爬虫失败: {str(e)}")
                return None
        
        return None


class RateMonitor:
    """利率监控主类 V2.0"""
    
    def __init__(self, rate_diff_threshold: float = 0.15):
        """
        初始化监控器
        
        :param rate_diff_threshold: 利差阈值（百分比，例如0.15代表15个基点）
        """
        self.cmb_scraper = CMBScraper()
        self.webank_scraper = WEBankScraper()
        self.rate_diff_threshold = rate_diff_threshold
    
    def check_arbitrage(self) -> Dict:
        """
        检查套利机会
        
        返回: {
            'should_alert': bool,
            'cmb_rate': float,
            'webank_rate': float,
            'rate_diff': float,
            'message': str,
            'cmb_detail': Dict,
            'webank_detail': Dict
        }
        """
        cmb_data = self.cmb_scraper.get_cd_rate()
        webank_data = self.webank_scraper.get_7day_rate()
        
        result = {
            'should_alert': False,
            'cmb_rate': None,
            'webank_rate': None,
            'rate_diff': None,
            'message': '',
            'cmb_detail': None,
            'webank_detail': None,
            'timestamp': None
        }
        
        if not cmb_data or not webank_data:
            result['message'] = '无法获取完整的利率数据'
            return result
        
        result['cmb_rate'] = cmb_data['rate']
        result['webank_rate'] = webank_data['rate']
        result['cmb_detail'] = cmb_data
        result['webank_detail'] = webank_data
        
        # 计算利差（基点）
        rate_diff = (cmb_data['rate'] - webank_data['rate']) * 100
        result['rate_diff'] = rate_diff
        
        # V2.0：只考虑支持实时到账的产品
        if rate_diff > self.rate_diff_threshold:
            result['should_alert'] = True
            logger.info(f"🎯 发现套利机会！利差: {rate_diff:.1f} bps")
        else:
            logger.info(f"⏳ 当前利差 {rate_diff:.1f} bps，未超过{self.rate_diff_threshold * 100:.0f}bps阈值")
        
        return result
