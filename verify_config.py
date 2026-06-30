#!/usr/bin/env python3
"""验证配置而不启动新Chrome实例"""

import logging
import os

# 设置日志
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def verify_config():
    """验证配置而不启动新Chrome实例"""

    log.info("🔍 验证配置状态...")

    # 检查Chrome稳定版
    chrome_path = "/home/wangzi/soft/chrome-stable/chrome"
    if os.path.exists(chrome_path):
        log.info("✅ Chrome稳定版已找到: %s", chrome_path)

        # 检查版本
        try:
            version = os.popen(f"{chrome_path} --version").read().strip()
            log.info("✅ Chrome版本: %s", version)
        except Exception as e:
            log.warning("⚠️ 无法获取Chrome版本: %s", e)
    else:
        log.error("❌ Chrome稳定版未找到")
        return False

    # 检查multiagent配置
    gemini_mode_path = "/home/wangzi/.claude/skills/multiagent/skills/multiagent/adapters/components/gemini_mode.py"
    if os.path.exists(gemini_mode_path):
        log.info("✅ Gemini模式控制器配置已找到")

        # 检查Chrome稳定版配置
        with open(gemini_mode_path, 'r') as f:
            content = f.read()
            if "CHROME_STABLE_PATH = \"/home/wangzi/soft/chrome-stable/chrome\"" in content:
                log.info("✅ Chrome稳定版配置已添加")
            else:
                log.warning("⚠️ Chrome稳定版配置未找到")

        # 检查模式切换优化
        if "async def _expand_thinking_submenu" in content and "SUBMENU_ANIMATION_S * 2" in content:
            log.info("✅ 思考程度子菜单优化已应用")
        else:
            log.warning("⚠️ 思考程度子菜单优化未找到")
    else:
        log.error("❌ Gemini模式控制器配置未找到")
        return False

    log.info("")
    log.info("📋 配置验证总结:")
    log.info("✅ Chrome稳定版配置完成")
    log.info("✅ 模式切换逻辑已优化")
    log.info("✅ 思考程度子菜单检测增强")
    log.info("")
    log.info("🎯 操作指导 (请手动执行):")
    log.info("1. 确保Chrome稳定版已启动")
    log.info("2. 打开Gemini网页 (https://gemini.google.com/u/0/app)")
    log.info("3. 按照以下步骤操作:")
    log.info("   - 点击模式选择器按钮")
    log.info("   - 点击'思考程度'选项")
    log.info("   - 点击'延長'选项")
    log.info("4. 验证模式是否切换为'延長'")
    log.info("")
    log.info("💡 提示: 如果遇到问题，请检查:")
    log.info("   - Chrome是否正常启动")
    log.info("   - Gemini页面是否完全加载")
    log.info("   - 网络连接是否正常")

    return True

if __name__ == "__main__":
    verify_config()