"""
测试Super Trend机器学习训练模块（简化版）
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime

def create_test_data():
    """创建测试数据用于验证"""
    print("创建测试数据...")
    
    # 生成1000个样本，15个特征
    n_samples = 1000
    n_features = 15
    
    # 生成特征数据
    feature_names = [f'feature_{i}' for i in range(n_features)]
    X = pd.DataFrame(
        np.random.randn(n_samples, n_features),
        columns=feature_names
    )
    
    # 生成目标变量（26.66%正样本，与真实数据一致）
    np.random.seed(42)
    y = np.random.choice([0, 1], size=n_samples, p=[0.7334, 0.2666])
    
    # 创建DataFrame
    df = X.copy()
    df['target'] = y
    
    # 保存测试数据
    test_path = os.path.join("data", "result", "super_trend", "test_training_data.csv")
    os.makedirs(os.path.dirname(test_path), exist_ok=True)
    df.to_csv(test_path, index=False)
    
    print(f"测试数据已保存: {test_path}")
    print(f"数据维度: {df.shape}")
    print(f"正样本比例: {y.mean():.2%}")
    
    return test_path

def test_trainer_basic():
    """测试训练器基本功能"""
    print("\n测试训练器基本功能...")
    
    try:
        from super_trend_ml_trainer import SuperTrendModelTrainer
        
        # 使用测试数据
        test_data_path = create_test_data()
        trainer = SuperTrendModelTrainer(test_data_path)
        
        # 测试数据加载
        X, y = trainer.load_training_data()
        print(f"✓ 数据加载成功: {X.shape}")
        
        # 测试参数配置
        print(f"✓ 模型参数配置: {len(trainer.params)} 个参数")
        
        # 测试特征列
        print(f"✓ 特征列数: {len(trainer.feature_columns)}")
        
        return True
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_dependencies():
    """检查依赖库"""
    print("检查依赖库...")
    
    dependencies = {
        'lightgbm': 'LightGBM机器学习库',
        'pandas': '数据处理',
        'numpy': '数值计算',
        'sklearn': 'scikit-learn',
        'matplotlib': '可视化'
    }
    
    missing = []
    for lib, desc in dependencies.items():
        try:
            __import__(lib)
            print(f"✓ {lib}: {desc}")
        except ImportError:
            print(f"✗ {lib}: {desc} - 未安装")
            missing.append(lib)
    
    if missing:
        print(f"\n缺少依赖库: {missing}")
        print("安装命令: pip install " + " ".join(missing))
        return False
    
    return True

def main():
    """主测试流程"""
    print("=== Super Trend训练模块测试 ===\n")
    
    # 检查依赖
    if not check_dependencies():
        print("请先安装缺少的依赖库")
        return
    
    # 测试基本功能
    if not test_trainer_basic():
        print("\n基本功能测试失败")
        return
    
    # 验证真实数据
    print("\n验证真实数据...")
    real_data_path = os.path.join("data", "result", "super_trend", "super_trend_training_data.csv")
    
    if os.path.exists(real_data_path):
        print(f"✓ 找到真实训练数据: {real_data_path}")
        
        try:
            df = pd.read_csv(real_data_path, nrows=5)
            print(f"✓ 数据可读取，前5行:")
            print(df.head())
            
            # 检查特征
            feature_cols = [col for col in df.columns if col != 'target']
            print(f"✓ 特征数量: {len(feature_cols)}")
            
        except Exception as e:
            print(f"✗ 读取真实数据失败: {e}")
    else:
        print(f"✗ 未找到真实训练数据: {real_data_path}")
        print("请先运行第一阶段扫描器生成数据")
    
    print("\n✅ 测试完成!")
    print("\n下一步:")
    print("1. 确保lightgbm等依赖已安装")
    print("2. 运行真实训练: python super_trend_ml_trainer.py")
    print("3. 模型将保存到: data/result/super_trend/models/trend_gbm_v1.pkl")

if __name__ == "__main__":
    main()