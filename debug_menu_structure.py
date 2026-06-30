#!/usr/bin/env python3
"""调试Gemini菜单结构，分析思考程度子菜单问题"""

import logging
from playwright.sync_api import sync_playwright

# 设置日志
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def debug_menu_structure():
    """调试Gemini菜单结构"""
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

            # 导航到Gemini
            log.info("导航到Gemini...")
            page.goto("https://gemini.google.com/u/0/app", wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            # 等待输入框出现
            log.info("等待输入框...")
            page.wait_for_selector('[contenteditable="true"][role="textbox"]', timeout=10000)

            # 点击模式选择器
            log.info("点击模式选择器...")
            model_btn = page.locator('button[aria-label*="模式挑選器"], button[aria-label*="Model selector"], button[aria-label*="模式选择器"]').first
            model_btn.wait_for(state="visible", timeout=5000)
            model_btn.click()

            # 等待菜单渲染
            page.wait_for_timeout(2000)

            # 获取所有菜单项
            log.info("分析菜单结构...")
            menu_items = page.evaluate("""() => {
                const items = document.querySelectorAll('gem-menu-item');
                return [...items].map((el, i) => ({
                    index: i,
                    text: (el.innerText || '').trim(),
                    visible: el.offsetParent !== null,
                    selected: el.classList.contains('selected'),
                    hasChildren: el.querySelector('[data-mat-icon-name="arrow_right"]') !== null
                }));
            }""")

            log.info("菜单项分析:")
            for item in menu_items:
                log.info(f"  {item['index']}: '{item['text']}' (visible: {item['visible']}, selected: {item['selected']}, hasChildren: {item['hasChildren']})")

            # 查找Pro模型
            pro_items = [item for item in menu_items if "Pro" in item['text'] and "Flash" not in item['text']]
            if pro_items:
                log.info(f"✅ Pro模型找到: {pro_items[0]['text']}")
                pro_index = pro_items[0]['index']

                # 点击Pro模型
                log.info("点击Pro模型...")
                page.locator("gem-menu-item").nth(pro_index).click()
                page.wait_for_timeout(2000)

                # 重新获取菜单项
                log.info("重新分析菜单结构...")
                new_menu_items = page.evaluate("""() => {
                    const items = document.querySelectorAll('gem-menu-item');
                    return [...items].map((el, i) => ({
                        index: i,
                        text: (el.innerText || '').trim(),
                        visible: el.offsetParent !== null,
                        selected: el.classList.contains('selected'),
                        hasChildren: el.querySelector('[data-mat-icon-name="arrow_right"]') !== null
                    }));
                }""")

                log.info("新菜单项分析:")
                for item in new_menu_items:
                    log.info(f"  {item['index']}: '{item['text']}' (visible: {item['visible']}, selected: {item['selected']}, hasChildren: {item['hasChildren']})")

                # 查找思考程度
                thinking_items = [item for item in new_menu_items if "思考程度" in item['text'] or "Thinking" in item['text']]
                if thinking_items:
                    log.info(f"✅ 思考程度找到: {thinking_items[0]['text']}")
                    thinking_index = thinking_items[0]['index']

                    # 点击思考程度
                    log.info("点击思考程度...")
                    page.locator("gem-menu-item").nth(thinking_index).click()
                    page.wait_for_timeout(2000)

                    # 重新获取菜单项
                    log.info("分析子菜单结构...")
                    submenu_items = page.evaluate("""() => {
                        const items = document.querySelectorAll('gem-menu-item');
                        return [...items].map((el, i) => ({
                            index: i,
                            text: (el.innerText || '').trim(),
                            visible: el.offsetParent !== null,
                            selected: el.classList.contains('selected'),
                            hasChildren: el.querySelector('[data-mat-icon-name="arrow_right"]') !== null
                        }));
                    }""")

                    log.info("子菜单项分析:")
                    for item in submenu_items:
                        log.info(f"  {item['index']}: '{item['text']}' (visible: {item['visible']}, selected: {item['selected']}, hasChildren: {item['hasChildren']})")

                    # 查找延長
                    extended_items = [item for item in submenu_items if "延長" in item['text'] and "標準" not in item['text']]
                    if extended_items:
                        log.info(f"✅ 延長找到: {extended_items[0]['text']}")
                    else:
                        log.warning("⚠️ 延長未找到")
                else:
                    log.warning("⚠️ 思考程度未找到")
            else:
                log.warning("⚠️ Pro模型未找到")

        except Exception as e:
            log.error(f"调试失败: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    debug_menu_structure()