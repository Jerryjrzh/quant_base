"""
多周期分析可视化模块
提供多周期数据和信号的可视化展示
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
from pathlib import Path

class MultiTimeframeVisualizer:
    """多周期分析可视化器"""
    
    def __init__(self):
        """初始化可视化器"""
        # 设置中文字体 - 使用英文标签避免字体问题
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 创建图表保存目录
        self.charts_dir = Path("charts/multi_timeframe")
        self.charts_dir.mkdir(parents=True, exist_ok=True)
        
        # 颜色配置
        self.colors = {
            'bullish': '#00C851',    # 绿色 - 看涨
            'bearish': '#FF4444',    # 红色 - 看跌
            'neutral': '#FFBB33',    # 黄色 - 中性
            'background': '#F8F9FA', # 背景色
            'grid': '#E0E0E0',       # 网格色
            'text': '#212529'        # 文字色
        }
        
        # 时间周期配置
        self.timeframe_config = {
            '5min': {'label': '5min', 'color': '#FF6B6B', 'weight': 0.005},
            '15min': {'label': '15min', 'color': '#4ECDC4', 'weight': 0.015},
            '30min': {'label': '30min', 'color': '#45B7D1', 'weight': 0.03},
            '1hour': {'label': '1hour', 'color': '#96CEB4', 'weight': 0.10},
            '4hour': {'label': '4hour', 'color': '#FFEAA7', 'weight': 0.20},
            '1day': {'label': '1day', 'color': '#DDA0DD', 'weight': 0.25},
            '1week': {'label': '1week', 'color': '#FF8C00', 'weight': 0.40}
        }
    
    def create_multi_timeframe_dashboard(self, stock_code: str, analysis_result: dict, 
                                       save_path: str = None) -> str:
        """
        创建多周期分析仪表板
        
        Args:
            stock_code: 股票代码
            analysis_result: 多周期分析结果
            save_path: 保存路径
            
        Returns:
            str: 图表文件路径
        """
        try:
            # 创建图表布局 (2x3)
            fig = plt.figure(figsize=(20, 12))
            fig.suptitle(f'{stock_code} Multi-Timeframe Analysis Dashboard', fontsize=16, fontweight='bold')
            
            # 1. 多周期信号强度雷达图
            ax1 = plt.subplot(2, 3, 1, projection='polar')
            self._plot_signal_radar(ax1, analysis_result)
            
            # 2. 时间周期权重分布
            ax2 = plt.subplot(2, 3, 2)
            self._plot_timeframe_weights(ax2, analysis_result)
            
            # 3. 策略信号对比
            ax3 = plt.subplot(2, 3, 3)
            self._plot_strategy_comparison(ax3, analysis_result)
            
            # 4. 置信度分析
            ax4 = plt.subplot(2, 3, 4)
            self._plot_confidence_analysis(ax4, analysis_result)
            
            # 5. 风险评估
            ax5 = plt.subplot(2, 3, 5)
            self._plot_risk_assessment(ax5, analysis_result)
            
            # 6. 综合评分
            ax6 = plt.subplot(2, 3, 6)
            self._plot_composite_score(ax6, analysis_result)
            
            # 调整布局
            plt.tight_layout()
            
            # 保存图表
            if save_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = self.charts_dir / f"{stock_code}_dashboard_{timestamp}.png"
            
            plt.savefig(save_path, dpi=300, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            plt.close()
            
            return str(save_path)
            
        except Exception as e:
            print(f"创建多周期仪表板失败: {e}")
            return None
    
    def _plot_signal_radar(self, ax, analysis_result):
        """绘制信号强度雷达图"""
        try:
            # 获取各时间周期的信号强度
            timeframe_signals = analysis_result.get('timeframe_signals', {})
            
            # 准备数据
            timeframes = list(self.timeframe_config.keys())
            values = []
            labels = []
            
            for tf in timeframes:
                if tf in timeframe_signals:
                    signal_data = timeframe_signals[tf]
                    # 将信号强度转换为数值 (-1到1的范围转换为0到1)
                    strength = signal_data.get('signal_strength', 0)
                    if isinstance(strength, str):
                        strength_map = {'strong_buy': 1, 'buy': 0.5, 'neutral': 0, 
                                      'sell': -0.5, 'strong_sell': -1}
                        strength = strength_map.get(strength, 0)
                    
                    # 转换为0-1范围
                    normalized_strength = (strength + 1) / 2
                    values.append(normalized_strength)
                else:
                    values.append(0.5)  # 中性值
                
                labels.append(self.timeframe_config[tf]['label'])
            
            # 闭合雷达图
            values += values[:1]
            
            # 角度计算
            angles = np.linspace(0, 2 * np.pi, len(timeframes), endpoint=False).tolist()
            angles += angles[:1]
            
            # 绘制雷达图
            ax.plot(angles, values, 'o-', linewidth=2, color='#4ECDC4')
            ax.fill(angles, values, alpha=0.25, color='#4ECDC4')
            
            # 设置标签
            ax.set_xticks(angles[:-1])
            ax.set_xticklabels(labels)
            ax.set_ylim(0, 1)
            ax.set_title('Multi-Timeframe Signal Strength', pad=20, fontweight='bold')
            
            # 添加网格线
            ax.grid(True, alpha=0.3)
            
        except Exception as e:
            ax.text(0.5, 0.5, f'雷达图生成失败\n{str(e)}', 
                   transform=ax.transAxes, ha='center', va='center')
    
    def _plot_timeframe_weights(self, ax, analysis_result):
        """绘制时间周期权重分布"""
        try:
            # 获取权重配置
            weights = [config['weight'] for config in self.timeframe_config.values()]
            labels = [config['label'] for config in self.timeframe_config.values()]
            colors = [config['color'] for config in self.timeframe_config.values()]
            
            # 绘制饼图
            wedges, texts, autotexts = ax.pie(weights, labels=labels, colors=colors,
                                            autopct='%1.1f%%', startangle=90)
            
            # 美化文字
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
            
            ax.set_title('Timeframe Weight Distribution', fontweight='bold')
            
        except Exception as e:
            ax.text(0.5, 0.5, f'权重图生成失败\n{str(e)}', 
                   transform=ax.transAxes, ha='center', va='center')
    
    def _plot_strategy_comparison(self, ax, analysis_result):
        """绘制策略信号对比"""
        try:
            # 获取策略信号
            strategy_signals = analysis_result.get('strategy_signals', {})
            
            strategies = []
            scores = []
            colors = []
            
            for strategy, data in strategy_signals.items():
                strategies.append(strategy.replace('_', ' ').title())
                score = data.get('final_score', 0)
                scores.append(score)
                
                # 根据分数选择颜色
                if score > 0.6:
                    colors.append(self.colors['bullish'])
                elif score < -0.6:
                    colors.append(self.colors['bearish'])
                else:
                    colors.append(self.colors['neutral'])
            
            # 绘制水平条形图
            bars = ax.barh(strategies, scores, color=colors, alpha=0.7)
            
            # 添加数值标签
            for i, (bar, score) in enumerate(zip(bars, scores)):
                width = bar.get_width()
                ax.text(width + 0.01 if width >= 0 else width - 0.01, 
                       bar.get_y() + bar.get_height()/2, 
                       f'{score:.3f}', ha='left' if width >= 0 else 'right', 
                       va='center', fontweight='bold')
            
            ax.set_xlim(-1, 1)
            ax.axvline(x=0, color='black', linestyle='-', alpha=0.3)
            ax.set_xlabel('Signal Score')
            ax.set_title('Strategy Signal Comparison', fontweight='bold')
            ax.grid(True, alpha=0.3, axis='x')
            
        except Exception as e:
            ax.text(0.5, 0.5, f'策略对比图生成失败\n{str(e)}', 
                   transform=ax.transAxes, ha='center', va='center')
    
    def _plot_confidence_analysis(self, ax, analysis_result):
        """绘制置信度分析"""
        try:
            # 获取置信度数据
            composite_signal = analysis_result.get('composite_signal', {})
            confidence = composite_signal.get('confidence_level', 0)
            
            # 创建置信度仪表盘
            theta = np.linspace(0, np.pi, 100)
            
            # 背景半圆
            ax.fill_between(theta, 0, 1, alpha=0.1, color='gray')
            
            # 置信度区域
            confidence_theta = theta[theta <= confidence * np.pi]
            if len(confidence_theta) > 0:
                color = self.colors['bullish'] if confidence > 0.7 else \
                       self.colors['neutral'] if confidence > 0.4 else \
                       self.colors['bearish']
                ax.fill_between(confidence_theta, 0, 1, alpha=0.6, color=color)
            
            # 指针
            pointer_angle = confidence * np.pi
            ax.plot([pointer_angle, pointer_angle], [0, 0.8], 
                   color='black', linewidth=3)
            ax.plot(pointer_angle, 0.8, 'o', color='black', markersize=8)
            
            # 标签
            ax.text(np.pi/2, 0.5, f'{confidence:.1%}', 
                   ha='center', va='center', fontsize=20, fontweight='bold')
            
            ax.set_xlim(0, np.pi)
            ax.set_ylim(0, 1)
            ax.set_title('Signal Confidence', fontweight='bold')
            ax.axis('off')
            
        except Exception as e:
            ax.text(0.5, 0.5, f'置信度图生成失败\n{str(e)}', 
                   transform=ax.transAxes, ha='center', va='center')
    
    def _plot_risk_assessment(self, ax, analysis_result):
        """绘制风险评估"""
        try:
            # 获取风险数据
            risk_assessment = analysis_result.get('risk_assessment', {})
            risk_level = risk_assessment.get('risk_level', 'medium')
            risk_score = risk_assessment.get('risk_score', 0.5)
            
            # 风险等级映射
            risk_levels = ['low', 'medium', 'high']
            risk_colors = [self.colors['bullish'], self.colors['neutral'], self.colors['bearish']]
            risk_labels = ['Low Risk', 'Medium Risk', 'High Risk']
            
            # 创建风险条形图
            y_pos = np.arange(len(risk_levels))
            values = [0.3, 0.5, 0.2]  # 示例分布
            
            # 当前风险等级高亮
            colors = []
            for i, level in enumerate(risk_levels):
                if level == risk_level:
                    colors.append(risk_colors[i])
                else:
                    colors.append('lightgray')
            
            bars = ax.barh(y_pos, values, color=colors, alpha=0.7)
            
            # 添加风险分数
            ax.text(0.5, len(risk_levels), f'Risk Score: {risk_score:.2f}', 
                   ha='center', va='center', fontweight='bold', 
                   bbox=dict(boxstyle="round,pad=0.3", facecolor='lightblue'))
            
            ax.set_yticks(y_pos)
            ax.set_yticklabels(risk_labels)
            ax.set_xlabel('Risk Distribution')
            ax.set_title('Risk Assessment', fontweight='bold')
            
        except Exception as e:
            ax.text(0.5, 0.5, f'风险评估图生成失败\n{str(e)}', 
                   transform=ax.transAxes, ha='center', va='center')
    
    def _plot_composite_score(self, ax, analysis_result):
        """绘制综合评分"""
        try:
            # 获取综合信号数据
            composite_signal = analysis_result.get('composite_signal', {})
            final_score = composite_signal.get('final_score', 0)
            signal_strength = composite_signal.get('signal_strength', 'neutral')
            
            # 创建评分表盘
            score_normalized = (final_score + 1) / 2  # 转换为0-1范围
            
            # 背景圆环
            circle = plt.Circle((0.5, 0.5), 0.4, fill=False, linewidth=10, 
                              color='lightgray', alpha=0.3)
            ax.add_patch(circle)
            
            # 评分圆环
            if final_score > 0.3:
                color = self.colors['bullish']
            elif final_score < -0.3:
                color = self.colors['bearish']
            else:
                color = self.colors['neutral']
            
            # 绘制评分弧线
            theta1 = 0
            theta2 = score_normalized * 360
            wedge = plt.matplotlib.patches.Wedge((0.5, 0.5), 0.4, theta1, theta2, 
                                               width=0.1, facecolor=color, alpha=0.8)
            ax.add_patch(wedge)
            
            # 中心文字
            ax.text(0.5, 0.6, f'{final_score:.3f}', ha='center', va='center', 
                   fontsize=16, fontweight='bold')
            ax.text(0.5, 0.4, signal_strength.replace('_', ' ').title(), 
                   ha='center', va='center', fontsize=12)
            
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_title('Composite Score', fontweight='bold')
            ax.axis('off')
            
        except Exception as e:
            ax.text(0.5, 0.5, f'综合评分图生成失败\n{str(e)}', 
                   transform=ax.transAxes, ha='center', va='center')
    
    def create_timeframe_comparison_chart(self, stock_code: str, timeframe_data: dict, 
                                        save_path: str = None) -> str:
        """
        创建多周期数据对比图表
        
        Args:
            stock_code: 股票代码
            timeframe_data: 多周期数据
            save_path: 保存路径
            
        Returns:
            str: 图表文件路径
        """
        try:
            # 创建子图布局
            fig, axes = plt.subplots(3, 2, figsize=(16, 12))
            fig.suptitle(f'{stock_code} Multi-Timeframe Data Comparison', fontsize=16, fontweight='bold')
            
            # 扁平化axes数组
            axes = axes.flatten()
            
            # 为每个时间周期创建价格图表
            for i, (timeframe, config) in enumerate(self.timeframe_config.items()):
                if i >= len(axes):
                    break
                    
                ax = axes[i]
                
                if timeframe in timeframe_data and timeframe_data[timeframe] is not None:
                    data = timeframe_data[timeframe]
                    
                    # 绘制K线图（简化版）
                    if not data.empty and 'close' in data.columns:
                        # 使用收盘价绘制线图
                        ax.plot(data.index, data['close'], 
                               color=config['color'], linewidth=2, 
                               label=f"{config['label']} 收盘价")
                        
                        # 添加移动平均线
                        if len(data) >= 20:
                            ma20 = data['close'].rolling(window=20).mean()
                            ax.plot(data.index, ma20, 
                                   color=config['color'], alpha=0.5, 
                                   linestyle='--', label='MA20')
                        
                        ax.set_title(f"{config['label']} ({len(data)}条数据)")
                        ax.legend()
                        ax.grid(True, alpha=0.3)
                        
                        # 格式化x轴
                        if isinstance(data.index, pd.DatetimeIndex):
                            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
                            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
                    else:
                        ax.text(0.5, 0.5, '无数据', transform=ax.transAxes, 
                               ha='center', va='center')
                        ax.set_title(f"{config['label']} (无数据)")
                else:
                    ax.text(0.5, 0.5, '数据不可用', transform=ax.transAxes, 
                           ha='center', va='center')
                    ax.set_title(f"{config['label']} (不可用)")
            
            # 调整布局
            plt.tight_layout()
            
            # 保存图表
            if save_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = self.charts_dir / f"{stock_code}_timeframes_{timestamp}.png"
            
            plt.savefig(save_path, dpi=300, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            plt.close()
            
            return str(save_path)
            
        except Exception as e:
            print(f"创建多周期对比图表失败: {e}")
            return None
    
    def create_signal_timeline_chart(self, stock_code: str, signal_history: list, 
                                   save_path: str = None) -> str:
        """
        创建信号时间线图表
        
        Args:
            stock_code: 股票代码
            signal_history: 信号历史记录
            save_path: 保存路径
            
        Returns:
            str: 图表文件路径
        """
        try:
            if not signal_history:
                print("无信号历史数据")
                return None
            
            # 创建图表
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
            fig.suptitle(f'{stock_code} 信号时间线分析', fontsize=16, fontweight='bold')
            
            # 准备数据
            timestamps = []
            signal_strengths = []
            confidence_levels = []
            
            for record in signal_history:
                timestamps.append(pd.to_datetime(record['timestamp']))
                
                # 转换信号强度为数值
                strength = record.get('signal_strength', 'neutral')
                strength_map = {
                    'strong_buy': 1, 'buy': 0.5, 'neutral': 0, 
                    'sell': -0.5, 'strong_sell': -1
                }
                signal_strengths.append(strength_map.get(strength, 0))
                confidence_levels.append(record.get('confidence_level', 0))
            
            # 绘制信号强度时间线
            ax1.plot(timestamps, signal_strengths, 'o-', linewidth=2, markersize=6, 
                    color='#4ECDC4', label='信号强度')
            ax1.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
            ax1.fill_between(timestamps, signal_strengths, 0, alpha=0.3, color='#4ECDC4')
            
            ax1.set_ylabel('信号强度')
            ax1.set_title('信号强度变化')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            ax1.set_ylim(-1.2, 1.2)
            
            # 添加信号强度标签
            for i, (ts, strength) in enumerate(zip(timestamps, signal_strengths)):
                if abs(strength) > 0.3:  # 只显示较强的信号
                    strength_text = {1: 'Strong Buy', 0.5: 'Buy', -0.5: 'Sell', -1: 'Strong Sell'}
                    ax1.annotate(strength_text.get(strength, ''), 
                               (ts, strength), textcoords="offset points", 
                               xytext=(0,10), ha='center', fontsize=8)
            
            # 绘制置信度时间线
            ax2.plot(timestamps, confidence_levels, 's-', linewidth=2, markersize=6, 
                    color='#FF6B6B', label='置信度')
            ax2.fill_between(timestamps, confidence_levels, 0, alpha=0.3, color='#FF6B6B')
            
            ax2.set_ylabel('置信度')
            ax2.set_xlabel('时间')
            ax2.set_title('信号置信度变化')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            ax2.set_ylim(0, 1.1)
            
            # 格式化x轴
            for ax in [ax1, ax2]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
            
            # 调整布局
            plt.tight_layout()
            
            # 保存图表
            if save_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = self.charts_dir / f"{stock_code}_timeline_{timestamp}.png"
            
            plt.savefig(save_path, dpi=300, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            plt.close()
            
            return str(save_path)
            
        except Exception as e:
            print(f"创建信号时间线图表失败: {e}")
            return None
    
    def create_performance_summary_chart(self, performance_data: dict, 
                                       save_path: str = None) -> str:
        """
        创建性能摘要图表
        
        Args:
            performance_data: 性能数据
            save_path: 保存路径
            
        Returns:
            str: 图表文件路径
        """
        try:
            # 创建图表布局
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 10))
            fig.suptitle('多周期系统性能摘要', fontsize=16, fontweight='bold')
            
            # 1. 信号准确率分析
            if 'accuracy_by_timeframe' in performance_data:
                accuracy_data = performance_data['accuracy_by_timeframe']
                timeframes = list(accuracy_data.keys())
                accuracies = list(accuracy_data.values())
                
                bars = ax1.bar(timeframes, accuracies, 
                              color=[self.timeframe_config[tf]['color'] for tf in timeframes],
                              alpha=0.7)
                
                # 添加数值标签
                for bar, acc in zip(bars, accuracies):
                    height = bar.get_height()
                    ax1.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                            f'{acc:.1%}', ha='center', va='bottom', fontweight='bold')
                
                ax1.set_ylabel('准确率')
                ax1.set_title('各周期信号准确率')
                ax1.set_ylim(0, 1)
                ax1.grid(True, alpha=0.3, axis='y')
            
            # 2. 信号分布饼图
            if 'signal_distribution' in performance_data:
                signal_dist = performance_data['signal_distribution']
                labels = list(signal_dist.keys())
                sizes = list(signal_dist.values())
                colors = [self.colors['bullish'] if 'buy' in label.lower() else
                         self.colors['bearish'] if 'sell' in label.lower() else
                         self.colors['neutral'] for label in labels]
                
                ax2.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', 
                       startangle=90)
                ax2.set_title('信号类型分布')
            
            # 3. 置信度分布直方图
            if 'confidence_distribution' in performance_data:
                confidence_data = performance_data['confidence_distribution']
                ax3.hist(confidence_data, bins=20, alpha=0.7, color='#4ECDC4', 
                        edgecolor='black')
                ax3.set_xlabel('置信度')
                ax3.set_ylabel('频次')
                ax3.set_title('置信度分布')
                ax3.grid(True, alpha=0.3)
            
            # 4. 系统性能指标
            if 'performance_metrics' in performance_data:
                metrics = performance_data['performance_metrics']
                metric_names = list(metrics.keys())
                metric_values = list(metrics.values())
                
                bars = ax4.barh(metric_names, metric_values, 
                               color='#96CEB4', alpha=0.7)
                
                # 添加数值标签
                for bar, value in zip(bars, metric_values):
                    width = bar.get_width()
                    ax4.text(width + 0.01, bar.get_y() + bar.get_height()/2,
                            f'{value:.3f}', ha='left', va='center', fontweight='bold')
                
                ax4.set_xlabel('指标值')
                ax4.set_title('系统性能指标')
                ax4.grid(True, alpha=0.3, axis='x')
            
            # 调整布局
            plt.tight_layout()
            
            # 保存图表
            if save_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = self.charts_dir / f"performance_summary_{timestamp}.png"
            
            plt.savefig(save_path, dpi=300, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            plt.close()
            
            return str(save_path)
            
        except Exception as e:
            print(f"创建性能摘要图表失败: {e}")
            return None