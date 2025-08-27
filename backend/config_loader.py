#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置加载器
用于加载股票分级标准配置文件
"""

import yaml
import os
from typing import Dict, Any

class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径，默认为 config/stock_grading_criteria.yaml
        """
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            config_path = os.path.join(base_dir, 'config', 'stock_grading_criteria.yaml')
        
        self.config_path = config_path
        self._config = None
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self._config is None:
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f)
                print(f"✅ 配置文件加载成功: {self.config_path}")
            except FileNotFoundError:
                print(f"⚠️ 配置文件不存在: {self.config_path}")
                self._config = self._get_default_config()
            except yaml.YAMLError as e:
                print(f"⚠️ 配置文件格式错误: {e}")
                self._config = self._get_default_config()
            except Exception as e:
                print(f"⚠️ 加载配置文件失败: {e}")
                self._config = self._get_default_config()
        
        return self._config
    
    def get_grade_criteria(self, grade: str) -> Dict[str, Any]:
        """获取指定等级的分级标准"""
        config = self.load_config()
        grades = config.get('grades', {})
        
        if grade not in grades:
            raise ValueError(f"未找到等级 '{grade}' 的配置")
        
        return grades[grade]
    
    def get_global_settings(self) -> Dict[str, Any]:
        """获取全局设置"""
        config = self.load_config()
        return config.get('global_settings', {})
    
    def list_available_grades(self) -> list:
        """列出所有可用的等级"""
        config = self.load_config()
        return list(config.get('grades', {}).keys())
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'grades': {
                'A': {
                    'name': 'A级 (优质股票)',
                    'rules': [
                        {
                            'type': 'comprehensive_score',
                            'range': [80, 101],
                            'reason': '综合评分A级 ({score:.1f}分)'
                        },
                        {
                            'type': 'confidence_and_risk',
                            'confidence_min': 0.85,
                            'risk_levels': ['低'],
                            'reason': '高置信度A级 (置信度{confidence:.1%}, {risk_level}风险)'
                        }
                    ]
                },
                'B': {
                    'name': 'B级 (潜力股票)',
                    'rules': [
                        {
                            'type': 'comprehensive_score',
                            'range': [60, 80],
                            'reason': '综合评分B级 ({score:.1f}分)'
                        },
                        {
                            'type': 'confidence_and_risk',
                            'confidence_range': [0.60, 0.85],
                            'risk_levels': ['中', '低'],
                            'reason': '中等置信度B级 (置信度{confidence:.1%}, {risk_level}风险)'
                        }
                    ]
                }
            },
            'global_settings': {
                'enable_data_cache': True,
                'export_excel': True
            }
        }
    
    def validate_config(self) -> bool:
        """验证配置文件的有效性"""
        try:
            config = self.load_config()
            
            # 检查必要的字段
            if 'grades' not in config:
                print("⚠️ 配置文件缺少 'grades' 字段")
                return False
            
            grades = config['grades']
            if not isinstance(grades, dict):
                print("⚠️ 'grades' 字段必须是字典类型")
                return False
            
            # 检查每个等级的配置
            for grade, criteria in grades.items():
                if not isinstance(criteria, dict):
                    print(f"⚠️ 等级 '{grade}' 的配置必须是字典类型")
                    return False
                
                if 'rules' not in criteria:
                    print(f"⚠️ 等级 '{grade}' 缺少 'rules' 字段")
                    return False
                
                rules = criteria['rules']
                if not isinstance(rules, list):
                    print(f"⚠️ 等级 '{grade}' 的 'rules' 字段必须是列表类型")
                    return False
                
                # 检查每个规则
                for i, rule in enumerate(rules):
                    if not isinstance(rule, dict):
                        print(f"⚠️ 等级 '{grade}' 的第 {i+1} 个规则必须是字典类型")
                        return False
                    
                    if 'type' not in rule:
                        print(f"⚠️ 等级 '{grade}' 的第 {i+1} 个规则缺少 'type' 字段")
                        return False
            
            print("✅ 配置文件验证通过")
            return True
            
        except Exception as e:
            print(f"⚠️ 配置文件验证失败: {e}")
            return False
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """保存配置到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            print(f"✅ 配置文件保存成功: {self.config_path}")
            self._config = None  # 清除缓存，强制重新加载
            return True
            
        except Exception as e:
            print(f"⚠️ 保存配置文件失败: {e}")
            return False
    
    def update_grade_criteria(self, grade: str, criteria: Dict[str, Any]) -> bool:
        """更新指定等级的分级标准"""
        try:
            config = self.load_config()
            
            if 'grades' not in config:
                config['grades'] = {}
            
            config['grades'][grade] = criteria
            
            return self.save_config(config)
            
        except Exception as e:
            print(f"⚠️ 更新等级 '{grade}' 的配置失败: {e}")
            return False
    
    def add_new_grade(self, grade: str, name: str, rules: list, risk_warning: list = None) -> bool:
        """添加新的等级配置"""
        criteria = {
            'name': name,
            'rules': rules
        }
        
        if risk_warning:
            criteria['risk_warning'] = risk_warning
        
        return self.update_grade_criteria(grade, criteria)