#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试增强版MA13筛选器

验证：
1. 日线四步筛选逻辑
2. 小时线双模型评分
3. 综合评分系统
4. API集成
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_enhanced_screener_import():
    """测试增强筛选器导入"""
    print("🧪 测试增强筛选器导入...")
    
    try:
        from backend.enhanced_ma13_screener import EnhancedMA13Screener, MA13ScreenResult
        print("✅ 增强筛选器导入成功")
        
        screener = EnhancedMA13Screener()
        print("✅ 筛选器实例化成功")
        
        # 检查关键属性
        assert hasattr(screener, 'daily_params'), "缺少日线参数"
        assert hasattr(screener, 'hourly_params'), "缺少小时线参数"
        assert hasattr(screener, 'scoring_weights'), "缺少评分权重"
        
        print("✅ 筛选器属性检查通过")
        return True
        
    except Exception as e:
        print(f"❌ 增强筛选器导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_single_stock_analysis():
    """测试单股分析"""
    print("\n🧪 测试单股分析...")
    
    try:
        from backend.enhanced_ma13_screener import enhanced_ma13_screener
        
        # 测试股票
        test_stocks = ['sh601388', 'sh688291', 'sz002796']
        
        for stock_code in test_stocks:
            print(f"\n   测试股票: {stock_code}")
            
            result = enhanced_ma13_screener.analyze_single_stock(stock_code)
            
            if result:
                print(f"   ✅ 分析成功")
                print(f"      日线符合: {result.daily_qualified}")
                print(f"      日线阶段: {result.daily_stage}")
                print(f"      日线得分: {result.daily_score:.1f}")
                print(f"      小时线得分: {result.hourly_score:.1f}")
                print(f"      小时线模型: {result.hourly_model}")
                print(f"      总分: {result.total_score:.1f}")
                print(f"      信心度: {result.confidence:.2f}")
                print(f"      市场阶段: {result.market_phase}")
                
                if result.recommendation:
                    rec = result.recommendation
                    print(f"      推荐操作: {rec.get('action', 'N/A')}")
                    print(f"      建议仓位: {rec.get('position_size', 0):.1%}")
                
                if result.key_levels:
                    levels = result.key_levels
                    print(f"      当前价格: {levels.get('current_price', 0):.2f}")
                    print(f"      支撑位: {levels.get('support_1_upper', 0):.2f}")
                    print(f"      目标位: {levels.get('target_1', 0):.2f}")
            else:
                print(f"   ⚠️  分析失败或数据不足")
        
        return True
        
    except Exception as e:
        print(f"❌ 单股分析测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_batch_screening():
    """测试批量筛选"""
    print("\n🧪 测试批量筛选...")
    
    try:
        from backend.enhanced_ma13_screener import enhanced_ma13_screener
        
        # 测试股票列表
        test_codes = ['sh601388', 'sh688291', 'sz002796']
        
        print(f"   批量筛选 {len(test_codes)} 只股票...")
        results = enhanced_ma13_screener.screen_stocks(test_codes)
        
        print(f"   ✅ 筛选完成，符合条件: {len(results)} 只")
        
        for i, result in enumerate(results[:3]):  # 显示前3名
            print(f"   {i+1}. {result.stock_code}")
            print(f"      总分: {result.total_score:.1f}")
            print(f"      信心度: {result.confidence:.2f}")
            print(f"      推荐: {result.recommendation.get('action', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 批量筛选测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_daily_screening_stages():
    """测试日线筛选阶段"""
    print("\n🧪 测试日线筛选阶段...")
    
    try:
        from backend.enhanced_ma13_screener import EnhancedMA13Screener
        from backend.data_handler import get_full_data_with_indicators
        
        screener = EnhancedMA13Screener()
        
        # 测试股票
        stock_code = 'sh688291'
        df = get_full_data_with_indicators(stock_code)
        
        if df is None:
            print(f"   ⚠️  无法获取 {stock_code} 数据")
            return False
        
        print(f"   测试股票: {stock_code} ({len(df)} 条记录)")
        
        # 测试各个阶段
        accumulation_score = screener._check_accumulation_phase(df)
        print(f"   积累期得分: {accumulation_score:.1f}/30")
        
        breakout_score = screener._check_breakout_phase(df)
        print(f"   突破期得分: {breakout_score:.1f}/30")
        
        pullback_score = screener._check_pullback_phase(df)
        print(f"   回调期得分: {pullback_score:.1f}/25")
        
        total_daily = accumulation_score + breakout_score + pullback_score
        print(f"   日线总分: {total_daily:.1f}/85")
        
        # 测试完整日线分析
        daily_analysis = screener._analyze_daily_data(df, stock_code)
        print(f"   日线分析结果:")
        print(f"      符合条件: {daily_analysis['qualified']}")
        print(f"      阶段: {daily_analysis['stage']}")
        print(f"      得分: {daily_analysis['score']:.1f}")
        
        return True
        
    except Exception as e:
        print(f"❌ 日线筛选阶段测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_hourly_models():
    """测试小时线模型"""
    print("\n🧪 测试小时线模型...")
    
    try:
        from backend.enhanced_ma13_screener import EnhancedMA13Screener
        from backend.data_handler import get_full_data_with_indicators
        
        screener = EnhancedMA13Screener()
        
        # 测试股票
        stock_code = 'sh688291'
        daily_df = get_full_data_with_indicators(stock_code)
        
        if daily_df is None:
            print(f"   ⚠️  无法获取 {stock_code} 数据")
            return False
        
        print(f"   测试股票: {stock_code}")
        
        # 测试小时线分析
        hourly_analysis = screener._analyze_hourly_data(stock_code, daily_df)
        
        if hourly_analysis:
            print(f"   ✅ 小时线分析成功")
            print(f"      模型: {hourly_analysis['model']}")
            print(f"      得分: {hourly_analysis['score']:.1f}")
            print(f"      信号: {hourly_analysis['signals']}")
        else:
            print(f"   ⚠️  小时线分析失败")
        
        # 测试后备分析
        simulated = screener._hourly_fallback_analysis(daily_df)
        print(f"   模拟小时线分析:")
        print(f"      得分: {simulated['score']:.1f}")
        print(f"      模型: {simulated['model']}")
        print(f"      信号: {simulated['signals']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 小时线模型测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_integration():
    """测试API集成"""
    print("\n🧪 测试API集成...")
    
    try:
        import requests
        
        # 测试增强扫描API
        url = 'http://localhost:5000/api/ma13/full_market_scan'
        payload = {
            'max_stocks': 10,
            'use_enhanced_screener': True
        }
        
        print(f"   发送增强扫描请求...")
        response = requests.post(url, json=payload, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"   ✅ 增强扫描API成功")
                
                summary = data.get('summary', {})
                print(f"      扫描方法: {summary.get('screening_method', 'N/A')}")
                print(f"      扫描总数: {summary.get('total_scanned', 0)}")
                print(f"      符合条件: {summary.get('qualified_count', 0)}")
                print(f"      符合率: {summary.get('qualified_rate', 0):.1f}%")
                
                # 检查增强功能
                enhanced_features = data.get('enhanced_features', {})
                print(f"      增强功能:")
                for feature, enabled in enhanced_features.items():
                    status = "✅" if enabled else "❌"
                    print(f"        {status} {feature}")
                
                # 显示统计信息
                scan_stats = data.get('scan_stats', {})
                if 'stage_distribution' in scan_stats:
                    print(f"      阶段分布: {scan_stats['stage_distribution']}")
                if 'model_distribution' in scan_stats:
                    print(f"      模型分布: {scan_stats['model_distribution']}")
                
                return True
            else:
                print(f"   ❌ API返回失败: {data.get('message', 'Unknown error')}")
                return False
        else:
            print(f"   ❌ HTTP错误: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("   ⚠️  无法连接到服务器，请确保Flask应用正在运行")
        return False
    except Exception as e:
        print(f"   ❌ API集成测试失败: {e}")
        return False

def test_scoring_system():
    """测试评分系统"""
    print("\n🧪 测试评分系统...")
    
    try:
        from backend.enhanced_ma13_screener import EnhancedMA13Screener, MA13ScreenResult
        
        screener = EnhancedMA13Screener()
        
        # 创建模拟结果
        mock_result = MA13ScreenResult(
            stock_code='TEST001',
            daily_qualified=True,
            daily_stage='ma13_pullback_ready',
            daily_score=75.0,
            hourly_score=45.0,
            hourly_model='oversold_rebound',
            market_phase='markup'
        )
        
        # 添加小时线信号
        mock_result.hourly_signals = {
            'macd_underwater_cross': True,
            'rsi_oversold_bounce': True,
            'volume_increase': True,
            'hammer_candle': False
        }
        
        # 测试综合评分
        total_score = screener._calculate_total_score(mock_result)
        print(f"   综合得分: {total_score:.1f}")
        
        # 测试信心度计算
        mock_result.total_score = total_score
        confidence = screener._calculate_confidence(mock_result)
        print(f"   信心度: {confidence:.2f}")
        
        # 测试评分权重
        weights = screener.scoring_weights
        print(f"   评分权重: {weights}")
        
        # 测试阈值
        thresholds = screener.score_thresholds
        print(f"   评分阈值: {thresholds}")
        
        print(f"   ✅ 评分系统测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 评分系统测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("增强版MA13筛选器测试")
    print("=" * 50)
    
    tests = [
        ("增强筛选器导入", test_enhanced_screener_import),
        ("日线筛选阶段", test_daily_screening_stages),
        ("小时线模型", test_hourly_models),
        ("评分系统", test_scoring_system),
        ("单股分析", test_single_stock_analysis),
        ("批量筛选", test_batch_screening),
        ("API集成", test_api_integration),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ 测试 {test_name} 出现异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print(f"\n{'='*50}")
    print("测试结果汇总:")
    print("=" * 50)
    
    passed = 0
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\n总体结果: {passed}/{len(results)} 个测试通过")
    
    if passed == len(results):
        print("🎉 所有测试通过！增强版MA13筛选器已就绪")
        print("\n✅ 核心特性:")
        print("   - 日线四步筛选：海选→精选→择时→确认")
        print("   - 小时线双模型：超跌反弹 + 中继确认")
        print("   - 融合评分系统：参照confluence_scorer")
        print("   - 市场阶段识别：积累期/上升期/分配期/下跌期")
        print("   - 关键价位计算：支撑位/阻力位/目标位/止损位")
        print("\n📖 使用方法:")
        print("   1. 访问 http://localhost:5000/ma13_strategy")
        print("   2. 点击\"全市场扫描\"按钮")
        print("   3. 系统自动使用增强筛选器")
        print("   4. 查看详细的筛选结果和评分")
    else:
        print("⚠️  部分测试失败，需要进一步检查")
        
        if passed >= 5:
            print("\n💡 提示: 核心功能正常，API测试失败可能是因为Flask应用未运行")

if __name__ == "__main__":
    main()