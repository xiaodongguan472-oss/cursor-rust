"""全局样式表 — 专业级现代桌面应用主题"""

MAIN_STYLESHEET = """
* {
    outline: none;
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei UI",
                 "PingFang SC", "Noto Sans CJK SC", sans-serif;
}

QMainWindow {
    background-color: #f4f6f9;
}

QToolTip {
    background-color: #1e293b;
    color: #f1f5f9;
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 500;
    opacity: 240;
}

/* ===== 侧边栏 ===== */
#Sidebar {
    background: qlineargradient(x1:0,y1:0,x2:0.3,y2:1,
        stop:0 #1e1b4b, stop:0.5 #312e81, stop:1 #3730a3);
    border: none;
    border-right: 1px solid rgba(255, 255, 255, 0.08);
}

#SidebarBtn {
    background: transparent;
    color: rgba(255, 255, 255, 0.55);
    border: none;
    border-radius: 10px;
    text-align: left;
    padding: 10px 14px 10px 18px;
    font-size: 13px;
    font-weight: 500;
    margin: 1px 10px;
}
#SidebarBtn:hover {
    background-color: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.95);
}
#SidebarBtn:pressed {
    background-color: rgba(255, 255, 255, 0.12);
}

#SidebarBtnActive {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(99,102,241,0.32), stop:1 rgba(99,102,241,0.12));
    color: #ffffff;
    border: none;
    border-left: 3px solid #a78bfa;
    border-radius: 10px;
    text-align: left;
    padding: 10px 14px 10px 15px;
    font-size: 13px;
    font-weight: 700;
    margin: 1px 10px;
}

/* ===== 内容区 ===== */
#ContentArea {
    background-color: #f4f6f9;
    border: none;
}

/* ===== 卡片 ===== */
#Card {
    background-color: #ffffff;
    border: 1px solid #e8ecf1;
    border-radius: 18px;
}
#Card:hover {
    border-color: #dde1e7;
}

#CardTitle {
    color: #0f172a;
    font-size: 15px;
    font-weight: 700;
    background: transparent;
}

#CardLabel {
    color: #64748b;
    font-size: 13px;
    font-weight: 400;
    background: transparent;
}

#CardValue {
    color: #1e293b;
    font-size: 13px;
    font-weight: 500;
    background: transparent;
}

/* ===== 按钮 ===== */
#PrimaryBtn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #4f46e5, stop:1 #6366f1);
    color: white;
    border: none;
    border-radius: 12px;
    padding: 10px 26px;
    font-size: 13px;
    font-weight: 700;
    min-height: 40px;
}
#PrimaryBtn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #4338ca, stop:1 #4f46e5);
}
#PrimaryBtn:pressed {
    background-color: #3730a3;
}
#PrimaryBtn:disabled {
    background: #94a3b8;
}

#SecondaryBtn {
    background-color: #ffffff;
    color: #334155;
    border: 1.5px solid #e2e8f0;
    border-radius: 12px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 600;
    min-height: 40px;
}
#SecondaryBtn:hover {
    background-color: #f8fafc;
    border-color: #cbd5e1;
    color: #0f172a;
}

#DangerBtn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #dc2626, stop:1 #ef4444);
    color: white;
    border: none;
    border-radius: 12px;
    padding: 10px 26px;
    font-size: 13px;
    font-weight: 700;
    min-height: 40px;
}
#DangerBtn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #b91c1c, stop:1 #dc2626);
}

/* ===== 输入框 ===== */
QLineEdit {
    background-color: #ffffff;
    border: 2px solid #e2e8f0;
    border-radius: 12px;
    padding: 11px 16px;
    font-size: 13px;
    color: #1e293b;
    selection-background-color: #c7d2fe;
    selection-color: #1e1b4b;
}
QLineEdit:hover {
    border-color: #cbd5e1;
}
QLineEdit:focus {
    border: 2px solid #6366f1;
    background-color: #fafbff;
}

QLineEdit#AuthCdkInput {
    font-size: 14px;
    padding: 3px 14px;
    border: 2px solid #e2e8f0;
    border-radius: 12px;
    background-color: #fafbfc;
    font-weight: 500;
}
QLineEdit#AuthCdkInput:hover {
    border-color: #cbd5e1;
    background-color: #ffffff;
}
QLineEdit#AuthCdkInput:focus {
    border: 2px solid #6366f1;
    background-color: #ffffff;
}

QWidget#AuthCodeDisplay {
    background-color: #fafbfc;
    border: 2px solid #e2e8f0;
    border-radius: 12px;
}
QWidget#AuthCodeDisplay QLabel#AuthCodeValue {
    font-size: 13px;
    font-weight: 500;
    color: #475569;
    background: transparent;
    border: none;
    outline: none;
    margin: 0px;
    padding: 0px;
    font-family: "SF Mono", "Menlo", "Consolas", monospace;
}

QFrame#InfoFieldStrip {
    background-color: #fafbfc;
    border: 1.5px solid #e2e8f0;
    border-radius: 12px;
}
QFrame#InfoFieldStrip:hover {
    border-color: #cbd5e1;
    background-color: #ffffff;
}
QLabel#InfoFieldValue {
    font-size: 13px;
    font-weight: 500;
    color: #334155;
    background: transparent;
    border: none;
}

QLabel#DisplayValue {
    font-size: 13px;
    font-weight: 500;
    color: #334155;
    background: transparent;
    border: none;
}

#SectionToolBtn {
    background-color: #f1f5f9;
    color: #334155;
    border: 1.5px solid #e2e8f0;
    border-radius: 10px;
    padding: 7px 16px;
    font-size: 12px;
    font-weight: 600;
    min-height: 32px;
}
#SectionToolBtn:hover {
    background-color: #e2e8f0;
    border-color: #cbd5e1;
    color: #0f172a;
}
#SectionToolBtn:pressed {
    background-color: #cbd5e1;
}
#SectionToolBtn:disabled {
    color: #94a3b8;
    background: #f8fafc;
}

#SectionPanel {
    background-color: #ffffff;
    border: 1px solid #e8ecf1;
    border-radius: 16px;
}

/* ===== 表格 ===== */
QTableWidget {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    gridline-color: #f1f5f9;
    font-size: 13px;
    color: #1e293b;
    selection-background-color: #eef2ff;
    selection-color: #1e293b;
}
QTableWidget::item {
    padding: 10px 12px;
    border-bottom: 1px solid #f1f5f9;
}
QTableWidget::item:hover {
    background-color: #f8fafc;
}
QTableWidget::item:selected {
    background-color: #eef2ff;
}
QHeaderView::section {
    background-color: #f8fafc;
    color: #64748b;
    border: none;
    border-bottom: 2px solid #e2e8f0;
    padding: 10px 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    text-transform: uppercase;
}

/* ===== 滚动条 ===== */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 4px 0;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 3px;
    min-height: 40px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    height: 0;
    background: transparent;
}
QScrollBar:horizontal {
    height: 8px;
    background: transparent;
}
QScrollBar::handle:horizontal {
    background: #cbd5e1;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    width: 0;
    background: transparent;
}

/* ===== 消息框 ===== */
QMessageBox {
    background-color: #ffffff;
}
QMessageBox QLabel {
    color: #1e293b;
    font-size: 14px;
    line-height: 1.5;
}
QMessageBox QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #4f46e5, stop:1 #6366f1);
    color: white;
    border: none;
    border-radius: 10px;
    padding: 10px 28px;
    font-size: 13px;
    font-weight: 700;
    min-width: 80px;
}
QMessageBox QPushButton:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #4338ca, stop:1 #4f46e5);
}
QMessageBox QPushButton:pressed {
    background: #3730a3;
}

/* ===== 对话框 ===== */
QDialog {
    background-color: #f8fafc;
}

/* ===== 复选框 ===== */
QCheckBox {
    color: #475569;
    font-size: 13px;
    font-weight: 500;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #cbd5e1;
    border-radius: 5px;
    background: #ffffff;
}
QCheckBox::indicator:hover {
    border-color: #6366f1;
}
QCheckBox::indicator:checked {
    background: #4f46e5;
    border-color: #4f46e5;
}

/* ===== 下拉框 ===== */
QComboBox {
    background-color: #ffffff;
    border: 2px solid #e2e8f0;
    border-radius: 10px;
    padding: 8px 14px;
    font-size: 13px;
    color: #1e293b;
    min-height: 36px;
}
QComboBox:hover {
    border-color: #cbd5e1;
}
QComboBox:focus {
    border-color: #6366f1;
}
QComboBox::drop-down {
    border: none;
    width: 28px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    selection-background-color: #eef2ff;
    selection-color: #1e293b;
    padding: 4px;
}
"""
