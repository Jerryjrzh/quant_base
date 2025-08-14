/**
 * 前端统一配置管理器
 * 从后端API加载配置，处理策略映射和兼容性
 */

class FrontendConfigManager {
    constructor() {
        this.config = null;
        this.strategies = {};
        this.legacyMapping = {};
        this.reverseMapping = {};
        this.loaded = false;
        
        // 初始化加载配置
        this.loadConfig();
    }
    
    /**
     * 从后端API加载配置
     */
    async loadConfig() {
        try {
            const response = await fetch('/api/config/unified');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            if (data.success) {
                this.config = data.data;
                this.strategies = this.config.strategies || {};
                this._buildMappings();
                this.loaded = true;
                console.log('配置加载成功:', Object.keys(this.strategies).length, '个策略');
            } else {
                throw new Error(data.error || '加载配置失败');
            }
        } catch (error) {
            console.error('加载配置失败，使用默认配置:', error);
            this._loadDefaultConfig();
        }
    }
    
    /**
     * 构建策略映射表
     */
    _buildMappings() {
        this.legacyMapping = {};
        this.reverseMapping = {};
        
        Object.keys(this.strategies).forEach(strategyId => {
            const strategy = this.strategies[strategyId];
            const legacyMap = strategy.legacy_mapping || {};
            
            // 构建正向映射 (旧ID -> 新ID)
            if (legacyMap.old_id) {
                this.legacyMapping[legacyMap.old_id] = strategyId;
            }
            if (legacyMap.api_id) {
                this.legacyMapping[legacyMap.api_id] = strategyId;
            }
            
            // 构建反向映射 (新ID -> API ID)
            this.reverseMapping[strategyId] = legacyMap.api_id || legacyMap.old_id || strategyId;
        });
    }
    
    /**
     * 加载默认配置（当API不可用时）
     */
    _loadDefaultConfig() {
        this.legacyMapping = {
            'PRE_CROSS': '临界金叉_v1.0',
            'TRIPLE_CROSS': '三重金叉_v1.0',
            'MACD_ZERO_AXIS': 'macd零轴启动_v1.0',
            'WEEKLY_GOLDEN_CROSS_MA': '周线金叉+日线ma_v1.0',
            'ABYSS_BOTTOMING': '深渊筑底策略_v2.0'
        };
        
        this.reverseMapping = {};
        Object.keys(this.legacyMapping).forEach(oldId => {
            const newId = this.legacyMapping[oldId];
            this.reverseMapping[newId] = oldId;
        });
        
        this.loaded = true;
    }
    
