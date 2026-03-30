"""银行利率爬取模块"""
import requests
from bs4 import BeautifulSoup
import json
from typing import Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CMBScraper:
    """招商银行爬虫 - 大额存单转让区"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def get_cd_rate(self) -> Optional[Dict]:
        """
        获取招商银行大额存单转让区利率
        返回: {'rate': float, 'term': str, 'support_real_time': bool}
        """
        try:
            # 招商银行大额存单转让API
            url = "https://ccard.cmbchina.com/contentapi/sso/api/queryProduct"
            
            payload = {
                'productType': 'CD',  # 大额存单
                'termCode': '7'       # 7天期
            }
            
            response = requests.get(
                url,
                params=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 解析响应数据
            if data.get('code') == '0' and data.get('data'):
                products = data['data'].get('products', [])
                
                if products:
                    product = products[0]
                    
                    # 提取7天期产品的信息
                    return {
                        'rate': float(product.get('rate', 0)),
                        'term': '7天',
                        'support_real_time': product.get('realtimeFlag', False),
                        'source': 'CMB'
                    }
            
            logger.warning("招商银行数据解析失败")
            return None
            
        except Exception as e:
            logger.error(f"招商银行爬虫失败: {str(e)}")
            return None


class WEBankScraper:
    """微众银行爬虫 - 7天理财利率"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def get_7day_rate(self) -> Optional[Dict]:
        """
        获取微众银行7天理财产品利率
        返回: {'rate': float, 'term': str, 'product_name': str}
        """
        try:
            # 微众银行理财产品API
            url = "https://api.webank.com/wealth/product/list"
            
            params = {
                'term': '7',
                'type': 'finance'
            }
            
            response = requests.get(
                url,
                params=params,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 解析响应数据
            if data.get('code') == 0 and data.get('data'):
                products = data['data'].get('products', [])
                
                if products:
                    product = products[0]
                    
                    return {
                        'rate': float(product.get('yearRate', 0)),
                        'term': '7天',
                        'product_name': product.get('productName', '微众银行7天理财'),
                        'support_real_time': True,  # 微众银行一般支持T+1到账
                        'source': 'WeBank'
                    }
            
            logger.warning("微众银行数据解析失败")
            return None
            
        except Exception as e:
            logger.error(f"微众银行爬虫失败: {str(e)}")
            return None


class RateMonitor:
    """利率监控主类"""
    
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
            'message': str
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
            'timestamp': None
        }
        
        if not cmb_data or not webank_data:
            result['message'] = '无法获取完整的利率数据'
            return result
        
        result['cmb_rate'] = cmb_data['rate']
        result['webank_rate'] = webank_data['rate']
        
        # 计算利差（基点）
        rate_diff = (cmb_data['rate'] - webank_data['rate']) * 100
        result['rate_diff'] = rate_diff
        
        # 判断是否需要提醒
        if (rate_diff > self.rate_diff_threshold and 
            cmb_data.get('support_real_time', False)):
            result['should_alert'] = True
            result['message'] = (
                f"发现套利机会！\n"
                f"招商银行7天大额存单转让率: {cmb_data['rate']:.3%}\n"
                f"微众银行7天理财率: {webank_data['rate']:.3%}\n"
                f"利差: {rate_diff:.1f} 个基点\n"
                f"招商银行支持实时到账: {cmb_data.get('support_real_time', False)}"
            )
        else:
            if rate_diff <= self.rate_diff_threshold:
                result['message'] = (
                    f"当前利差 {rate_diff:.1f} 个基点，未超过15个基点阈值。\n"
                    f"招商银行7天大额存单转让率: {cmb_data['rate']:.3%}\n"
                    f"微众银行7天理财率: {webank_data['rate']:.3%}"
                )
            else:
                result['message'] = "招商银行不支持实时到账"
        
        return result
