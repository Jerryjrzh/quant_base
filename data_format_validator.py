#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通达信数据格式验证和修复工具

功能：
1. 验证数据文件路径结构
2. 检测错误的目录分类
3. 自动修复数据文件位置
4. 验证数据文件格式完整性
"""

import os
import shutil
import struct
import pandas as pd
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataFormatValidator:
    """数据格式验证器"""
    
    def __init__(self, base_path: str = None):
        self.base_path = base_path or os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        self.backup_path = os.path.join(self.base_path, "backup_before_fix")
        
    def get_correct_market(self, stock_code: str) -> str:
        """根据股票代码确定正确的市场目录"""
        # 港股代码包含#
        if '#' in stock_code:
            return 'ds'
        
        # 如果已经包含市场前缀，直接返回
        if stock_code.startswith(('sh', 'sz', 'bj')):
            return stock_code[:2]
        
        # A股代码规则（纯数字代码）
        if stock_code.startswith('00') or stock_code.startswith('30'):
            return 'sz'  # 深圳
        elif stock_code.startswith('60') or stock_code.startswith('68'):
            return 'sh'  # 上海
        elif stock_code.startswith('8') or stock_code.startswith('4'):
            return 'bj'  # 北京
        else:
            # 默认处理
            if stock_code.startswith('0'):
                return 'sz'
            elif stock_code.startswith('6'):
                return 'sh'
            else:
                return 'unknown'
    
    def scan_data_structure(self) -> Dict[str, List[str]]:
        """扫描当前数据目录结构"""
        structure = {}
        
        if not os.path.exists(self.base_path):
            logger.error(f"数据目录不存在: {self.base_path}")
            return structure
        
        # 扫描所有子目录
        for item in os.listdir(self.base_path):
            item_path = os.path.join(self.base_path, item)
            if os.path.isdir(item_path):
                # 查找lday目录
                lday_path = os.path.join(item_path, 'lday')
                if os.path.exists(lday_path):
                    day_files = [f for f in os.listdir(lday_path) if f.endswith('.day')]
                    if day_files:
                        structure[item] = day_files
                else:
                    # 直接在目录下查找.day文件
                    day_files = [f for f in os.listdir(item_path) if f.endswith('.day')]
                    if day_files:
                        structure[item] = day_files
        
        return structure
    
    def validate_file_locations(self) -> List[Dict]:
        """验证文件位置是否正确"""
        issues = []
        structure = self.scan_data_structure()
        
        logger.info("开始验证文件位置...")
        
        for current_dir, files in structure.items():
            logger.info(f"检查目录 {current_dir}: {len(files)} 个文件")
            
            for filename in files:
                stock_code = filename.replace('.day', '')
                correct_market = self.get_correct_market(stock_code)
                
                if current_dir != correct_market:
                    issue = {
                        'stock_code': stock_code,
                        'filename': filename,
                        'current_location': current_dir,
                        'correct_location': correct_market,
                        'current_path': self._get_file_path(current_dir, filename),
                        'correct_path': self._get_correct_file_path(stock_code)
                    }
                    issues.append(issue)
                    
        logger.info(f"发现 {len(issues)} 个位置错误的文件")
        return issues
    
    def _get_file_path(self, market_dir: str, filename: str) -> str:
        """获取文件的当前路径"""
        # 先尝试lday子目录
        lday_path = os.path.join(self.base_path, market_dir, 'lday', filename)
        if os.path.exists(lday_path):
            return lday_path
        
        # 再尝试直接在市场目录下
        direct_path = os.path.join(self.base_path, market_dir, filename)
        if os.path.exists(direct_path):
            return direct_path
        
        return ""
    
    def _get_correct_file_path(self, stock_code: str) -> str:
        """获取文件的正确路径"""
        correct_market = self.get_correct_market(stock_code)
        return os.path.join(self.base_path, correct_market, 'lday', f'{stock_code}.day')
    
    def validate_file_format(self, file_path: str, stock_code: str) -> Dict:
        """验证单个文件的格式"""
        result = {
            'file_path': file_path,
            'stock_code': stock_code,
            'valid': False,
            'record_count': 0,
            'date_range': None,
            'errors': []
        }
        
        if not os.path.exists(file_path):
            result['errors'].append("文件不存在")
            return result
        
        try:
            # 检测文件格式
            is_hk_stock = '#' in stock_code
            record_size = 32
            
            with open(file_path, 'rb') as f:
                f.seek(0, 2)  # 移到文件末尾
                file_size = f.tell()
                f.seek(0)  # 回到开头
                
                if file_size % record_size != 0:
                    result['errors'].append(f"文件大小不是{record_size}的倍数")
                    return result
                
                expected_records = file_size // record_size
                valid_records = 0
                dates = []
                
                # 选择解包格式
                if is_hk_stock:
                    unpack_format = '<IfffffIi'
                else:
                    unpack_format = '<IIIIIfI'
                
                unpack_size = struct.calcsize(unpack_format)
                
                # 验证前100条记录
                max_check = min(100, expected_records)
                
                for i in range(max_check):
                    chunk = f.read(record_size)
                    if len(chunk) < record_size:
                        break
                    
                    try:
                        if is_hk_stock:
                            date, open_p, high_p, low_p, close_p, amount, volume, _reserved = struct.unpack(unpack_format, chunk)
                        else:
                            date, open_p, high_p, low_p, close_p, amount, volume = struct.unpack(unpack_format, chunk[:unpack_size])
                        
                        # 验证日期格式
                        year = date // 10000
                        month = (date % 10000) // 100
                        day = date % 100
                        
                        if year < 1990 or year > 2030 or month < 1 or month > 12 or day < 1 or day > 31:
                            continue
                        
                        # 验证价格数据
                        if is_hk_stock:
                            price_divisor = 1.0
                        else:
                            price_divisor = 100.0
                        
                        if open_p / price_divisor <= 0:
                            continue
                        
                        valid_records += 1
                        dates.append(datetime.strptime(str(date), '%Y%m%d'))
                        
                    except (struct.error, ValueError) as e:
                        result['errors'].append(f"记录{i}解析错误: {str(e)}")
                
                result['record_count'] = expected_records
                result['valid_records'] = valid_records
                
                if dates:
                    result['date_range'] = (min(dates), max(dates))
                    result['valid'] = valid_records > 0
                else:
                    result['errors'].append("没有有效的数据记录")
                
        except Exception as e:
            result['errors'].append(f"文件读取错误: {str(e)}")
        
        return result
    
    def create_backup(self) -> bool:
        """创建数据备份"""
        try:
            if os.path.exists(self.backup_path):
                logger.info(f"备份目录已存在: {self.backup_path}")
                return True
            
            os.makedirs(self.backup_path, exist_ok=True)
            logger.info(f"创建备份目录: {self.backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"创建备份目录失败: {e}")
            return False
    
    def fix_file_locations(self, issues: List[Dict], dry_run: bool = True) -> Dict:
        """修复文件位置"""
        result = {
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        if not dry_run and not self.create_backup():
            result['errors'].append("无法创建备份，操作中止")
            return result
        
        for issue in issues:
            try:
                current_path = issue['current_path']
                correct_path = issue['correct_path']
                
                if dry_run:
                    logger.info(f"[DRY RUN] 将移动: {current_path} -> {correct_path}")
                    result['success'] += 1
                else:
                    # 确保目标目录存在
                    os.makedirs(os.path.dirname(correct_path), exist_ok=True)
                    
                    # 移动文件
                    shutil.move(current_path, correct_path)
                    logger.info(f"已移动: {current_path} -> {correct_path}")
                    result['success'] += 1
                    
            except Exception as e:
                error_msg = f"移动文件失败 {issue['filename']}: {str(e)}"
                logger.error(error_msg)
                result['errors'].append(error_msg)
                result['failed'] += 1
        
        return result
    
    def generate_report(self) -> str:
        """生成验证报告"""
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("通达信数据格式验证报告")
        report_lines.append("=" * 60)
        report_lines.append(f"数据目录: {self.base_path}")
        report_lines.append(f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")
        
        # 扫描目录结构
        structure = self.scan_data_structure()
        report_lines.append("目录结构:")
        for dir_name, files in structure.items():
            report_lines.append(f"  {dir_name}/: {len(files)} 个文件")
        report_lines.append("")
        
        # 验证文件位置
        issues = self.validate_file_locations()
        report_lines.append(f"位置错误的文件: {len(issues)} 个")
        
        if issues:
            report_lines.append("\n错误详情:")
            for issue in issues[:10]:  # 只显示前10个
                report_lines.append(f"  {issue['stock_code']}: {issue['current_location']} -> {issue['correct_location']}")
            
            if len(issues) > 10:
                report_lines.append(f"  ... 还有 {len(issues) - 10} 个文件")
        
        # 验证文件格式（抽样检查）
        report_lines.append("\n文件格式验证（抽样）:")
        sample_count = 0
        valid_count = 0
        
        for dir_name, files in structure.items():
            if sample_count >= 10:
                break
            
            for filename in files[:3]:  # 每个目录检查3个文件
                if sample_count >= 10:
                    break
                
                stock_code = filename.replace('.day', '')
                file_path = self._get_file_path(dir_name, filename)
                
                if file_path:
                    format_result = self.validate_file_format(file_path, stock_code)
                    sample_count += 1
                    
                    if format_result['valid']:
                        valid_count += 1
                        status = "✓"
                    else:
                        status = "✗"
                    
                    report_lines.append(f"  {status} {stock_code}: {format_result['record_count']} 条记录")
                    
                    if format_result['errors']:
                        for error in format_result['errors'][:2]:
                            report_lines.append(f"    错误: {error}")
        
        report_lines.append(f"\n格式验证结果: {valid_count}/{sample_count} 个文件格式正确")
        
        return "\n".join(report_lines)

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='通达信数据格式验证和修复工具')
    parser.add_argument('--base-path', help='数据目录路径')
    parser.add_argument('--fix', action='store_true', help='修复文件位置（默认为预览模式）')
    parser.add_argument('--stock-code', help='验证特定股票代码')
    parser.add_argument('--report-only', action='store_true', help='只生成报告')
    
    args = parser.parse_args()
    
    # 创建验证器
    validator = DataFormatValidator(args.base_path)
    
    print("通达信数据格式验证工具")
    print("=" * 50)
    
    if args.stock_code:
        # 验证特定股票
        print(f"验证股票: {args.stock_code}")
        
        correct_market = validator.get_correct_market(args.stock_code)
        print(f"应该在市场: {correct_market}")
        
        # 查找文件
        structure = validator.scan_data_structure()
        found = False
        
        for dir_name, files in structure.items():
            filename = f"{args.stock_code}.day"
            if filename in files:
                file_path = validator._get_file_path(dir_name, filename)
                print(f"找到文件: {file_path}")
                
                # 验证格式
                format_result = validator.validate_file_format(file_path, args.stock_code)
                print(f"格式验证: {'通过' if format_result['valid'] else '失败'}")
                print(f"记录数: {format_result['record_count']}")
                
                if format_result['date_range']:
                    start_date, end_date = format_result['date_range']
                    print(f"日期范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
                
                if format_result['errors']:
                    print("错误:")
                    for error in format_result['errors']:
                        print(f"  - {error}")
                
                found = True
                break
        
        if not found:
            print(f"未找到股票 {args.stock_code} 的数据文件")
    
    elif args.report_only:
        # 只生成报告
        report = validator.generate_report()
        print(report)
        
        # 保存报告到文件
        report_file = f"data_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n报告已保存到: {report_file}")
    
    else:
        # 完整验证和修复流程
        print("1. 扫描数据目录结构...")
        structure = validator.scan_data_structure()
        total_files = sum(len(files) for files in structure.values())
        print(f"   发现 {len(structure)} 个目录，共 {total_files} 个数据文件")
        
        print("\n2. 验证文件位置...")
        issues = validator.validate_file_locations()
        
        if issues:
            print(f"   发现 {len(issues)} 个位置错误的文件")
            
            # 显示前5个问题
            print("\n   问题示例:")
            for issue in issues[:5]:
                print(f"   - {issue['stock_code']}: {issue['current_location']} -> {issue['correct_location']}")
            
            if len(issues) > 5:
                print(f"   ... 还有 {len(issues) - 5} 个文件")
            
            if args.fix:
                print("\n3. 修复文件位置...")
                fix_result = validator.fix_file_locations(issues, dry_run=False)
                print(f"   成功: {fix_result['success']}")
                print(f"   失败: {fix_result['failed']}")
                
                if fix_result['errors']:
                    print("   错误:")
                    for error in fix_result['errors']:
                        print(f"   - {error}")
            else:
                print("\n3. 预览模式（使用 --fix 参数执行实际修复）")
                fix_result = validator.fix_file_locations(issues, dry_run=True)
                print(f"   将修复: {fix_result['success']} 个文件")
        else:
            print("   所有文件位置正确")
        
        # 生成完整报告
        print("\n4. 生成验证报告...")
        report = validator.generate_report()
        report_file = f"data_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"   报告已保存到: {report_file}")

if __name__ == "__main__":
    main()