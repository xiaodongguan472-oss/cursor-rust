"""服务条款 / 隐私政策 / 使用政策 弹窗"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QTextBrowser,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


_TERMS_OF_SERVICE = """\
<h2>服务条款</h2>
<p><b>最后更新：2026 年 4 月</b></p>

<h3>1. 服务概述</h3>
<p>AI助手（以下简称"本软件"）是一款聚合多款 AI 编程工具的管理平台，为用户提供 Cursor、Kiro、Codex、Claude Code、Gemini、OpenClaw 等工具的统一管理服务。</p>

<h3>2. 账号注册与使用</h3>
<ul>
<li>您需注册账号并使用有效邮箱完成验证。</li>
<li>每个邮箱仅可注册一个账号。</li>
<li>您有责任保管好自己的账号和密码，因账号被盗产生的损失由您自行承担。</li>
<li>禁止出租、出借、转让或以任何方式分享您的账号给第三方。</li>
</ul>

<h3>3. 激活码与付费</h3>
<ul>
<li>本软件通过激活码（卡密）提供服务，激活码有明确的使用期限和额度限制。</li>
<li>激活码一经激活，不支持退款。</li>
<li>激活码仅供个人使用，严禁二次销售或分发。</li>
<li>若检测到滥用行为，我们保留封禁账号和激活码的权利。</li>
</ul>

<h3>4. 服务可用性</h3>
<ul>
<li>我们将尽最大努力保障服务的稳定运行，但不对服务的持续可用性做出保证。</li>
<li>因第三方平台（如 AWS、Cursor 等）策略变化导致的服务中断，不属于我们的责任范围。</li>
<li>我们保留因维护、升级等原因暂停服务的权利，并会提前通知用户。</li>
</ul>

<h3>5. 禁止行为</h3>
<ul>
<li>禁止对本软件进行逆向工程、反编译或破解。</li>
<li>禁止利用本软件从事任何违法或侵权活动。</li>
<li>禁止通过自动化工具批量注册账号或刷取额度。</li>
<li>禁止干扰或破坏服务的正常运行。</li>
</ul>

<h3>6. 免责声明</h3>
<ul>
<li>本软件仅作为工具管理平台，不对第三方 AI 平台的输出内容负责。</li>
<li>因不可抗力（包括但不限于政策变化、自然灾害、网络攻击）导致的服务中断，我们不承担责任。</li>
<li>使用本软件所产生的一切后果由用户自行承担。</li>
</ul>

<h3>7. 条款变更</h3>
<p>我们保留随时修改本条款的权利。修改后的条款将在软件内公布，继续使用即视为您接受新条款。</p>
"""

_PRIVACY_POLICY = """\
<h2>隐私政策</h2>
<p><b>最后更新：2026 年 4 月</b></p>

<h3>1. 信息收集</h3>
<p>我们在提供服务过程中，可能收集以下信息：</p>
<ul>
<li><b>账号信息</b>：注册邮箱、昵称、密码（加密存储）。</li>
<li><b>设备信息</b>：设备唯一标识符（用于激活码绑定和限制设备数量）。</li>
<li><b>使用数据</b>：激活码使用次数、登录时间等服务运行必需的数据。</li>
<li><b>日志数据</b>：服务端请求日志（用于故障排查和安全防护）。</li>
</ul>

<h3>2. 信息使用</h3>
<p>我们收集的信息仅用于以下目的：</p>
<ul>
<li>提供和维护本软件的核心服务。</li>
<li>验证用户身份和管理激活码。</li>
<li>监控和防止滥用行为。</li>
<li>改进产品体验和修复问题。</li>
</ul>

<h3>3. 信息存储</h3>
<ul>
<li>您的密码使用 SHA-256 加盐哈希存储，我们无法获取您的明文密码。</li>
<li>所有敏感数据传输均使用 AES 加密。</li>
<li>数据存储在安全的服务器上，采取必要的安全防护措施。</li>
</ul>

<h3>4. 信息共享</h3>
<ul>
<li>我们<b>不会</b>将您的个人信息出售给任何第三方。</li>
<li>我们<b>不会</b>与第三方共享您的账号信息，除非法律要求。</li>
<li>在使用第三方 AI 平台时，相关请求数据将按各平台自身的隐私政策处理。</li>
</ul>

<h3>5. 本地数据</h3>
<ul>
<li>本软件会在您的设备本地存储配置文件和认证令牌。</li>
<li>这些本地数据仅在您的设备上存在，不会被上传到我们的服务器。</li>
<li>卸载软件时，建议手动清理相关配置目录。</li>
</ul>

<h3>6. Cookie 与跟踪</h3>
<p>本软件为桌面应用程序，不使用 Cookie 或第三方跟踪技术。</p>

<h3>7. 用户权利</h3>
<p>您有权：</p>
<ul>
<li>查看和修改您的个人信息（昵称、密码）。</li>
<li>申请删除您的账号和相关数据。</li>
<li>了解我们存储了哪些关于您的信息。</li>
</ul>

