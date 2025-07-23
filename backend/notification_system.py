#!/usr/bin/env python3
"""
通知系统

这个模块实现了多渠道通知功能，包括：
- 邮件通知
- Webhook通知
- 消息推送
- 报告分发
"""

import os
import sys
import json
import logging
import smtplib
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# 尝试导入HTTP请求库
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class NotificationSystem:
    """通知系统"""
    
    def __init__(self, config: Optional[Dict] = None):
        """初始化通知系统"""
        self.config = config or self._get_default_config()
        self.logger = logging.getLogger(__name__)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "email": {
                "enabled": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "from_name": "交易决策支持系统",
                "recipients": []
            },
            "webhook": {
                "enabled": False,
                "url": "",
                "headers": {
                    "Content-Type": "application/json"
                }
            },
            "templates": {
                "signal_alert": {
                    "subject": "🎯 交易信号提醒",
                    "template": "signal_alert.html"
                },
                "daily_report": {
                    "subject": "📊 每日交易报告",
                    "template": "daily_report.html"
                },
                "system_alert": {
                    "subject": "⚠️ 系统提醒",
                    "template": "system_alert.html"
                }
            }
        }
    
    def send_signal_alert(self, signals: List[Dict]) -> Dict[str, Any]:
        """发送信号提醒"""
        try:
            if not signals:
                return {'success': True, 'message': '无信号需要发送'}
            
            self.logger.info(f"发送{len(signals)}个信号的提醒")
            
            # 准备消息内容
            message_data = {
                'type': 'signal_alert',
                'timestamp': datetime.now().isoformat(),
                'signals': signals,
                'summary': {
                    'total_signals': len(signals),
                    'buy_signals': len([s for s in signals if s.get('signal_type') == 'buy']),
                    'sell_signals': len([s for s in signals if s.get('signal_type') == 'sell']),
                    'avg_confidence': sum(s.get('confidence', 0) for s in signals) / len(signals)
                }
            }
            
            results = {}
            
            # 发送邮件通知
            if self.config['email']['enabled']:
                email_result = self._send_email_notification(message_data)
                results['email'] = email_result
            
            # 发送Webhook通知
            if self.config['webhook']['enabled']:
                webhook_result = self._send_webhook_notification(message_data)
                results['webhook'] = webhook_result
            
            return {
                'success': True,
                'message': f'信号提醒发送完成',
                'results': results
            }
            
        except Exception as e:
            self.logger.error(f"发送信号提醒失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_daily_report(self, report_path: str) -> Dict[str, Any]:
        """发送每日报告"""
        try:
            self.logger.info(f"发送每日报告: {report_path}")
            
            if not os.path.exists(report_path):
                return {'success': False, 'error': '报告文件不存在'}
            
            # 准备消息内容
            message_data = {
                'type': 'daily_report',
                'timestamp': datetime.now().isoformat(),
                'report_path': report_path,
                'report_size': os.path.getsize(report_path)
            }
            
            results = {}
            
            # 发送邮件（附带报告文件）
            if self.config['email']['enabled']:
                email_result = self._send_email_with_attachment(message_data, report_path)
                results['email'] = email_result
            
            # 发送Webhook通知
            if self.config['webhook']['enabled']:
                webhook_result = self._send_webhook_notification(message_data)
                results['webhook'] = webhook_result
            
            return {
                'success': True,
                'message': '每日报告发送完成',
                'results': results
            }
            
        except Exception as e:
            self.logger.error(f"发送每日报告失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_system_alert(self, alert_type: str, message: str, details: Optional[Dict] = None) -> Dict[str, Any]:
        """发送系统提醒"""
        try:
            self.logger.info(f"发送系统提醒: {alert_type}")
            
            # 准备消息内容
            message_data = {
                'type': 'system_alert',
                'alert_type': alert_type,
                'message': message,
                'details': details or {},
                'timestamp': datetime.now().isoformat()
            }
            
            results = {}
            
            # 发送邮件通知
            if self.config['email']['enabled']:
                email_result = self._send_email_notification(message_data)
                results['email'] = email_result
            
            # 发送Webhook通知
            if self.config['webhook']['enabled']:
                webhook_result = self._send_webhook_notification(message_data)
                results['webhook'] = webhook_result
            
            return {
                'success': True,
                'message': '系统提醒发送完成',
                'results': results
            }
            
        except Exception as e:
            self.logger.error(f"发送系统提醒失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_email_notification(self, message_data: Dict) -> Dict[str, Any]:
        """发送邮件通知"""
        try:
            email_config = self.config['email']
            
            if not email_config['recipients']:
                return {'success': False, 'error': '无收件人'}
            
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = f"{email_config['from_name']} <{email_config['username']}>"
            msg['To'] = ', '.join(email_config['recipients'])
            
            # 根据消息类型设置主题和内容
            msg_type = message_data['type']
            template_config = self.config['templates'].get(msg_type, {})
            
            msg['Subject'] = template_config.get('subject', '系统通知')
            
            # 生成邮件内容
            html_content = self._generate_email_content(message_data)
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # 发送邮件
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                server.starttls()
                server.login(email_config['username'], email_config['password'])
                server.send_message(msg)
            
            return {
                'success': True,
                'message': f'邮件发送成功，收件人: {len(email_config["recipients"])}人'
            }
            
        except Exception as e:
            self.logger.error(f"发送邮件失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_email_with_attachment(self, message_data: Dict, attachment_path: str) -> Dict[str, Any]:
        """发送带附件的邮件"""
        try:
            email_config = self.config['email']
            
            if not email_config['recipients']:
                return {'success': False, 'error': '无收件人'}
            
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = f"{email_config['from_name']} <{email_config['username']}>"
            msg['To'] = ', '.join(email_config['recipients'])
            msg['Subject'] = self.config['templates']['daily_report']['subject']
            
            # 邮件正文
            html_content = self._generate_email_content(message_data)
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # 添加附件
            with open(attachment_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {os.path.basename(attachment_path)}'
                )
                msg.attach(part)
            
            # 发送邮件
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                server.starttls()
                server.login(email_config['username'], email_config['password'])
                server.send_message(msg)
            
            return {
                'success': True,
                'message': f'带附件邮件发送成功，收件人: {len(email_config["recipients"])}人'
            }
            
        except Exception as e:
            self.logger.error(f"发送带附件邮件失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_webhook_notification(self, message_data: Dict) -> Dict[str, Any]:
        """发送Webhook通知"""
        if not HAS_REQUESTS:
            return {'success': False, 'error': 'requests库未安装'}
        
        try:
            webhook_config = self.config['webhook']
            
            if not webhook_config['url']:
                return {'success': False, 'error': 'Webhook URL未配置'}
            
            # 发送POST请求
            response = requests.post(
                webhook_config['url'],
                json=message_data,
                headers=webhook_config['headers'],
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': 'Webhook通知发送成功'
                }
            else:
                return {
                    'success': False,
                    'error': f'Webhook返回错误: {response.status_code}'
                }
                
        except Exception as e:
            self.logger.error(f"发送Webhook通知失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _generate_email_content(self, message_data: Dict) -> str:
        """生成邮件内容"""
        msg_type = message_data['type']
        
        if msg_type == 'signal_alert':
            return self._generate_signal_alert_html(message_data)
        elif msg_type == 'daily_report':
            return self._generate_daily_report_html(message_data)
        elif msg_type == 'system_alert':
            return self._generate_system_alert_html(message_data)
        else:
            return self._generate_default_html(message_data)
    
    def _generate_signal_alert_html(self, message_data: Dict) -> str:
        """生成信号提醒HTML"""
        signals = message_data.get('signals', [])
        summary = message_data.get('summary', {})
        
        html = f'''
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #667eea; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .signal {{ background: #f8f9fa; margin: 10px 0; padding: 15px; border-left: 4px solid #667eea; }}
                .buy {{ border-left-color: #28a745; }}
                .sell {{ border-left-color: #dc3545; }}
                .summary {{ background: #e9ecef; padding: 15px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎯 交易信号提醒</h1>
                <p>发送时间: {message_data['timestamp']}</p>
            </div>
            <div class="content">
                <div class="summary">
                    <h3>📊 信号摘要</h3>
                    <p>总信号数: {summary.get('total_signals', 0)}</p>
                    <p>买入信号: {summary.get('buy_signals', 0)}</p>
                    <p>卖出信号: {summary.get('sell_signals', 0)}</p>
                    <p>平均置信度: {summary.get('avg_confidence', 0):.2%}</p>
                </div>
                <h3>🎯 信号详情</h3>
        '''
        
        for signal in signals:
            signal_class = signal.get('signal_type', 'buy')
            html += f'''
                <div class="signal {signal_class}">
                    <strong>{signal.get('stock_code', 'N/A')}</strong> - 
                    {signal.get('signal_type', 'N/A').upper()} 
                    (置信度: {signal.get('confidence', 0):.2%})
                    <br>
                    触发价格: ¥{signal.get('trigger_price', 0):.2f}
                    <br>
                    时间: {signal.get('signal_date', 'N/A')}
                </div>
            '''
        
        html += '''
            </div>
        </body>
        </html>
        '''
        
        return html
    
    def _generate_daily_report_html(self, message_data: Dict) -> str:
        """生成每日报告HTML"""
        return f'''
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #667eea; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 每日交易报告</h1>
                <p>生成时间: {message_data['timestamp']}</p>
            </div>
            <div class="content">
                <p>您的每日交易报告已生成完成，请查看附件。</p>
                <p>报告文件: {os.path.basename(message_data.get('report_path', ''))}</p>
                <p>文件大小: {message_data.get('report_size', 0) / 1024:.1f} KB</p>
            </div>
        </body>
        </html>
        '''
    
    def _generate_system_alert_html(self, message_data: Dict) -> str:
        """生成系统提醒HTML"""
        return f'''
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #ffc107; color: #333; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .alert {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>⚠️ 系统提醒</h1>
                <p>时间: {message_data['timestamp']}</p>
            </div>
            <div class="content">
                <div class="alert">
                    <h3>提醒类型: {message_data.get('alert_type', 'N/A')}</h3>
                    <p>{message_data.get('message', 'N/A')}</p>
                </div>
            </div>
        </body>
        </html>
        '''
    
    def _generate_default_html(self, message_data: Dict) -> str:
        """生成默认HTML"""
        return f'''
        <html>
        <body>
            <h1>系统通知</h1>
            <p>时间: {message_data.get('timestamp', 'N/A')}</p>
            <pre>{json.dumps(message_data, indent=2, ensure_ascii=False)}</pre>
        </body>
        </html>
        '''


def main():
    """测试函数"""
    logging.basicConfig(level=logging.INFO)
    
    # 创建通知系统
    notification = NotificationSystem()
    
    print("🔔 通知系统测试")
    print("=" * 50)
    
    # 测试信号提醒
    test_signals = [
        {
            'stock_code': 'sz300290',
            'signal_type': 'buy',
            'confidence': 0.85,
            'trigger_price': 17.5,
            'signal_date': datetime.now().isoformat()
        }
    ]
    
    result = notification.send_signal_alert(test_signals)
    print(f"信号提醒测试: {'✅' if result['success'] else '❌'} {result['message']}")
    
    # 测试系统提醒
    result = notification.send_system_alert('test', '这是一个测试提醒')
    print(f"系统提醒测试: {'✅' if result['success'] else '❌'} {result['message']}")


if __name__ == "__main__":
    main()