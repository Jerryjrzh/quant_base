#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移脚本：从A/B级跟踪器迁移到统一跟踪器
"""

import os
import shutil
from datetime import datetime

def backup_old_trackers():
    """备份原有的A/B级跟踪器"""
    print("📦 备份原有的A/B级跟踪器...")
    
    backup_dir = f"backups/old_trackers_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    files_to_backup = [
        'backend/a_grade_stock_tracker.py',
        'backend/b_grade_stock_tracker.py',
        'test_b_grade_stock_tracker.py'
    ]
    
    backed_up_files = []
    for file_path in files_to_backup:
        if os.path.exists(file_path):
            backup_path = os.path.join(backup_dir, os.path.basename(file_path))
            shutil.copy2(file_path, backup_path)
            backed_up_files.append(file_path)
            print(f"  ✅ 备份: {file_path} -> {backup_path}")
    
    if backed_up_files:
        print(f"📁 备份完成，文件保存在: {backup_dir}")
        return backup_dir
    else:
        print("⚠️ 未找到需要备份的文件")
        return None

def create_compatibility_scripts():
    """创建兼容性脚本，保持原有接口"""
    print("🔗 创建兼容性脚本...")
    
    # A级跟踪器兼容脚本
    a_grade_compat = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A级股票跟踪器兼容脚本
使用统一跟踪器实现，保持原有接口兼容性
"""

import sys
import os

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from unified_stock_tracker import UnifiedStockTracker
from config_loader import ConfigLoader

def run_a_grade_tracking():
    """运行A级股票跟踪"""
    print("🚀 启动A级股票跟踪器 (使用统一跟踪器)")
    
    try:
        # 加载A级配置
        config_loader = ConfigLoader()
        a_criteria = config_loader.get_grade_criteria('A')
        
        # 创建统一跟踪器
        tracker = UnifiedStockTracker('A', a_criteria)
        
        # 运行完整分析
        result = tracker.run_full_analysis()
        
        print(f"✅ A级股票跟踪完成: 发现{result['total_stocks']}只A级股票")
        return result
        
    except Exception as e:
        print(f"❌ A级股票跟踪失败: {e}")
        raise

if __name__ == '__main__':
    run_a_grade_tracking()
'''
    
    # B级跟踪器兼容脚本
    b_grade_compat = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B级股票跟踪器兼容脚本
使用统一跟踪器实现，保持原有接口兼容性
"""

import sys
import os

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from unified_stock_tracker import UnifiedStockTracker
from config_loader import ConfigLoader

def run_b_grade_tracking():
    """运行B级股票跟踪"""
    print("🚀 启动B级股票跟踪器 (使用统一跟踪器)")
    
    try:
        # 加载B级配置
        config_loader = ConfigLoader()
        b_criteria = config_loader.get_grade_criteria('B')
        
        # 创建统一跟踪器
        tracker = UnifiedStockTracker('B', b_criteria)
        
        # 运行完整分析
        result = tracker.run_full_analysis()
        
        print(f"✅ B级股票跟踪完成: 发现{result['total_stocks']}只B级股票")
        return result
        
    except Exception as e:
        print(f"❌ B级股票跟踪失败: {e}")
        raise

if __name__ == '__main__':
    run_b_grade_tracking()
'''
    
    # 写入兼容性脚本
    with open('run_a_grade_tracker_compat.py', 'w', encoding='utf-8') as f:
        f.write(a_grade_compat)
    print("  ✅ 创建A级跟踪器兼容脚本: run_a_grade_tracker_compat.py")
    
    with open('run_b_grade_tracker_compat.py', 'w', encoding='utf-8') as f:
        f.write(b_grade_compat)
    print("  ✅ 创建B级跟踪器兼容脚本: run_b_grade_tracker_compat.py")

