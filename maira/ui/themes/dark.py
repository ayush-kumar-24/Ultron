"""Default dark theme QSS."""

DARK_THEME = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QListWidget {
    background-color: #181825;
    border: none;
    padding: 8px;
}
QListWidget::item {
    padding: 10px 12px;
    border-radius: 6px;
}
QListWidget::item:selected {
    background-color: #313244;
    color: #89b4fa;
}
QPushButton {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 16px;
}
QPushButton:hover {
    background-color: #45475a;
}
QPushButton:pressed {
    background-color: #585b70;
}
QLineEdit, QTextEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px;
    color: #cdd6f4;
}
QScrollArea {
    border: none;
    background-color: #1e1e2e;
}
QLabel#errorBanner {
    background-color: #452a2a;
    color: #f38ba8;
    padding: 8px 12px;
    border-radius: 6px;
}
QLabel#userBubble {
    background-color: #313244;
    padding: 10px 12px;
    border-radius: 8px;
}
QLabel#assistantBubble {
    background-color: #11111b;
    padding: 10px 12px;
    border-radius: 8px;
}
QLabel#chatHeader {
    color: #cdd6f4;
    font-size: 15px;
    font-weight: 600;
    padding: 4px 0;
}
QPushButton#newChatButton {
    padding: 6px 12px;
}
QPushButton#historyToggleButton {
    padding: 6px 12px;
    min-width: 110px;
}
QPushButton#contextToggleButton {
    padding: 6px 12px;
}
QLabel#contextDebugPanel {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    color: #a6adc8;
    padding: 10px 12px;
}
QWidget#chatHistoryPanel {
    background-color: #181825;
    border-right: 1px solid #313244;
}
QLabel#historyTitle {
    color: #a6adc8;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.4px;
    padding: 2px 4px;
}
QListWidget#chatHistoryList {
    background-color: transparent;
    border: none;
    padding: 0;
    outline: none;
}
QListWidget#chatHistoryList::item {
    color: #cdd6f4;
    padding: 10px 10px;
    margin: 2px 0;
    border-radius: 8px;
}
QListWidget#chatHistoryList::item:selected {
    background-color: #313244;
    color: #89b4fa;
}
QListWidget#chatHistoryList::item:hover {
    background-color: #1e1e2e;
}
QLabel#plannerTitle {
    color: #cdd6f4;
    font-size: 18px;
    font-weight: 600;
}
QLabel#todoOpenLabel {
    color: #cdd6f4;
}
QLabel#todoDoneLabel {
    color: #6c7086;
    text-decoration: line-through;
}
QPushButton#todoCheck {
    padding: 4px;
    min-width: 28px;
}
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background: #181825;
    color: #a6adc8;
    padding: 8px 14px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #313244;
    color: #89b4fa;
}
QLabel#memoryTitle {
    color: #cdd6f4;
    font-size: 18px;
    font-weight: 600;
}
QListWidget#memoryList::item {
    padding: 10px;
    margin: 2px 0;
    border-radius: 8px;
}
QLabel#voiceTitle {
    color: #cdd6f4;
    font-size: 18px;
    font-weight: 600;
}
QLabel#voiceStatus {
    color: #89b4fa;
    font-size: 22px;
    font-weight: 600;
    padding: 8px;
}
QLabel#voiceStatus[voiceState="listening"] {
    color: #a6e3a1;
}
QLabel#voiceStatus[voiceState="processing"] {
    color: #f9e2af;
}
QLabel#voiceStatus[voiceState="speaking"] {
    color: #cba6f7;
}
QLabel#voiceStatus[voiceState="error"] {
    color: #f38ba8;
}
QLabel#voiceHint {
    color: #a6adc8;
}
QPushButton#voiceMicButton {
    background-color: #313244;
    border: 2px solid #45475a;
    border-radius: 90px;
    font-size: 15px;
    font-weight: 600;
    min-width: 180px;
    min-height: 180px;
}
QPushButton#voiceMicButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}
QPushButton#voiceMicButton:pressed,
QPushButton#voiceMicButton:checked {
    background-color: #1e3a2f;
    border-color: #a6e3a1;
    color: #a6e3a1;
}
"""
