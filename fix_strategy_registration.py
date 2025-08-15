#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复策略注册问题
直接修改策略管理器以支持中文策略名称
"""

import sys
import os
import json

def fix_strategy_manager():
    """修复策略管理器"""
    strategy_manager_file = "backend/strategy_manager.py"
    
    # 读取当前文件
    with open(strategy_manager_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否已经包含修复代码
    if "_register_config_strategies" in content:
        print("策略管理器已包含修复代码")
        return
    
    # 在类的__init__方法末尾添加配置策略注册
    init_method_end = "        #logger.info(f\"策略管理器初始化完成，发现 {len(self.registered_strategies)} 个策略\")"
    
    if init_method_end in content:
        replacement = init_method_end + """
        
        # 注册配置文件中的策略
        self._register_config_strategies()"""
        
        content = content.replace(init_method_end, replacement)
        
        # 添加新方法
        new_method = '''
    def _register_config_strategies(self):
        """注册配置文件中的策略"""
        try:
            config_strategies = self.config_manager.get_strategies()
            
            for config_id, config_data in config_strategies.items():
                if config_id not in self.registered_strategies:
                    # 尝试根据名称找到对应的策略类
                    strategy_name = config_data.get('name', '')
                    
                    # 查找匹配的策略类
                    for registered_id, strategy_class in list(self.registered_strategies.items()):
                        try:
                            temp_instance = strategy_class()
                            if temp_instance.name == strategy_name:
                                # 注册配置ID作为别名
                                self.registered_strategies[config_id] = strategy_class
                                logger.info(f"注册策略别名: {config_id} -> {registered_id}")
                                break
                        except Exception as e:
                            continue
                            
        except Exception as e:
            logger.error(f"注册配置策略失败: {e}")'''
        
        # 在类的末尾添加新方法
        class_end = "# 全局策略管理器实例"
        content = content.replace(class_end, new_method + "\n\n" + class_end)
        
        # 写回文件
        with open(strategy_manager_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ 策略管理器修复完成")
    else:
        print("❌ 未找到预期的代码位置")

def test_fix():
    """测试修复效果"""
    print("=== 测试策略注册修复 ===")
    
    # 检查配置文件
    config_file = "config/unified_strategy_config.json"
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        strategies = config.get('strategies', {})
        enabled_strategies = [sid for sid, sdata in strategies.items() if sdata.get('enabled', False)]
        
        print(f"配置文件中启用的策略: {len(enabled_strategies)}")
        for sid in enabled_strategies:
            print(f"  - {sid}")
    
    print("\n修复建议:")
    print("1. 确保策略类的name属性与配置文件中的name字段匹配")
    print("2. 添加策略别名支持")
    print("3. 改进错误处理和日志输出")

if __name__ == "__main__":
    fix_strategy_manager()
    test_fix()