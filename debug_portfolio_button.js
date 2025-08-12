// 调试持仓管理按钮的脚本

console.log('开始调试持仓管理按钮...');

// 检查DOM元素是否存在
function checkElements() {
    const elements = {
        'portfolio-btn': document.getElementById('portfolio-btn'),
        'portfolio-modal': document.getElementById('portfolio-modal'),
        'portfolio-close': document.getElementById('portfolio-close')
    };
    
    console.log('DOM元素检查:');
    for (const [id, element] of Object.entries(elements)) {
        console.log(`${id}: ${element ? '✅ 存在' : '❌ 不存在'}`);
    }
    
    return elements;
}

// 测试按钮点击事件
function testButtonClick() {
    const portfolioBtn = document.getElementById('portfolio-btn');
    
    if (!portfolioBtn) {
        console.error('❌ 找不到持仓管理按钮');
        return;
    }
    
    console.log('✅ 找到持仓管理按钮');
    
    // 检查是否已有事件监听器
    const listeners = getEventListeners ? getEventListeners(portfolioBtn) : null;
    console.log('按钮事件监听器:', listeners);
    
    // 手动触发点击事件
    console.log('手动触发点击事件...');
    portfolioBtn.click();
}

// 检查是否有JavaScript错误
function checkForErrors() {
    window.addEventListener('error', function(e) {
        console.error('JavaScript错误:', e.error);
        console.error('错误位置:', e.filename, '行:', e.lineno);
    });
}

// 页面加载完成后执行检查
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM加载完成，开始检查...');
    
    checkForErrors();
    
    setTimeout(() => {
        checkElements();
        testButtonClick();
    }, 1000);
});

// 导出函数供控制台使用
window.debugPortfolio = {
    checkElements,
    testButtonClick,
    checkForErrors
};