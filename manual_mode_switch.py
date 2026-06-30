#!/usr/bin/env python3
"""按照用户指导手动操作Gemini延长思考模式：点击模式选择器 → 思考程度 → 延长"""

import logging
from playwright.sync_api import sync_playwright

# 设置日志
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def manual_mode_switch():
    """按照用户指导手动操作Gemini延长思考模式"""
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

            # 步骤1：点击模式选择器
            log.info("步骤1：点击模式选择器...")
            model_btn = page.locator('button[aria-label*="模式挑選器"], button[aria-label*="Model selector"], button[aria-label*="模式选择器"]').first
            model_btn.wait_for(state="visible", timeout=5000)
            model_btn.click()
            page.wait_for_timeout(2000)

            # 步骤2：找到并点击思考程度
            log.info("步骤2：找到并点击思考程度...")
            # 从调试结果看，思考程度对应索引1的"3.5 思考 解决复杂问题"
            thinking_btn = page.locator("gem-menu-item").nth(1)
            thinking_btn.wait_for(state="visible", timeout=5000)
            thinking_btn.click()
            page.wait_for_timeout(2000)

            # 步骤3：找到并点击延长
            log.info("步骤3：找到并点击延长...")
            # 等待子菜单出现
            page.wait_for_timeout(2000)

            # 在子菜单中查找延長选项
            extended_btn = page.locator("gem-menu-item").filter(has_text="延長").first
            extended_btn.wait_for(state="visible", timeout=5000)
            extended_btn.click()
            page.wait_for_timeout(2000)

            # 验证模式是否切换成功
            log.info("验证模式切换...")
            new_mode = page.evaluate("""() => {
                const btn = document.querySelector('button[aria-label*="模式"]');
                if (!btn) return 'unknown';
                const aria = btn.getAttribute('aria-label') || '';
                return aria.includes('延長') || aria.includes('Extended') ? 'extended' : 'standard';
            }""")

            if new_mode == 'extended':
                log.info("✅ 成功！Pro Extended Thinking模式已启用")
                log.info("现在可以发送复杂问题了，Gemini将使用延长思考模式回答")
            else:
                log.warning("⚠️ 模式切换可能未完全生效")

            # 等待用户确认
            log.info("操作完成，请检查浏览器中Gemini的模式是否已切换为延长思考")
            input("按回车键关闭浏览器...")

        except Exception as e:
            log.error(f"操作失败: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    manual_mode_switch()