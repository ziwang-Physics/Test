#!/usr/bin/env python3
"""测试 Gemini 延长思考模式修复的脚本"""

import logging
from playwright.sync_api import sync_playwright

# 设置日志
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def test_gemini_mode_fix():
    """测试 Gemini 模式切换修复"""
    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=False, args=[
            '--disable-features=OptimizationHints,Translate,HttpsUpgrades',
            '--disable-background-networking',
            '--disable-client-side-phishing-detection',
            '--disable-field-trial-config',
            '--disable-component-update',
            '--disable-sync',
            '--no-sandbox',
            '--disable-gpu',
            '--ignore-certificate-errors',
            '--disable-dev-shm-usage'
        ])

        try:
            # 创建新页面
            page = browser.new_page()

            # 导航到 Gemini
            page.goto("https://gemini.google.com/u/0/app", wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            # 等待输入框出现
            page.wait_for_selector('[contenteditable="true"][role="textbox"]', timeout=10000)

            # 模拟模式切换
            log.info("测试 Gemini 延长思考模式切换...")

            # 点击模式选择器
            model_btn = page.locator('button[aria-label*="模式挑選器"], button[aria-label*="Model selector"], button[aria-label*="模式选择器"]').first
            model_btn.wait_for(state="visible", timeout=5000)
            model_btn.click()

            # 等待菜单渲染
            page.wait_for_timeout(2000)

            # 检查菜单项
            menu_items = page.evaluate("""() => {
                return [...document.querySelectorAll('gem-menu-item')]
                    .filter(el => (el.innerText || '').trim().length > 0)
                    .length;
            }""")

            log.info(f"菜单项数量: {menu_items}")

            if menu_items >= 2:
                log.info("✅ 菜单项渲染成功")

                # 查找 Pro 模型
                pro_found = page.evaluate("""() => {
                    const items = document.querySelectorAll('gem-menu-item');
                    for (const item of items) {
                        const text = item.innerText || '';
                        if (text.includes('Pro') && !text.includes('Flash')) {
                            return true;
                        }
                    }
                    return false;
                }""")

                if pro_found:
                    log.info("✅ Pro 模型找到")
                else:
                    log.warning("⚠️ Pro 模型未找到")

                # 查找思考程度
                thinking_found = page.evaluate("""() => {
                    const items = document.querySelectorAll('gem-menu-item');
                    for (const item of items) {
                        const text = item.innerText || '';
                        if (text.includes('思考程度') || text.includes('Thinking')) {
                            return true;
                        }
                    }
                    return false;
                }""")

                if thinking_found:
                    log.info("✅ 思考程度菜单项找到")
                else:
                    log.warning("⚠️ 思考程度菜单项未找到")
            else:
                log.warning("⚠️ 菜单项渲染不完整")

        except Exception as e:
            log.error(f"测试失败: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    test_gemini_mode_fix()