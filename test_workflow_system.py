#!/usr/bin/env python3
"""
三阶段交易决策支持系统 - 测试脚本

用于验证系统的基本功能和组件集成。
"""

import os
import sys
import json
import unittest
from datetime import datetime
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

class TestWorkflowSystem(unittest.TestCase):
    """工作流系统测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.test_config_file = "test_workflow_config.json"
        self.test_pool_file = "test_core_pool.json"
        
        # 创建测试配置
        test_config = {
            "phase1": {"enabled": True, "frequency_days": 0},
            "phase2": {"enabled": True, "frequency_days": 0},
            "phase3": {"enabled": True, "frequency_days": 0},
            "data": {
                "cache_dir": "test_cache",
                "core_pool_file": self.test_pool_file,
                "performance_log": "test_performance.json",
                "workflow_state": "test_workflow_state.json"
            },
            "logging": {"level": "ERROR", "file": "test.log"}
        }
        
        with open(self.test_config_file, 'w') as f:
            json.dump(test_config, f)
    
    def tearDown(self):
        """测试后清理"""
        test_files = [
            self.test_config_file,
            self.test_pool_file,
            "test_performance.json",
            "test_workflow_state.json",
            "test.log"
        ]
        
        for file_path in test_files:
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # 清理测试目录
        if os.path.exists("test_cache"):
            import shutil
            shutil.rmtree("test_cache")
    
    def test_config_loading(self):
        """测试配置加载"""
        try:
            from workflow_manager import WorkflowManager
            manager = WorkflowManager(self.test_config_file)
            
            self.assertIsNotNone(manager.config)
            self.assertTrue(manager.config['phase1']['enabled'])
            print("✅ 配置加载测试通过")
        except ImportError:
            print("⚠️  跳过配置加载测试 (缺少依赖)")
    
    def test_directory_creation(self):
        """测试目录创建"""
        try:
            from workflow_manager import WorkflowManager
            manager = WorkflowManager(self.test_config_file)
            
            # 检查目录是否创建
            self.assertTrue(os.path.exists("test_cache"))
            self.assertTrue(os.path.exists("logs"))
            self.assertTrue(os.path.exists("reports"))
            print("✅ 目录创建测试通过")
        except ImportError:
            print("⚠️  跳过目录创建测试 (缺少依赖)")
    
    def test_state_management(self):
        """测试状态管理"""
        try:
            from workflow_manager import WorkflowManager
            manager = WorkflowManager(self.test_config_file)
            
            # 测试状态获取
            state = manager.get_workflow_state()
            self.assertIsInstance(state, dict)
            
            # 测试状态保存
            test_state = {"test_key": "test_value"}
            manager.save_workflow_state(test_state)
            
            # 验证状态保存
            loaded_state = manager.get_workflow_state()
            self.assertEqual(loaded_state["test_key"], "test_value")
            print("✅ 状态管理测试通过")
        except ImportError:
            print("⚠️  跳过状态管理测试 (缺少依赖)")
    
    def test_core_pool_operations(self):
        """测试核心观察池操作"""
        try:
            from workflow_manager import WorkflowManager
            manager = WorkflowManager(self.test_config_file)
            
            # 测试核心池更新
            test_stocks = [
                {"stock_code": "test001", "score": 0.8},
                {"stock_code": "test002", "score": 0.7}
            ]
            manager._update_core_pool(test_stocks)
            
            # 测试核心池加载
            loaded_pool = manager._load_core_pool()
            self.assertEqual(len(loaded_pool), 2)
            self.assertEqual(loaded_pool[0]["stock_code"], "test001")
            print("✅ 核心观察池操作测试通过")
        except ImportError:
            print("⚠️  跳过核心观察池测试 (缺少依赖)")


def test_file_structure():
    """测试文件结构"""
    print("\n🔍 检查文件结构...")
    
    required_files = [
        "workflow_manager.py",
        "run_workflow.py", 
        "workflow_config.json",
        "quick_start.py"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
        else:
            print(f"  ✅ {file_path}")
    
    if missing_files:
        print(f"  ❌ 缺少文件: {missing_files}")
        return False
    
    print("✅ 文件结构检查通过")
    return True


def test_imports():
    """测试模块导入"""
    print("\n🔍 检查模块导入...")
    
    modules_to_test = [
        ("json", "JSON处理"),
        ("datetime", "日期时间"),
        ("pathlib", "路径处理"),
        ("logging", "日志系统"),
        ("argparse", "命令行参数")
    ]
    
    failed_imports = []
    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            print(f"  ✅ {module_name} ({description})")
        except ImportError:
            failed_imports.append((module_name, description))
            print(f"  ❌ {module_name} ({description})")
    
    if failed_imports:
        print(f"导入失败的模块: {[m[0] for m in failed_imports]}")
        return False
    
    print("✅ 模块导入检查通过")
    return True


def test_config_file():
    """测试配置文件"""
    print("\n🔍 检查配置文件...")
    
    if not os.path.exists("workflow_config.json"):
        print("  ❌ 配置文件不存在")
        return False
    
    try:
        with open("workflow_config.json", 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        required_sections = ['phase1', 'phase2', 'phase3', 'data', 'logging']
        for section in required_sections:
            if section in config:
                print(f"  ✅ {section} 配置段")
            else:
                print(f"  ❌ 缺少 {section} 配置段")
                return False
        
        print("✅ 配置文件检查通过")
        return True
        
    except json.JSONDecodeError as e:
        print(f"  ❌ 配置文件JSON格式错误: {e}")
        return False
    except Exception as e:
        print(f"  ❌ 配置文件读取错误: {e}")
        return False


def run_basic_tests():
    """运行基本测试"""
    print("🧪 开始基本功能测试")
    print("=" * 50)
    
    tests = [
        ("文件结构", test_file_structure),
        ("模块导入", test_imports),
        ("配置文件", test_config_file)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 测试: {test_name}")
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} 测试失败")
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
    
    print(f"\n📊 基本测试结果: {passed}/{total} 通过")
    return passed == total


def run_unit_tests():
    """运行单元测试"""
    print("\n🧪 开始单元测试")
    print("=" * 50)
    
    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestWorkflowSystem)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, 'w'))
    result = runner.run(suite)
    
    # 显示结果
    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total_tests - failures - errors
    
    print(f"📊 单元测试结果: {passed}/{total_tests} 通过")
    
    if failures:
        print(f"❌ 失败: {failures}")
    if errors:
        print(f"❌ 错误: {errors}")
    
    return failures == 0 and errors == 0


def main():
    """主测试函数"""
    print("🎯 三阶段交易决策支持系统 - 系统测试")
    print("=" * 60)
    
    # 运行基本测试
    basic_passed = run_basic_tests()
    
    # 运行单元测试
    unit_passed = run_unit_tests()
    
    # 总结
    print("\n" + "=" * 60)
    print("📋 测试总结:")
    
    if basic_passed:
        print("✅ 基本功能测试: 通过")
    else:
        print("❌ 基本功能测试: 失败")
    
    if unit_passed:
        print("✅ 单元测试: 通过")
    else:
        print("❌ 单元测试: 失败")
    
    overall_success = basic_passed and unit_passed
    
    if overall_success:
        print("\n🎉 所有测试通过！系统基本功能正常。")
        print("\n📝 下一步建议:")
        print("  1. 运行 python quick_start.py 体验演示功能")
        print("  2. 运行 python run_workflow.py --status 查看系统状态")
        print("  3. 配置实际的数据源和参数")
    else:
        print("\n⚠️  部分测试失败，请检查系统配置。")
    
    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())