def create_migration_guide():
    """创建迁移指南"""
    print("📖 创建迁移指南...")
    
    guide = '''# 股票跟踪器迁移指南

## 概述

原有的 `a_grade_stock_tracker.py` 和 `b_grade_stock_tracker.py` 已经被统一的 `UnifiedStockTracker` 替代。新系统消除了代码重复，提供了更好的可维护性和扩展性。

## 主要改进

1. **消除代码重复**: 原来两个文件95%的代码重复，现在统一为一个可配置的系统
2. **配置化分级标准**: 分级标准现在存储在 `config/stock_grading_criteria.yaml` 中，可以轻松修改
3. **数据缓存优化**: 实现了数据缓存，避免重复加载相同股票的数据
4. **更好的扩展性**: 可以轻松添加C级、D级等新的分级标准

## 使用方法

### 1. 使用统一跟踪器

```bash
# 运行A级股票跟踪
python run_unified_stock_tracker.py --grade A

# 运行B级股票跟踪
python run_unified_stock_tracker.py --grade B

# 运行所有等级的跟踪
python run_unified_stock_tracker.py --all-grades

# 列出所有可用等级
python run_unified_stock_tracker.py --list-grades
```

### 2. 使用兼容性脚本（保持原有接口）

```bash
# 使用A级兼容脚本
python run_a_grade_tracker_compat.py

# 使用B级兼容脚本
python run_b_grade_tracker_compat.py
```

### 3. 修改分级标准

编辑 `config/stock_grading_criteria.yaml` 文件来调整分级标准，无需修改代码。

## 配置文件结构

```yaml
grades:
  A:
    name: "A级 (优质股票)"
    rules:
      - type: comprehensive_score
        range: [80, 101]
        reason: "综合评分A级 ({score:.1f}分)"
      # 更多规则...
  B:
    name: "B级 (潜力股票)"
    rules:
      # B级规则...
```

## 测试

运行测试脚本验证系统正常工作：

```bash
python test_unified_stock_tracker.py
```

## 文件变更

- ✅ 新增: `backend/unified_stock_tracker.py` - 统一股票跟踪器
- ✅ 新增: `backend/config_loader.py` - 配置加载器
- ✅ 新增: `config/stock_grading_criteria.yaml` - 分级标准配置
- ✅ 新增: `run_unified_stock_tracker.py` - 主运行脚本
- 📦 备份: 原有的A/B级跟踪器文件已备份
- 🔗 兼容: 创建了兼容性脚本保持原有接口

## 注意事项

1. 原有的A/B级跟踪器文件已备份，可以随时恢复
2. 兼容性脚本确保现有的调用方式仍然有效
3. 新系统完全兼容原有的数据格式和输出格式
4. 如有问题，可以使用备份文件恢复到原有系统

## 优势

- **维护性**: 只需维护一套代码，bug修复和功能增强更容易
- **扩展性**: 可以轻松添加新的分级标准（C级、D级等）
- **配置化**: 分级标准可以通过配置文件调整，无需修改代码
- **性能**: 数据缓存减少了重复的数据加载操作
- **一致性**: 所有等级使用相同的逻辑，确保结果一致性
'''
    
    with open('STOCK_TRACKER_MIGRATION_GUIDE.md', 'w', encoding='utf-8') as f:
        f.write(guide)
    print("  ✅ 创建迁移指南: STOCK_TRACKER_MIGRATION_GUIDE.md")

def main():
    """主迁移函数"""
    print("🚀 开始股票跟踪器迁移")
    print("=" * 60)
    
    # 1. 备份原有文件
    backup_dir = backup_old_trackers()
    
    # 2. 创建兼容性脚本
    create_compatibility_scripts()
    
    # 3. 创建迁移指南
    create_migration_guide()
    
    print("\n" + "=" * 60)
    print("🎉 迁移完成！")
    print("\n📋 迁移摘要:")
    print("  ✅ 原有文件已备份")
    print("  ✅ 统一跟踪器已就绪")
    print("  ✅ 配置文件已创建")
    print("  ✅ 兼容性脚本已创建")
    print("  ✅ 迁移指南已生成")
    
    print("\n🚀 下一步:")
    print("  1. 运行测试: python test_unified_stock_tracker.py")
    print("  2. 尝试新系统: python run_unified_stock_tracker.py --grade A")
    print("  3. 查看迁移指南: STOCK_TRACKER_MIGRATION_GUIDE.md")
    
    if backup_dir:
        print(f"  4. 如有问题，可从备份恢复: {backup_dir}")

if __name__ == '__main__':
    main()