<h3>8. 未成年人保护</h3>
<p>本软件不面向 16 岁以下未成年人，我们不会故意收集未成年人的个人信息。</p>

<h3>9. 政策变更</h3>
<p>如隐私政策发生重大变更，我们将通过软件公告通知用户。</p>
"""

_USAGE_POLICY = """\
<h2>使用政策</h2>
<p><b>最后更新：2026 年 4 月</b></p>

<h3>1. 合理使用原则</h3>
<p>为确保所有用户能够获得良好的服务体验，请遵守以下使用规范：</p>
<ul>
<li>请合理使用每日额度，避免无意义的大量重复请求。</li>
<li>不要通过脚本或自动化工具批量消耗额度。</li>
<li>一个激活码仅供一人使用，请勿多人共享。</li>
</ul>

<h3>2. 设备限制</h3>
<ul>
<li>每个激活码有最大绑定设备数限制（默认 2 台）。</li>
<li>超出设备限制时，需要解绑旧设备后才能在新设备上使用。</li>
<li>频繁更换设备可能触发安全检测。</li>
</ul>

<h3>3. 频率限制</h3>
<p>为防止滥用和保障服务质量，我们对 API 调用实施频率限制：</p>
<ul>
<li>每 10 分钟、每小时、每天均有对应的请求上限。</li>
<li>超出限制后将暂时无法使用，等待冷却期过后自动恢复。</li>
<li>如有特殊需求，可联系管理员申请调整限额。</li>
</ul>

<h3>4. 账号安全</h3>
<ul>
<li>请勿将激活码、账号密码、配置文件截图发送给他人。</li>
<li>请勿在公共场合或不安全的网络环境下登录。</li>
<li>发现账号异常请立即修改密码。</li>
</ul>

<h3>5. 内容规范</h3>
<ul>
<li>禁止使用本软件生成违法、色情、暴力或侵权内容。</li>
<li>禁止使用本软件进行任何形式的网络攻击或恶意活动。</li>
<li>用户应对使用 AI 工具生成的内容承担全部责任。</li>
</ul>

<h3>6. 违规处理</h3>
<p>对于违反使用政策的行为，我们将采取以下措施：</p>
<ul>
<li><b>警告</b>：首次轻微违规将收到警告通知。</li>
<li><b>限流</b>：多次违规将降低额度或缩短使用期限。</li>
<li><b>封禁</b>：严重违规将永久封禁账号和激活码，不予退款。</li>
</ul>

<h3>7. 客户端行为</h3>
<ul>
<li>本软件需要在后台运行以维持服务（如 Cursor 无感换号等功能）。</li>
<li>本软件会修改部分编辑器的配置文件以实现功能，修改内容仅限于认证相关配置。</li>
<li>软件运行期间请勿手动修改被管理的配置文件，以免造成冲突。</li>
</ul>

<h3>8. 反馈与投诉</h3>
<p>如您对使用政策有疑问或需要投诉，请通过软件内公告中提供的联系方式联系我们。</p>
"""

POLICIES = {
    "terms": ("服务条款", _TERMS_OF_SERVICE),
    "privacy": ("隐私政策", _PRIVACY_POLICY),
    "usage": ("使用政策", _USAGE_POLICY),
}


class PolicyDialog(QDialog):
    """显示政策/条款内容的弹窗"""

    def __init__(self, policy_key: str, parent=None):
        super().__init__(parent)
        title, html = POLICIES.get(policy_key, ("", ""))
        self.setWindowTitle(title)
        self.setMinimumSize(560, 520)
        self.resize(620, 600)
        self.setStyleSheet("background: #ffffff;")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel(title)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFixedHeight(52)
        header.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #0f172a; "
            "background: #f8fafc; border-bottom: 1px solid #e2e8f0; "
            "padding: 0 24px;"
        )
        layout.addWidget(header)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html)
        browser.setStyleSheet(
            "QTextBrowser { "
            "  border: none; padding: 24px 32px; "
            "  font-size: 14px; color: #334155; line-height: 1.7; "
            "  background: #ffffff; "
            "}"
        )
        layout.addWidget(browser, 1)

        btn_bar = QVBoxLayout()
        btn_bar.setContentsMargins(24, 12, 24, 16)
        close_btn = QPushButton("我已知晓")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedHeight(40)
        close_btn.setStyleSheet(
            "QPushButton { "
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #4f46e5, stop:1 #6366f1);"
            "  color: #fff; border: none; border-radius: 10px; "
            "  font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { "
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #4338ca, stop:1 #4f46e5); }"
        )
        shadow = QGraphicsDropShadowEffect(close_btn)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(99, 102, 241, 60))
        close_btn.setGraphicsEffect(shadow)
        close_btn.clicked.connect(self.accept)
        btn_bar.addWidget(close_btn)
        layout.addLayout(btn_bar)