    /**
     * 等待配置加载完成
     */
    async waitForLoad() {
        while (!this.loaded) {
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }
    
    /**
     * 获取所有策略
     */
    getStrategies() {
        return this.strategies;
    }
    
    /**
     * 获取单个策略
     */
    getStrategy(strategyId) {
        return this.strategies[strategyId];
    }
    
    /**
     * 获取已启用的策略
     */
    getEnabledStrategies() {
        const enabled = {};
        Object.keys(this.strategies).forEach(id => {
            const strategy = this.strategies[id];
            if (strategy.enabled !== false) {
                enabled[id] = strategy;
            }
        });
        return enabled;
    }
    
    /**
     * 获取全局设置
     */
    getGlobalSettings() {
        return this.config?.global_settings || {};
    }
    
    /**
     * 获取前端设置
     */
    getFrontendSettings() {
        return this.config?.frontend_settings || {};
    }
}

// 移除重复的函数定义，这些函数在后面已经重新定义

/**
 * 获取策略显示名称
 * @param {object} strategy 策略对象
 * @returns {string} 显示名称
 */
function getStrategyDisplayName(strategy) {
    if (strategy.name && strategy.version) {
        return `${strategy.name} v${strategy.version}`;
    }
    return strategy.id || '未知策略';
}

/**
 * 检查策略是否兼容当前系统
 * @param {object} strategy 策略对象
 * @returns {boolean} 是否兼容
 */
function isStrategyCompatible(strategy) {
    // 基本兼容性检查
    if (!strategy.id || !strategy.name) {
        return false;
    }

    // 检查是否有必需的配置
    if (strategy.required_data_length && strategy.required_data_length > 1000) {
        console.warn(`策略 ${strategy.id} 需要过多数据: ${strategy.required_data_length} 天`);
        return false;
    }

    return true;
}

/**
 * 格式化策略配置用于显示
 * @param {object} config 策略配置
 * @returns {object} 格式化后的配置
 */
function formatStrategyConfigForDisplay(config) {
    const formatted = { ...config };

    // 格式化数值
    Object.keys(formatted).forEach(key => {
        const value = formatted[key];
        if (typeof value === 'number') {
            if (key.includes('percent') || key.includes('ratio')) {
                formatted[key] = `${(value * 100).toFixed(1)}%`;
            } else if (key.includes('days')) {
                formatted[key] = `${value} 天`;
            } else if (value < 1 && value > 0) {
                formatted[key] = value.toFixed(3);
            }
        }
    });

    return formatted;
}

// 移除重复的导出代码// 创建全局配置管理器实例
const configManager = new FrontendConfigManager();

// 兼容性映射对象 - 保持向后兼容
const STRATEGY_ID_MAPPING = {
    'PRE_CROSS': '临界金叉_v1.0',
    'TRIPLE_CROSS': '三重金叉_v1.0',
    'MACD_ZERO_AXIS': 'macd零轴启动_v1.0',
    'WEEKLY_GOLDEN_CROSS_MA': '周线金叉+日线ma_v1.0',
    'ABYSS_BOTTOMING': '深渊筑底策略_v2.0'
};

const REVERSE_STRATEGY_MAPPING = {
    '临界金叉_v1.0': 'PRE_CROSS',
    '三重金叉_v1.0': 'TRIPLE_CROSS',
    'macd零轴启动_v1.0': 'MACD_ZERO_AXIS',
    '周线金叉+日线ma_v1.0': 'WEEKLY_GOLDEN_CROSS_MA',
    '深渊筑底策略_v2.0': 'ABYSS_BOTTOMING'
};

/**
 * 将旧策略ID转换为新策略ID
 * @param {string} oldStrategyId 旧策略ID
 * @returns {string} 新策略ID
 */
function mapOldToNewStrategyId(oldStrategyId) {
    if (!configManager.loaded) {
        console.warn('配置管理器尚未加载完成，使用默认映射');
        return STRATEGY_ID_MAPPING[oldStrategyId] || oldStrategyId;
    }
    return configManager.legacyMapping[oldStrategyId] || oldStrategyId;
}

/**
 * 将新策略ID转换为旧策略ID（用于API调用）
 * @param {string} newStrategyId 新策略ID
 * @returns {string} 旧策略ID
 */
function mapNewToOldStrategyId(newStrategyId) {
    if (!configManager.loaded) {
        console.warn('配置管理器尚未加载完成，使用默认映射');
        return REVERSE_STRATEGY_MAPPING[newStrategyId] || newStrategyId;
    }
    return configManager.reverseMapping[newStrategyId] || newStrategyId;
}

/**
 * 获取策略显示名称
 * @param {object} strategy 策略对象
 * @returns {string} 显示名称
 */
function getStrategyDisplayName(strategy) {
    if (strategy.name && strategy.version) {
        return `${strategy.name} v${strategy.version}`;
    }
    return strategy.id || '未知策略';
}

/**
 * 检查策略是否兼容当前系统
 * @param {object} strategy 策略对象
 * @returns {boolean} 是否兼容
 */
function isStrategyCompatible(strategy) {
    // 基本兼容性检查
    if (!strategy.id || !strategy.name) {
        return false;
    }

    // 检查是否有必需的配置
    if (strategy.required_data_length && strategy.required_data_length > 1000) {
        console.warn(`策略 ${strategy.id} 需要过多数据: ${strategy.required_data_length} 天`);
        return false;
    }

    return true;
}

/**
 * 格式化策略配置用于显示
 * @param {object} config 策略配置
 * @returns {object} 格式化后的配置
 */
function formatStrategyConfigForDisplay(config) {
    const formatted = { ...config };

    // 格式化数值
    Object.keys(formatted).forEach(key => {
        const value = formatted[key];
        if (typeof value === 'number') {
            if (key.includes('percent') || key.includes('ratio')) {
                formatted[key] = `${(value * 100).toFixed(1)}%`;
            } else if (key.includes('days')) {
                formatted[key] = `${value} 天`;
            } else if (value < 1 && value > 0) {
                formatted[key] = value.toFixed(3);
            }
        }
    });

    return formatted;
}

/**
 * 加载可用策略到下拉框
 */
async function loadAvailableStrategies() {
    await configManager.waitForLoad();
    
    const strategySelect = document.getElementById('strategy-select');
    if (!strategySelect) return;
    
    // 清空现有选项
    strategySelect.innerHTML = '<option value="">请选择策略</option>';
    
    // 添加策略选项
    const strategies = configManager.getEnabledStrategies();
    Object.keys(strategies).forEach(strategyId => {
        const strategy = strategies[strategyId];
        const option = document.createElement('option');
        option.value = strategyId;
        option.textContent = getStrategyDisplayName(strategy);
        strategySelect.appendChild(option);
    });
    
    console.log('策略列表加载完成:', Object.keys(strategies).length, '个策略');
}

/**
 * 获取策略配置
 * @param {string} strategyId 策略ID
 * @returns {object} 策略配置
 */
function getStrategyConfig(strategyId) {
    const strategy = configManager.getStrategy(strategyId);
    return strategy?.config || {};
}

/**
 * 获取前端设置
 * @param {string} key 设置键名
 * @param {any} defaultValue 默认值
 * @returns {any} 设置值
 */
function getFrontendSetting(key, defaultValue = null) {
    const settings = configManager.getFrontendSettings();
    return settings[key] !== undefined ? settings[key] : defaultValue;
}

// 导出函数（如果使用模块系统）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        configManager,
        mapOldToNewStrategyId,
        mapNewToOldStrategyId,
        getStrategyDisplayName,
        isStrategyCompatible,
        formatStrategyConfigForDisplay,
        loadAvailableStrategies,
        getStrategyConfig,
        getFrontendSetting
    };
}

// 在浏览器环境中，将函数添加到全局作用域
if (typeof window !== 'undefined') {
    window.configManager = configManager;
    window.STRATEGY_ID_MAPPING = STRATEGY_ID_MAPPING;
    window.REVERSE_STRATEGY_MAPPING = REVERSE_STRATEGY_MAPPING;
    window.mapOldToNewStrategyId = mapOldToNewStrategyId;
    window.mapNewToOldStrategyId = mapNewToOldStrategyId;
    window.getStrategyDisplayName = getStrategyDisplayName;
    window.isStrategyCompatible = isStrategyCompatible;
    window.formatStrategyConfigForDisplay = formatStrategyConfigForDisplay;
    window.loadAvailableStrategies = loadAvailableStrategies;
    window.getStrategyConfig = getStrategyConfig;
    window.getFrontendSetting = getFrontendSetting;
}