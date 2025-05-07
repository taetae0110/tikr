import sys
import os
import time
import random
import json
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs  # URL 쿼리 파라미터 처리용
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                            QVBoxLayout, QHBoxLayout, QWidget, QFrame, QDialog,
                            QListWidget, QLineEdit, QFormLayout, QDoubleSpinBox,
                            QFileDialog, QMessageBox, QListWidgetItem, QTabWidget,
                            QGridLayout, QGroupBox, QSpinBox, QComboBox, QInputDialog,
                            QFontComboBox, QColorDialog, QCheckBox, QTextEdit)
from PyQt5.QtGui import QPixmap, QFont, QPalette, QBrush, QImage, QIcon, QColor
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize

# mcrcon 라이브러리 가져오기 (설치 필요: pip install mcrcon)
try:
    from mcrcon import MCRcon
except ImportError:
    # MCRCON 라이브러리가 설치되지 않은 경우 대체 클래스 제공
    class MCRcon:
        def __init__(self, host, password, port=25575):
            self.host = host
            self.password = password
            self.port = port
        
        def connect(self):
            print(f"MCRCON 라이브러리가 설치되지 않았습니다. pip install mcrcon 명령으로 설치해주세요.")
            print(f"MCRCON 연결 시도: {self.host}:{self.port}")
        
        def command(self, cmd):
            print(f"MCRCON 명령어 실행 (라이브러리 없음): {cmd}")
            return "MCRCON 라이브러리가 설치되지 않아 명령을 실행할 수 없습니다."
        
        def __enter__(self):
            self.connect()
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.disconnect()
        
        def disconnect(self):
            pass

# 기본 폴더 설정
CONFIG_FOLDER = "config"
IMAGE_FOLDER = "images"
DEFAULT_CONFIG_FILE = os.path.join(CONFIG_FOLDER, "profile_1.json")

# 폴더가 없으면 생성
for folder in [CONFIG_FOLDER, IMAGE_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# 룰렛 요청 정보를 저장하는 클래스
class RouletteRequest:
    """룰렛 요청 정보를 저장하는 클래스"""
    def __init__(self, profile_index, nickname=None):
        self.profile_index = profile_index
        self.nickname = nickname  # None이면 닉네임 없음
        self.timestamp = time.time()
    
    def __str__(self):
        nickname_display = self.nickname if self.nickname else "익명"
        return f"요청: 프로필 {self.profile_index+1}, 닉네임: {nickname_display}"

# 신호 클래스 정의 (스레드 간 통신용)
class RouletteSignals(QObject):
    start_roulette = pyqtSignal()
    update_images = pyqtSignal(list)
    finish_animation = pyqtSignal(int)

# 룰렛 항목 클래스
class RouletteItem:
    def __init__(self, name="룰렛 항목", image_path="", command="", probability=25.0, display_text="", webhook_url=""):
        self.name = name
        self.image_path = image_path
        self.command = command
        self.probability = probability
        self.display_text = display_text  # 텍스트 모드에서 표시할 텍스트
        self.multiplier = "X1"  # 배율 기본값
        self.webhook_url = webhook_url  # 추가: 개별 항목의 웹훅 URL
    
    def to_dict(self):
        return {
            'name': self.name,
            'image_path': self.image_path,
            'command': self.command,
            'probability': self.probability,
            'display_text': self.display_text,
            'multiplier': getattr(self, 'multiplier', 'X1'),
            'webhook_url': getattr(self, 'webhook_url', '')  # 추가: 웹훅 URL 저장
        }
    
    @staticmethod
    def from_dict(data):
        item = RouletteItem(
            name=data.get('name', "룰렛 항목"),
            image_path=data.get('image_path', ""),
            command=data.get('command', ""),
            probability=data.get('probability', 25.0),
            display_text=data.get('display_text', ""),
            webhook_url=data.get('webhook_url', "")  # 추가: 웹훅 URL 로드
        )
        item.multiplier = data.get('multiplier', 'X1')
        return item
    
# MCRCON 설정 클래스
class MCRCONSettings:
    def __init__(self, host="localhost", port=25575, password="", enabled=False):
        self.host = host
        self.port = port
        self.password = password
        self.enabled = enabled
    
    def to_dict(self):
        return {
            'host': self.host,
            'port': self.port,
            'password': self.password,
            'enabled': self.enabled
        }
    
    @staticmethod
    def from_dict(data):
        return MCRCONSettings(
            host=data.get('host', 'localhost'),
            port=data.get('port', 25575),
            password=data.get('password', ''),
            enabled=data.get('enabled', False)
        )

# 웹훅 설정 클래스
class WebhookSettings:
    def __init__(self, url="", username="룰렛 봇", avatar_url="", enabled=False):
        self.url = url
        self.username = username
        self.avatar_url = avatar_url
        self.enabled = enabled
    
    def to_dict(self):
        return {
            'url': self.url,
            'username': self.username,
            'avatar_url': self.avatar_url,
            'enabled': self.enabled
        }
    
    @staticmethod
    def from_dict(data):
        return WebhookSettings(
            url=data.get('url', ''),
            username=data.get('username', '룰렛 봇'),
            avatar_url=data.get('avatar_url', ''),
            enabled=data.get('enabled', False)
        )

# 폰트 및 표시 설정 클래스
class DisplaySettings:
    def __init__(self, font_family="Arial", font_size=12, text_color="#ffffff", 
                 use_text_mode=False, title_font_size=16, fixed_slot_count=0):
        self.font_family = font_family
        self.font_size = font_size
        self.text_color = text_color
        self.use_text_mode = use_text_mode
        self.title_font_size = title_font_size
        self.fixed_slot_count = fixed_slot_count  # 0 = 자동, 그 외 = 고정 슬롯 수
    
    def to_dict(self):
        return {
            'font_family': self.font_family,
            'font_size': self.font_size,
            'text_color': self.text_color,
            'use_text_mode': self.use_text_mode,
            'title_font_size': self.title_font_size,
            'fixed_slot_count': self.fixed_slot_count
        }
    
    @staticmethod
    def from_dict(data):
        return DisplaySettings(
            font_family=data.get('font_family', 'Arial'),
            font_size=data.get('font_size', 12),
            text_color=data.get('text_color', '#ffffff'),
            use_text_mode=data.get('use_text_mode', False),
            title_font_size=data.get('title_font_size', 16),
            fixed_slot_count=data.get('fixed_slot_count', 0)
        )

# 프로필 클래스
class Profile:
    def __init__(self, name="프로필 1", items=None, webhook=None, mcrcon=None, display=None):
        self.name = name
        self.items = items if items else []
        self.webhook = webhook if webhook else WebhookSettings()
        self.mcrcon = mcrcon if mcrcon else MCRCONSettings()
        self.display = display if display else DisplaySettings()
        self.rotation_time = 5.0  # 기본 회전 시간
    
    def to_dict(self):
        return {
            'name': self.name,
            'items': [item.to_dict() for item in self.items],
            'webhook': self.webhook.to_dict(),
            'mcrcon': self.mcrcon.to_dict(),
            'display': self.display.to_dict(),
            'rotation_time': self.rotation_time
        }
    
    @staticmethod
    def from_dict(data):
        profile = Profile(
            name=data.get('name', "프로필 1")
        )
        profile.rotation_time = data.get('rotation_time', 5.0)
        
        if 'items' in data:
            profile.items = [RouletteItem.from_dict(item_data) for item_data in data['items']]
        
        if 'webhook' in data:
            profile.webhook = WebhookSettings.from_dict(data['webhook'])
        
        if 'mcrcon' in data:
            profile.mcrcon = MCRCONSettings.from_dict(data['mcrcon'])
            
        if 'display' in data:
            profile.display = DisplaySettings.from_dict(data['display'])
            
        return profile

# 룰렛 항목 편집 대화상자
class ItemEditDialog(QDialog):
    def __init__(self, parent=None, item=None):
        super().__init__(parent)
        self.setWindowTitle("룰렛 항목 편집")
        self.setMinimumWidth(400)
        
        self.item = item if item else RouletteItem()
        
        layout = QVBoxLayout(self)
        
        # 항목 설정 폼
        form_layout = QFormLayout()
        
        # 이름 입력
        self.name_edit = QLineEdit(self.item.name)
        form_layout.addRow("항목 이름:", self.name_edit)
        
        # 표시 텍스트 (텍스트 모드용)
        self.display_text_edit = QTextEdit(self.item.display_text)
        self.display_text_edit.setFixedHeight(60)
        form_layout.addRow("표시 텍스트:", self.display_text_edit)
        
        # 이미지 경로 및 선택 버튼
        image_layout = QHBoxLayout()
        self.image_path_edit = QLineEdit(self.item.image_path)
        self.image_path_edit.setReadOnly(True)
        image_layout.addWidget(self.image_path_edit)
        
        self.browse_button = QPushButton("찾아보기...")
        self.browse_button.clicked.connect(self.browse_image)
        image_layout.addWidget(self.browse_button)
        
        form_layout.addRow("이미지:", image_layout)
        
        # 이미지 미리보기
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedSize(150, 150)
        self.update_preview()
        form_layout.addRow("미리보기:", self.preview)
        
        # 웹훅 URL 입력
        self.webhook_edit = QLineEdit(self.item.webhook_url)
        webhook_tip = "이 항목에만 적용되는 웹훅 URL을 입력하세요. 비워두면 기본 웹훅이 사용됩니다."
        self.webhook_edit.setToolTip(webhook_tip)
        form_layout.addRow("웹훅 URL:", self.webhook_edit)
        
        # 명령어 입력
        self.command_edit = QLineEdit(self.item.command)
        form_layout.addRow("RCON 명령어:", self.command_edit)
        
        # 배율 설정 - 최적화된 코드
        self.multiplier_spin = QSpinBox()
        self.multiplier_spin.setRange(1, 100)  # 1~100회 반복
        self.multiplier_spin.setPrefix("X")
        
        # 현재 배율 값 설정
        try:
            current_value = int(self.item.multiplier.replace('X', ''))
        except (ValueError, AttributeError):
            current_value = 1
        
        self.multiplier_spin.setValue(current_value)
        self.multiplier_spin.setToolTip("MCRCON 명령어와 웹훅 알림의 반복 횟수를 설정합니다.")
        form_layout.addRow("배율(반복 횟수):", self.multiplier_spin)
        
        # 확률 설정
        self.probability_spin = QDoubleSpinBox()
        self.probability_spin.setRange(0.1, 100)
        self.probability_spin.setSuffix("%")
        self.probability_spin.setValue(self.item.probability)
        form_layout.addRow("확률:", self.probability_spin)
        
        layout.addLayout(form_layout)
        
        # 버튼
        buttons_layout = QHBoxLayout()
        self.ok_button = QPushButton("확인")
        self.ok_button.clicked.connect(self.accept)
        
        self.cancel_button = QPushButton("취소")
        self.cancel_button.clicked.connect(self.reject)
        
        buttons_layout.addWidget(self.ok_button)
        buttons_layout.addWidget(self.cancel_button)
        
        layout.addLayout(buttons_layout)
    
    def browse_image(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "이미지 선택", "", "이미지 파일 (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_name:
            self.image_path_edit.setText(file_name)
            self.update_preview()
    
    def update_preview(self):
        if os.path.exists(self.image_path_edit.text()):
            pixmap = QPixmap(self.image_path_edit.text())
            self.preview.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.preview.setText("이미지 없음")
    
    def accept(self):
        self.item.name = self.name_edit.text()
        self.item.image_path = self.image_path_edit.text()
        self.item.command = self.command_edit.text()
        self.item.probability = self.probability_spin.value()
        self.item.display_text = self.display_text_edit.toPlainText()
        self.item.multiplier = f"X{self.multiplier_spin.value()}"
        self.item.webhook_url = self.webhook_edit.text()
        super().accept()

# 웹훅 설정 탭
class WebhookSettingsTab(QWidget):
    def __init__(self, webhook_settings=None):
        super().__init__()
        self.webhook_settings = webhook_settings or WebhookSettings()
        
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        # 웹훅 활성화 체크박스
        self.enabled_check = QCheckBox("웹훅 활성화")
        self.enabled_check.setChecked(self.webhook_settings.enabled)
        form_layout.addRow("", self.enabled_check)
        
        # 웹훅 URL 설정
        webhook_layout = QHBoxLayout()
        self.webhook_url = QLineEdit(self.webhook_settings.url)
        webhook_layout.addWidget(self.webhook_url)
        
        # 웹훅 테스트 버튼
        self.test_webhook = QPushButton("테스트")
        self.test_webhook.clicked.connect(self.test_webhook_url)
        webhook_layout.addWidget(self.test_webhook)
        
        form_layout.addRow("웹훅 URL:", webhook_layout)
        
        # 봇 이름 설정
        self.webhook_username = QLineEdit(self.webhook_settings.username)
        form_layout.addRow("웹훅 사용자명:", self.webhook_username)
        
        # 봇 아바타 URL 설정
        self.webhook_avatar = QLineEdit(self.webhook_settings.avatar_url)
        form_layout.addRow("아바타 URL:", self.webhook_avatar)
        
        layout.addLayout(form_layout)
        layout.addStretch()
    
    def test_webhook_url(self):
        url = self.webhook_url.text()
        if not url:
            QMessageBox.warning(self, "웹훅 테스트", "웹훅 URL을 입력해주세요.")
            return
            
        try:
            payload = {
                "content": "룰렛 웹훅 테스트 메시지입니다.",
                "username": self.webhook_username.text() or "룰렛 봇"
            }
            
            # 아바타 URL이 있으면 추가
            if self.webhook_avatar.text():
                payload["avatar_url"] = self.webhook_avatar.text()
            
            response = requests.post(url, json=payload, timeout=3)
            
            if response.status_code == 204:  # Discord 웹훅 성공 응답코드
                QMessageBox.information(self, "웹훅 테스트", "웹훅 테스트에 성공했습니다!")
            else:
                QMessageBox.warning(self, "웹훅 테스트", f"웹훅 테스트 실패. 응답 코드: {response.status_code}")
        except Exception as e:
            QMessageBox.critical(self, "웹훅 테스트", f"웹훅 테스트 중 오류 발생: {e}")
    
    def save_settings(self):
        self.webhook_settings.url = self.webhook_url.text()
        self.webhook_settings.username = self.webhook_username.text()
        self.webhook_settings.avatar_url = self.webhook_avatar.text()
        self.webhook_settings.enabled = self.enabled_check.isChecked()
        return self.webhook_settings

# MCRCON 설정 탭
class MCRCONSettingsTab(QWidget):
    def __init__(self, mcrcon_settings=None):
        super().__init__()
        self.mcrcon_settings = mcrcon_settings or MCRCONSettings()
        
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        # MCRCON 활성화 체크박스
        self.enabled_check = QCheckBox("MCRCON 활성화")
        self.enabled_check.setChecked(self.mcrcon_settings.enabled)
        form_layout.addRow("", self.enabled_check)
        
        # 서버 호스트 설정
        self.host_edit = QLineEdit(self.mcrcon_settings.host)
        form_layout.addRow("서버 호스트:", self.host_edit)
        
        # 포트 설정
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.mcrcon_settings.port)
        form_layout.addRow("포트:", self.port_spin)
        
        # 비밀번호 설정
        self.password_edit = QLineEdit(self.mcrcon_settings.password)
        self.password_edit.setEchoMode(QLineEdit.Password)
        form_layout.addRow("RCON 비밀번호:", self.password_edit)
        
        # MCRCON 테스트 버튼
        test_layout = QHBoxLayout()
        self.test_button = QPushButton("RCON 연결 테스트")
        self.test_button.clicked.connect(self.test_mcrcon)
        test_layout.addWidget(self.test_button)
        test_layout.addStretch()
        
        layout.addLayout(form_layout)
        layout.addLayout(test_layout)
        layout.addStretch()
        
        # 도움말 추가
        help_label = QLabel(
            "MCRCON은 Minecraft 서버에 원격 명령을 전송하기 위한 프로토콜입니다.\n"
            "사용하려면 server.properties 파일에서 enable-rcon=true와 rcon.password를 설정하세요.")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
    
    def test_mcrcon(self):
        host = self.host_edit.text()
        port = self.port_spin.value()
        password = self.password_edit.text()
        
        if not host or not password:
            QMessageBox.warning(self, "MCRCON 테스트", "호스트와 비밀번호를 모두 입력해주세요.")
            return
        
        try:
            with MCRcon(host, password, port) as mcr:
                response = mcr.command("list")  # 간단한 명령어로 테스트
                QMessageBox.information(self, "MCRCON 테스트", f"RCON 연결 성공!\n응답: {response}")
        except Exception as e:
            QMessageBox.critical(self, "MCRCON 테스트", f"RCON 연결 실패: {e}")
    
    def save_settings(self):
        self.mcrcon_settings.host = self.host_edit.text()
        self.mcrcon_settings.port = self.port_spin.value()
        self.mcrcon_settings.password = self.password_edit.text()
        self.mcrcon_settings.enabled = self.enabled_check.isChecked()
        return self.mcrcon_settings

# 표시 설정 탭 (폰트, 색상 등)
class DisplaySettingsTab(QWidget):
    def __init__(self, display_settings=None):
        super().__init__()
        self.display_settings = display_settings or DisplaySettings()
        
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        # 텍스트 모드 사용 여부
        self.text_mode_check = QCheckBox("텍스트 모드 사용")
        self.text_mode_check.setChecked(self.display_settings.use_text_mode)
        form_layout.addRow("", self.text_mode_check)
        
        # 고정 슬롯 수 설정 추가
        self.fixed_slot_spin = QSpinBox()
        self.fixed_slot_spin.setRange(0, 12)  # 0은 자동, 1~12는 고정 수
        self.fixed_slot_spin.setValue(self.display_settings.fixed_slot_count)
        self.fixed_slot_spin.setSpecialValueText("자동")  # 0일 때는 "자동"으로 표시
        self.fixed_slot_spin.setToolTip("표시할 슬롯의 수를 설정합니다. '자동'은 모든 항목을 표시하고, 숫자는 항상 고정된 수의 슬롯을 표시합니다.")
        form_layout.addRow("표시 슬롯 수:", self.fixed_slot_spin)
        
        # 폰트 선택
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(self.display_settings.font_family))
        form_layout.addRow("폰트:", self.font_combo)
        
        # 일반 텍스트 폰트 크기
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 36)
        self.font_size_spin.setValue(self.display_settings.font_size)
        form_layout.addRow("폰트 크기:", self.font_size_spin)
        
        # 제목 폰트 크기
        self.title_font_size_spin = QSpinBox()
        self.title_font_size_spin.setRange(10, 48)
        self.title_font_size_spin.setValue(self.display_settings.title_font_size)
        form_layout.addRow("제목 폰트 크기:", self.title_font_size_spin)
        
        # 텍스트 색상 선택
        color_layout = QHBoxLayout()
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(24, 24)
        self.color_preview.setStyleSheet(f"background-color: {self.display_settings.text_color}; border: 1px solid black;")
        color_layout.addWidget(self.color_preview)
        
        self.color_button = QPushButton("색상 선택...")
        self.color_button.clicked.connect(self.choose_color)
        color_layout.addWidget(self.color_button)
        color_layout.addStretch()
        
        form_layout.addRow("텍스트 색상:", color_layout)
        
        # 미리보기 섹션
        preview_layout = QVBoxLayout()
        preview_label = QLabel("미리보기:")
        preview_layout.addWidget(preview_label)
        
        self.preview_frame = QFrame()
        self.preview_frame.setFrameStyle(QFrame.StyledPanel)
        self.preview_frame.setMinimumHeight(100)
        
        preview_inner_layout = QVBoxLayout(self.preview_frame)
        self.preview_title = QLabel("항목 제목")
        self.preview_text = QLabel("항목 텍스트 예시입니다. 폰트와 색상이 적용됩니다.")
        self.preview_text.setWordWrap(True)
        
        preview_inner_layout.addWidget(self.preview_title)
        preview_inner_layout.addWidget(self.preview_text)
        
        preview_layout.addWidget(self.preview_frame)
        
        # 설정 변경 시 미리보기 업데이트
        self.font_combo.currentFontChanged.connect(self.update_preview)
        self.font_size_spin.valueChanged.connect(self.update_preview)
        self.title_font_size_spin.valueChanged.connect(self.update_preview)
        
        # 초기 미리보기 업데이트
        self.update_preview()
        
        layout.addLayout(form_layout)
        layout.addLayout(preview_layout)
        layout.addStretch()
    
    def choose_color(self):
        current_color = QColor(self.display_settings.text_color)
        color = QColorDialog.getColor(current_color, self, "텍스트 색상 선택")
        
        if color.isValid():
            self.display_settings.text_color = color.name()
            self.color_preview.setStyleSheet(f"background-color: {color.name()}; border: 1px solid black;")
            self.update_preview()
    
    def update_preview(self):
        # 현재 설정을 기반으로 미리보기 업데이트
        font_family = self.font_combo.currentFont().family()
        font_size = self.font_size_spin.value()
        title_font_size = self.title_font_size_spin.value()
        text_color = self.display_settings.text_color
        
        # 제목 폰트 설정
        title_font = QFont(font_family, title_font_size)
        title_font.setBold(True)
        self.preview_title.setFont(title_font)
        self.preview_title.setStyleSheet(f"color: {text_color};")
        
        # 일반 텍스트 폰트 설정
        text_font = QFont(font_family, font_size)
        self.preview_text.setFont(text_font)
        self.preview_text.setStyleSheet(f"color: {text_color};")
    
    def save_settings(self):
        self.display_settings.font_family = self.font_combo.currentFont().family()
        self.display_settings.font_size = self.font_size_spin.value()
        self.display_settings.title_font_size = self.title_font_size_spin.value()
        self.display_settings.use_text_mode = self.text_mode_check.isChecked()
        self.display_settings.fixed_slot_count = self.fixed_slot_spin.value()  # 고정 슬롯 수 저장
        # text_color는 choose_color 메서드에서 이미 업데이트됨
        return self.display_settings

# 설정 대화상자
class SettingsDialog(QDialog):
    def __init__(self, parent=None, profile=None):
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setMinimumSize(600, 450)
        
        self.profile = profile if profile else Profile()
        
        main_layout = QVBoxLayout(self)
        
        # 탭 위젯 생성
        tabs = QTabWidget()
        
        # 항목 탭
        items_tab = QWidget()
        items_layout = QVBoxLayout(items_tab)
        
        # 항목 목록
        self.items_list = QListWidget()
        self.update_items_list()
        items_layout.addWidget(self.items_list)
        
        # 항목 관리 버튼
        buttons_layout = QHBoxLayout()
        
        self.add_button = QPushButton("추가")
        self.add_button.clicked.connect(self.add_item)
        
        self.edit_button = QPushButton("편집")
        self.edit_button.clicked.connect(self.edit_item)
        
        self.delete_button = QPushButton("삭제")
        self.delete_button.clicked.connect(self.delete_item)
        
        buttons_layout.addWidget(self.add_button)
        buttons_layout.addWidget(self.edit_button)
        buttons_layout.addWidget(self.delete_button)
        
        items_layout.addLayout(buttons_layout)
        
        # 기타 설정
        general_tab = QWidget()
        general_layout = QFormLayout(general_tab)
        
        # 회전 시간 설정
        self.rotation_time = QDoubleSpinBox()
        self.rotation_time.setRange(1, 10)
        self.rotation_time.setValue(self.profile.rotation_time)
        self.rotation_time.setSuffix("초")
        general_layout.addRow("룰렛 회전 시간:", self.rotation_time)
        
        # 웹훅 설정 탭
        webhook_tab = WebhookSettingsTab(self.profile.webhook)
        
        # MCRCON 설정 탭
        mcrcon_tab = MCRCONSettingsTab(self.profile.mcrcon)
        
        # 표시 설정 탭
        display_tab = DisplaySettingsTab(self.profile.display)
        
        # 탭 추가
        tabs.addTab(items_tab, "룰렛 항목")
        tabs.addTab(general_tab, "기본 설정")
        tabs.addTab(webhook_tab, "웹훅 설정")
        tabs.addTab(mcrcon_tab, "MCRCON 설정")
        tabs.addTab(display_tab, "표시 설정")
        
        main_layout.addWidget(tabs)
        
        # 저장/취소 버튼
        save_layout = QHBoxLayout()
        
        self.normalize_button = QPushButton("확률 정규화")
        self.normalize_button.clicked.connect(self.normalize_probabilities)
        
        self.save_button = QPushButton("저장")
        self.save_button.clicked.connect(self.accept)
        
        self.cancel_button = QPushButton("취소")
        self.cancel_button.clicked.connect(self.reject)
        
        save_layout.addWidget(self.normalize_button)
        save_layout.addStretch()
        save_layout.addWidget(self.save_button)
        save_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(save_layout)
        
        # 참조 저장
        self.webhook_tab = webhook_tab
        self.mcrcon_tab = mcrcon_tab
        self.display_tab = display_tab
    
    def update_items_list(self):
        self.items_list.clear()
        for item in self.profile.items:
            list_item = QListWidgetItem(f"{item.name} ({item.probability}%)")
            if os.path.exists(item.image_path):
                icon = QIcon(item.image_path)
                list_item.setIcon(icon)
            self.items_list.addItem(list_item)
    
    def add_item(self):
        dialog = ItemEditDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.profile.items.append(dialog.item)
            self.update_items_list()
    
    def edit_item(self):
        current_row = self.items_list.currentRow()
        if current_row >= 0:
            dialog = ItemEditDialog(self, self.profile.items[current_row])
            if dialog.exec_() == QDialog.Accepted:
                self.profile.items[current_row] = dialog.item
                self.update_items_list()
    
    def delete_item(self):
        current_row = self.items_list.currentRow()
        if current_row >= 0:
            reply = QMessageBox.question(
                self, '항목 삭제', 
                f'"{self.profile.items[current_row].name}" 항목을 삭제하시겠습니까?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                del self.profile.items[current_row]
                self.update_items_list()
    
    def normalize_probabilities(self):
        if not self.profile.items:
            return
            
        total = sum(item.probability for item in self.profile.items)
        if total > 0:
            factor = 100.0 / total
            for item in self.profile.items:
                item.probability = round(item.probability * factor, 2)
            
            self.update_items_list()
            QMessageBox.information(self, "확률 정규화", "모든 항목의 확률 합이 100%가 되도록 조정되었습니다.")
    
    def accept(self):
        # 각 탭에서 설정 저장
        self.profile.rotation_time = self.rotation_time.value()
        self.profile.webhook = self.webhook_tab.save_settings()
        self.profile.mcrcon = self.mcrcon_tab.save_settings()
        self.profile.display = self.display_tab.save_settings()
        super().accept()

# 메인 애플리케이션 클래스
class RouletteApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 윈도우 설정
        self.setWindowTitle("자동룰렛 madeby 턴스튜디오")
        self.setFixedSize(800, 600)
        
        # 초기 상태: 투명 배경, 타이틀 바 없음
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        # 타이틀바 상태 변수
        self.titlebar_visible = False
        
        # 애니메이션 상태 변수 초기화
        self.animation_active = False
        self.selected_index = 0  # 선택된 항목의 인덱스
        
        # 숨김 타이머 변수 추가
        self.hide_timer = None  # 요소 숨기기 타이머
        
        # 프로필 관리
        self.profiles = self.load_profiles()
        self.current_profile_index = 0  # 현재 사용 중인 프로필 인덱스
        self.current_profile = self.profiles[self.current_profile_index] if self.profiles else Profile()
        self.selected_items = []  # 현재 표시 중인 아이템들
        
        # 요청 큐 초기화
        self.request_queue = []  # 대기 중인 룰렛 요청을 저장할 큐
        
        # 신호 객체 초기화
        self.signals = RouletteSignals()
        self.signals.start_roulette.connect(self.spin_roulette)
        self.signals.update_images.connect(self.update_roulette_display)
        self.signals.finish_animation.connect(self.finish_roulette)
        
        # 중앙 위젯 설정
        central_widget = QWidget(self)
        central_widget.setStyleSheet("background-color: transparent;")
        self.setCentralWidget(central_widget)
        
        # 메인 레이아웃
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 프로필 선택 콤보박스
        profile_layout = QHBoxLayout()
        profile_label = QLabel("프로필:")
        profile_label.setStyleSheet("color: white; background-color: transparent;")
        
        self.profile_combo = QComboBox()
        self.profile_combo.setStyleSheet("background-color: rgba(0, 0, 0, 100); color: white;")
        self.profile_combo.setFixedWidth(200)
        self.profile_combo.currentIndexChanged.connect(self.change_profile)
        
        profile_layout.addWidget(profile_label)
        profile_layout.addWidget(self.profile_combo)
        
        # 프로필 관리 버튼
        self.add_profile_button = QPushButton("프로필 추가")
        self.add_profile_button.setFixedSize(100, 30)
        self.add_profile_button.clicked.connect(self.add_profile)
        self.add_profile_button.setStyleSheet("background-color: rgba(0, 0, 0, 100); color: white;")

        self.rename_profile_button = QPushButton("이름변경")
        self.rename_profile_button.setFixedSize(80, 30)
        self.rename_profile_button.clicked.connect(self.rename_profile)
        self.rename_profile_button.setStyleSheet("background-color: rgba(0, 0, 0, 100); color: white;")

        # 링크 복사 버튼 추가
        self.copy_link_button = QPushButton("링크 복사")
        self.copy_link_button.setFixedSize(80, 30)
        self.copy_link_button.clicked.connect(self.copy_profile_link)
        self.copy_link_button.setStyleSheet("background-color: rgba(0, 50, 120, 100); color: white;")

        self.delete_profile_button = QPushButton("프로필 제거")
        self.delete_profile_button.setFixedSize(100, 30)
        self.delete_profile_button.clicked.connect(self.delete_profile)
        self.delete_profile_button.setStyleSheet("background-color: rgba(0, 0, 0, 100); color: white;")

        profile_layout.addWidget(self.add_profile_button)
        profile_layout.addWidget(self.rename_profile_button)
        profile_layout.addWidget(self.copy_link_button)
        profile_layout.addWidget(self.delete_profile_button)
        profile_layout.addStretch()
        
        main_layout.addLayout(profile_layout)
        
        # 지시자(화살표) 추가
        self.indicator = QLabel("", self)
        self.indicator.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.indicator)
        
        # 룰렛 프레임 - 투명 배경
        self.roulette_frame = QFrame()
        self.roulette_frame.setFrameStyle(QFrame.StyledPanel)
        self.roulette_frame.setStyleSheet("background-color: rgba(30, 30, 30, 150); border: 2px solid #444;")
        self.roulette_layout = QHBoxLayout(self.roulette_frame)
        self.roulette_frame.hide()  # 초기에 숨김
        
        # 룰렛 프레임을 메인 레이아웃에 추가
        main_layout.addWidget(self.roulette_frame)
        
        # 플레이스홀더 추가 (버튼 위치 고정용)
        self.placeholder_spacer = QFrame()
        self.placeholder_spacer.setFrameStyle(QFrame.NoFrame)
        self.placeholder_spacer.setStyleSheet("background-color: transparent;")
        self.placeholder_spacer.setMinimumHeight(200)  # 룰렛 프레임과 비슷한 높이로 설정
        main_layout.addWidget(self.placeholder_spacer)
        self.placeholder_spacer.hide()  # 초기에 숨김
        
        # 이미지 라벨 컨테이너
        self.item_widgets = []
        
        # 중간 여백 추가
        spacer = QWidget()
        spacer.setFixedHeight(30)
        spacer.setStyleSheet("background-color: transparent;")
        main_layout.addWidget(spacer)
        
        # 버튼 레이아웃
        button_layout = QHBoxLayout()
        
        # 설정 버튼
        self.settings_button = QPushButton("설정")
        self.settings_button.setFont(QFont("Arial", 14))
        self.settings_button.setStyleSheet("background-color: #3498db; color: white; padding: 10px;")
        self.settings_button.clicked.connect(self.open_settings)
        self.settings_button.setFixedSize(120, 40)
        button_layout.addWidget(self.settings_button)
        
        # 타이틀바 토글 버튼 추가
        self.toggle_titlebar_button = QPushButton("오버레이화 해제")
        self.toggle_titlebar_button.setFont(QFont("Arial", 10))
        self.toggle_titlebar_button.setStyleSheet("background-color: #9b59b6; color: white; padding: 8px;")
        self.toggle_titlebar_button.clicked.connect(self.toggle_titlebar)
        self.toggle_titlebar_button.setFixedSize(120, 40)
        button_layout.addWidget(self.toggle_titlebar_button)
        
        button_layout.addStretch()
        
        # 종료 버튼 - 타이틀바 없을 때 필요
        self.exit_button = QPushButton("X")
        self.exit_button.setFixedSize(30, 30)
        self.exit_button.setStyleSheet("background-color: #e74c3c; color: white;")
        self.exit_button.clicked.connect(self.close)
        button_layout.addWidget(self.exit_button)
        
        # 룰렛 돌리기 버튼
        self.spin_button = QPushButton("룰렛 돌리기")
        self.spin_button.setFont(QFont("Arial", 14))
        self.spin_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px;")
        self.spin_button.clicked.connect(self.spin_roulette)
        self.spin_button.setFixedSize(150, 40)
        button_layout.addWidget(self.spin_button)
        
        main_layout.addLayout(button_layout)
        
        # 프로필 콤보박스 초기화
        self.update_profile_combo()
        
        # 초기 UI 설정
        self.update_roulette_items()
        
        # 마우스 드래그 이벤트를 위한 변수
        self.drag_position = None
        
        # 닉네임 추적
        self._last_nickname = None

    def mousePressEvent(self, event):
    # 타이틀바가 없을 때만 드래그 기능 활성화
        if not self.titlebar_visible and event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        # 타이틀바가 없을 때만 드래그 기능 활성화
        if not self.titlebar_visible and event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None
    
    def update_profile_combo(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for profile in self.profiles:
            self.profile_combo.addItem(profile.name)
        
        # 현재 프로필 선택
        if self.profiles:
            self.profile_combo.setCurrentIndex(self.current_profile_index)
        self.profile_combo.blockSignals(False)
    
    def update_indicator(self, nickname):
        """닉네임 정보를 indicator 라벨에 표시"""
        try:
            # 닉네임이 실제로 의미 있는 값인 경우에만 표시
            if nickname and nickname.strip():
                # 현재 폰트 및 색상 설정 적용
                font = QFont(self.current_profile.display.font_family, 14, QFont.Bold)
                self.indicator.setFont(font)
                
                # 닉네임 설정 및 배경 스타일
                self.indicator.setText(f"{nickname}")
                self.indicator.setStyleSheet(
                    f"color: {self.current_profile.display.text_color}; "
                    f"background-color: rgba(0, 0, 0, 100); "
                    f"padding: 5px; border-radius: 5px; "
                    f"border: 2px solid #3498db;"
                )
                self.indicator.setAlignment(Qt.AlignCenter)
                
                # 표시 효과
                self.indicator.show()
                print(f"인디케이터 업데이트: {nickname}")
                
                # 현재 닉네임 저장
                self._last_nickname = nickname
            else:
                # 닉네임이 없거나 공백만 있으면 숨김
                self.indicator.setText("")
                self.indicator.hide()
                print("닉네임이 없어 인디케이터를 숨깁니다.")
                self._last_nickname = None
        except Exception as e:
            print(f"인디케이터 업데이트 오류: {e}")
    def toggle_titlebar(self):
        """타이틀바 표시/숨김을 토글하는 메서드"""
        try:
            # 현재 위치 저장
            current_pos = self.pos()
            
            # 윈도우 상태 토글
            self.titlebar_visible = not self.titlebar_visible
            
            if self.titlebar_visible:
                # 타이틀바 표시
                self.setWindowFlags(self.windowFlags() & ~Qt.FramelessWindowHint)
                self.toggle_titlebar_button.setText("오버레이화")
                self.exit_button.hide()  # 시스템 종료 버튼이 있으므로 숨김
            else:
                # 타이틀바 숨김
                self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
                self.toggle_titlebar_button.setText("오버레이화 해제")
                self.exit_button.show()  # 종료 버튼이 필요하므로 표시
            
            # 변경사항 적용 및 위치 복원
            self.show()
            self.move(current_pos)
            
            print(f"타이틀바 상태 변경: {'표시' if self.titlebar_visible else '숨김'}")
            
        except Exception as e:
            print(f"타이틀바 토글 오류: {e}")
    
    def hide_elements(self):
        """룰렛 프레임과 인디케이터를 숨기고 플레이스홀더를 표시"""
        try:
            self.roulette_frame.hide()
            self.indicator.setText("")
            self.indicator.hide()
            
            # 플레이스홀더 표시
            self.placeholder_spacer.show()
            
            print("룰렛 종료: 요소가 숨겨지고 플레이스홀더가 표시되었습니다.")
        except Exception as e:
            print(f"요소 숨기기 오류: {e}")

    def load_profiles(self):
        profiles = []
        try:
            # 샘플 이미지 생성 (이미지 없는 경우를 위해)
            sample_image_path = os.path.join(IMAGE_FOLDER, "sample.png")
            if not os.path.exists(sample_image_path):
                try:
                    # 간단한 샘플 이미지 생성
                    from PIL import Image, ImageDraw
                    img = Image.new('RGB', (150, 150), color=(73, 109, 137))
                    d = ImageDraw.Draw(img)
                    d.text((50, 70), "샘플", fill=(255, 255, 255))
                    img.save(sample_image_path)
                    print(f"샘플 이미지 생성됨: {sample_image_path}")
                except ImportError:
                    print("PIL 라이브러리 없음, 샘플 이미지 생성 불가")
            
            # 모든 프로필 설정 파일 찾기
            config_files = [f for f in os.listdir(CONFIG_FOLDER) if f.startswith("profile_") and f.endswith(".json")]
            
            if not config_files:
                # 기본 프로필
                profiles.append(Profile(name="프로필 1", items=[
                    RouletteItem(name="항목 1", probability=25),
                    RouletteItem(name="항목 2", probability=25),
                    RouletteItem(name="항목 3", probability=25),
                    RouletteItem(name="항목 4", probability=25)
                ]))
                return profiles
            
            for config_file in sorted(config_files):
                file_path = os.path.join(CONFIG_FOLDER, config_file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        profile = Profile.from_dict(data)
                        profiles.append(profile)
                    except json.JSONDecodeError:
                        print(f"파일 '{config_file}'의 JSON 형식이 잘못되었습니다.")
        except Exception as e:
            print(f"프로필 로드 오류: {e}")
            # 오류 발생 시 기본 프로필
            profiles.append(Profile(name="프로필 1", items=[
                RouletteItem(name="항목 1", probability=25),
                RouletteItem(name="항목 2", probability=25),
                RouletteItem(name="항목 3", probability=25),
                RouletteItem(name="항목 4", probability=25)
            ]))
        
        return profiles
    
    def save_profiles(self):
        try:
            # 이전 설정 파일 모두 삭제
            for file in os.listdir(CONFIG_FOLDER):
                if file.startswith("profile_") and file.endswith(".json"):
                    os.remove(os.path.join(CONFIG_FOLDER, file))
            
            # 새 설정 파일 저장
            for i, profile in enumerate(self.profiles):
                file_path = os.path.join(CONFIG_FOLDER, f"profile_{i+1}.json")
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"프로필 저장 오류: {e}")
            QMessageBox.critical(self, "저장 오류", f"프로필 저장 중 오류가 발생했습니다: {e}")
    
    def change_profile(self, index):
        if 0 <= index < len(self.profiles) and not self.animation_active:
            self.current_profile_index = index
            self.current_profile = self.profiles[index]
            
            # 링크 복사 버튼 텍스트 업데이트
            profile_number = index + 1
            self.copy_link_button.setToolTip(f"프로필 {profile_number} ({self.current_profile.name})의 링크 복사")
            
            self.update_roulette_items()
    
    def add_profile(self):
        if len(self.profiles) >= 10:
            QMessageBox.warning(self, "프로필 제한", "프로필은 최대 10개까지만 추가할 수 있습니다.")
            return
        
        name, ok = QInputDialog.getText(self, "프로필 추가", "새 프로필 이름:", text=f"프로필 {len(self.profiles)+1}")
        
        if ok and name:
            new_profile = Profile(name=name)
            self.profiles.append(new_profile)
            self.current_profile_index = len(self.profiles) - 1
            self.current_profile = new_profile
            self.update_profile_combo()
            self.update_roulette_items()
            self.save_profiles()
    
    def rename_profile(self):
        if not self.profiles:
            return
            
        current_name = self.current_profile.name
        new_name, ok = QInputDialog.getText(self, "프로필 이름 변경", 
                                          "새 이름:", text=current_name)
        
        if ok and new_name:
            self.current_profile.name = new_name
            self.update_profile_combo()
            self.save_profiles()
    
    def delete_profile(self):
        if not self.profiles or len(self.profiles) <= 1:
            QMessageBox.warning(self, "프로필 삭제 불가", "최소 하나의 프로필은 유지해야 합니다.")
            return
            
        reply = QMessageBox.question(self, "프로필 삭제",
                                    f"'{self.current_profile.name}' 프로필을 삭제하시겠습니까?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            del self.profiles[self.current_profile_index]
            self.current_profile_index = 0
            self.current_profile = self.profiles[0]
            self.update_profile_combo()
            self.update_roulette_items()
            self.save_profiles()
    
    # 최적화된 룰렛 항목 업데이트 메서드
    def update_roulette_items(self):
        try:
            print("룰렛 아이템 업데이트 시작")
            start_time = time.time()
            
            # 레이아웃 초기화
            if hasattr(self, 'roulette_layout'):
                # 기존 아이템 위젯 제거
                for widget in self.item_widgets:
                    self.roulette_layout.removeWidget(widget)
                    widget.setParent(None)  # 명시적으로 부모 관계 제거
                    widget.deleteLater()
                self.item_widgets.clear()
            
            # 가능한 아이템이 없으면 샘플 아이템 추가
            if not self.current_profile.items:
                self.current_profile.items = [
                    RouletteItem(name="항목 1", probability=25),
                    RouletteItem(name="항목 2", probability=25),
                    RouletteItem(name="항목 3", probability=25),
                    RouletteItem(name="항목 4", probability=25)
                ]
            
            # 모든 항목을 표시
            self.selected_items = self.current_profile.items
            item_count = len(self.selected_items)
            print(f"표시할 항목 수: {item_count}")
            
            if item_count == 0:
                self.roulette_frame.hide()
                self.placeholder_spacer.show()  # 플레이스홀더 표시
                print("항목이 없어 룰렛 프레임을 숨깁니다.")
                return
            
            # 플레이스홀더는 숨김
            self.placeholder_spacer.hide()
            
            # 현재 표시 설정 가져오기
            display = self.current_profile.display
            
            # 아이템 크기를 항목 수에 따라 자동 조정
            available_width = self.width() - 40  # 여백 감안
            
            # 아이템 생성을 일괄적으로 처리
            self.create_roulette_items(item_count, available_width, display)
            
            # 마지막에 한 번만 업데이트
            self.roulette_frame.update()
            
            end_time = time.time()
            print(f"룰렛 아이템 업데이트 완료 (소요시간: {end_time - start_time:.3f}초)")
        except Exception as e:
            print(f"룰렛 아이템 업데이트 오류: {e}")

    # 아이템 생성 메서드 - 고정 슬롯 수 지원 추가
    def create_roulette_items(self, item_count, available_width, display):
        # 고정 슬롯 수 확인
        fixed_slot_count = display.fixed_slot_count
        
        # 최소/최대 항목 너비 설정
        max_item_width = 150
        min_item_width = 80
        
        # 항목 수에 따른 크기 계산 (최소 너비 보장)
        if fixed_slot_count > 0:
            # 고정 슬롯 수 사용
            display_count = min(fixed_slot_count, item_count)
            item_width = max(min(available_width // fixed_slot_count, max_item_width), min_item_width)
            print(f"고정 슬롯 수 사용: {fixed_slot_count}개 슬롯")
        else:
            # 자동 (모든 항목 표시)
            display_count = item_count
            item_width = max(min(available_width // item_count, max_item_width), min_item_width)
            print(f"자동 슬롯 수 사용: {item_count}개 항목 모두 표시")
            
        item_height = item_width  # 정사각형 비율 유지
        
        # 폰트 설정
        font_family = display.font_family
        font_size = display.font_size
        title_font_size = display.title_font_size
        text_color = display.text_color
        use_text_mode = display.use_text_mode
        
        # 폰트 크기 자동 조정 (정수형으로 변환)
        adjusted_font_size = int(max(min(font_size, item_width // 8), 8))  # 최소 8pt
        adjusted_title_size = int(max(min(title_font_size, item_width // 6), 10))  # 최소 10pt
        adjusted_name_size = int(max(min(font_size * 0.8, item_width // 10), 6))  # 이름 라벨용
        
        print(f"항목 자동 크기 조정: {item_width}x{item_height}, 폰트: {adjusted_font_size}pt")
        
        # 표시할 항목 선택
        if fixed_slot_count > 0 and fixed_slot_count < item_count:
            # 고정 슬롯 수가 있고, 아이템 수가 그보다 많으면 선택적으로 표시
            center_idx = len(self.selected_items) // 2
            start_idx = max(0, center_idx - (fixed_slot_count // 2))
            end_idx = start_idx + fixed_slot_count
            
            if end_idx > len(self.selected_items):
                end_idx = len(self.selected_items)
                start_idx = max(0, end_idx - fixed_slot_count)
                
            display_items = self.selected_items[start_idx:end_idx]
            print(f"슬롯 제한으로 {len(display_items)}개 항목만 표시 (전체 {item_count}개 중)")
        else:
            # 자동 모드이거나 아이템 수가 충분하지 않으면 모두 표시
            display_items = self.selected_items
        
        # 항목 위젯 생성
        for i, item in enumerate(display_items):
            # 수직 레이아웃 컨테이너
            item_widget = QFrame()
            item_widget.setFrameStyle(QFrame.Box)
            item_widget.setStyleSheet("background-color: rgba(50, 50, 50, 200); border: 1px solid #00AAFF;")
            item_layout = QVBoxLayout(item_widget)
            item_layout.setSpacing(2)  # 레이아웃 내 위젯 간격 줄이기
            item_layout.setContentsMargins(4, 4, 4, 4)  # 여백 줄이기
            
            if use_text_mode:
                # 텍스트 모드
                text_label = QLabel(item.display_text or item.name)
                text_label.setFixedSize(item_width, item_height)
                text_label.setAlignment(Qt.AlignCenter)
                text_label.setWordWrap(True)
                text_label.setStyleSheet(f"color: {text_color}; background-color: rgba(60, 60, 60, 200); border: 1px solid #888;")
                text_label.setFont(QFont(font_family, adjusted_font_size))
                item_layout.addWidget(text_label)
            else:
                # 이미지 모드
                img_label = QLabel()
                img_label.setAlignment(Qt.AlignCenter)
                
                if os.path.exists(item.image_path):
                    pixmap = QPixmap(item.image_path).scaled(
                        item_width, item_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    img_label.setPixmap(pixmap)
                    img_label.setStyleSheet("background-color: rgba(60, 60, 60, 200); border: 1px solid #888;")
                else:
                    # 이미지 없으면 텍스트로
                    img_label.setText(item.name)
                    img_label.setStyleSheet(f"color: {text_color}; background-color: rgba(60, 60, 60, 200); border: 1px solid #888;")
                    img_label.setFont(QFont(font_family, adjusted_font_size))
                
                item_layout.addWidget(img_label)
            
            # 이름 라벨
            name_label = QLabel(item.name)
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setStyleSheet(f"color: {text_color}; background-color: transparent;")
            name_label.setFont(QFont(font_family, adjusted_name_size))
            name_label.setWordWrap(True)
            name_label.setFixedWidth(item_width)
            
            # 배율 라벨
            multiplier_label = QLabel(getattr(item, 'multiplier', 'X1'))
            multiplier_label.setAlignment(Qt.AlignCenter)
            multiplier_label.setStyleSheet(f"color: #FF6B6B; background-color: transparent; font-weight: bold;")
            multiplier_label.setFont(QFont(font_family, adjusted_title_size, QFont.Bold))
            
            item_layout.addWidget(name_label)
            item_layout.setAlignment(name_label, Qt.AlignHCenter)  # 레이블을 수평 가운데 정렬
            item_layout.addWidget(multiplier_label)
            
            self.item_widgets.append(item_widget)
            self.roulette_layout.addWidget(item_widget)
        
    def open_settings(self):
        if self.animation_active:
            return
            
        dialog = SettingsDialog(self, self.current_profile)
        if dialog.exec_() == QDialog.Accepted:
            # 설정값 적용
            self.current_profile = dialog.profile
            self.update_roulette_items()
            self.save_profiles()
    
    def spin_roulette(self):
        if self.animation_active:
            print("이미 애니메이션 실행 중, 요청은 큐에 있습니다.")
            return
        
        # 만약 숨김 타이머가 활성화 상태라면 취소
        if self.hide_timer is not None and self.hide_timer.isActive():
            print("요소 숨기기 타이머 취소됨 - 수동 룰렛 실행")
            self.hide_timer.stop()
            self.hide_timer = None
    
        if not self.current_profile.items:
            print("항목이 없습니다")
            # 큐의 요청을 처리
            if self.request_queue:
                self.request_queue.pop(0)  # 현재 요청 제거
                # 다음 요청이 있으면 처리
                if self.request_queue:
                    QTimer.singleShot(100, self.process_next_request)
            return
                
        print("룰렛 회전 시작")
        
        # 룰렛 프레임이 숨겨져 있으면 표시
        if not self.roulette_frame.isVisible():
            # 최신 항목으로 업데이트
            self.update_roulette_items()  
            self.roulette_frame.show()
            self.placeholder_spacer.hide()  # 플레이스홀더 숨김
        
        # 룰렛이 시작되기 전에 화면 업데이트
        for widget in self.item_widgets:
            if widget:
                # 시작할 때 색상 변경
                widget.setStyleSheet("background-color: rgba(70, 70, 70, 200); border: 2px solid #00aaff;")
        
        # 모든 위젯을 한 번에 업데이트
        self.roulette_frame.update()
        
        self.animation_active = True
        self.spin_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        
        # 애니메이션 시작
        self.start_animation()
    
    def start_animation(self):
        # 새 스레드에서 애니메이션 실행
        animation_thread = threading.Thread(target=self.animate_roulette, daemon=True)
        animation_thread.start()
    
    def animate_roulette(self):
        print("애니메이션 시작")
        
        try:
            # 선택할 항목 결정 (확률 기반)
            selected_item = self.select_item_by_probability()
            if selected_item is None:
                print("선택할 항목이 없습니다.")
                self.spin_button.setEnabled(True)
                self.settings_button.setEnabled(True)
                self.animation_active = False
                return
                
            print(f"선택된 항목: {selected_item.name}")
            
            # 선택된 항목의 인덱스 찾기
            try:
                selected_index = self.current_profile.items.index(selected_item) % len(self.selected_items)
            except ValueError:
                selected_index = random.randint(0, len(self.selected_items)-1)
            
            # 룰렛 회전 시간
            rotation_time = self.current_profile.rotation_time
            start_time = time.time()
            interval = 0.1  # 초기 속도
            
            # 임시 항목 리스트 생성 (회전용)
            temp_items = self.selected_items.copy()
            total_updates = 0
            
            while time.time() - start_time < rotation_time:
                # 아이템 회전
                temp_items = temp_items[1:] + [temp_items[0]]
                
                # 메인 스레드에서 UI 업데이트
                self.signals.update_images.emit(temp_items)
                total_updates += 1
                
                # 속도 점점 느려지게
                progress = (time.time() - start_time) / rotation_time
                interval = 0.1 + progress * 0.3
                time.sleep(interval)
            
            # 최종 결과 통지
            self.signals.finish_animation.emit(selected_index)
            print(f"총 {total_updates}번 업데이트됨, 최종 결과: {selected_item.name}")
        
        except Exception as e:
            print(f"애니메이션 오류: {e}")
            self.signals.finish_animation.emit(-1)
    
    def select_item_by_probability(self):
        """확률에 따라 항목을 선택"""
        if not self.current_profile.items:
            return None
            
        # 확률에 따른 가중치 계산
        weights = [item.probability for item in self.current_profile.items]
        total = sum(weights)
        
        if total <= 0:
            # 모든 확률이 0이면 균등 확률 적용
            return random.choice(self.current_profile.items)
        
        # 0~1 사이의 랜덤 값
        r = random.uniform(0, total)
        cumulative = 0
        
        for item, weight in zip(self.current_profile.items, weights):
            cumulative += weight
            if r <= cumulative:
                return item
        
        # 마지막 항목 반환 (부동소수점 오류 방지)
        return self.current_profile.items[-1]

    def update_roulette_display(self, items):
        """룰렛 UI 업데이트 - 성능 최적화"""
        try:
            # 현재 표시 설정
            display = self.current_profile.display
            font_family = display.font_family
            font_size = display.font_size
            text_color = display.text_color
            use_text_mode = display.use_text_mode
            fixed_slot_count = display.fixed_slot_count
            
            # 고정 슬롯 수가 설정된 경우, 표시할 항목 선택
            if fixed_slot_count > 0 and fixed_slot_count < len(items):
                # 선택된 항목 중심으로 표시 항목 결정
                center_idx = len(items) // 2
                start_idx = max(0, center_idx - (fixed_slot_count // 2))
                end_idx = start_idx + fixed_slot_count
                
                if end_idx > len(items):
                    end_idx = len(items)
                    start_idx = max(0, end_idx - fixed_slot_count)
                
                display_items = items[start_idx:end_idx]
            else:
                display_items = items
            
            # 업데이트 전에 UI 이벤트 처리 일시 중지
            QApplication.setOverrideCursor(Qt.WaitCursor)
            
            # 위젯과 표시 항목의 수가 다를 수 있으므로 최소값 사용
            for i, (widget, item) in enumerate(zip(self.item_widgets, display_items)):
                # 위젯의 자식 찾기 (첫 번째만)
                layout = widget.layout()
                if not layout or layout.count() == 0:
                    continue
                    
                # 첫 번째 자식 (이미지 또는 텍스트 라벨)
                first_child = layout.itemAt(0).widget()
                if not first_child:
                    continue
                    
                if use_text_mode:
                    # 텍스트 모드
                    first_child.setText(item.display_text or item.name)
                else:
                    # 이미지 모드 - 캐시된 이미지 사용
                    image_path = item.image_path
                    if hasattr(item, '_cached_pixmap') and item._cached_pixmap:
                        first_child.setPixmap(item._cached_pixmap)
                    elif os.path.exists(image_path):
                        pixmap = QPixmap(image_path).scaled(
                            150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        # 픽스맵 캐싱
                        item._cached_pixmap = pixmap
                        first_child.setPixmap(pixmap)
                    else:
                        first_child.setText(item.name)
                        
                # 이름 라벨 (두 번째 자식)
                if layout.count() > 1:
                    name_label = layout.itemAt(1).widget()
                    if name_label:
                        name_label.setText(item.name)
                
                # 배율 라벨 (세 번째 자식)
                if layout.count() > 2:
                    multiplier_label = layout.itemAt(2).widget()
                    if multiplier_label:
                        multiplier_label.setText(getattr(item, 'multiplier', 'X1'))
            
            # UI 이벤트 처리 재개
            QApplication.restoreOverrideCursor()
            
            # 부드러운 애니메이션을 위한 필수 이벤트 처리
            QApplication.processEvents()
            
        except Exception as e:
            print(f"UI 업데이트 오류: {e}")
            QApplication.restoreOverrideCursor()
            
    def finish_roulette(self, selected_index):
        """룰렛 애니메이션 종료 및 결과 처리"""
        if selected_index < 0:
            # 오류 발생 또는 항목 없음
            self.spin_button.setEnabled(True)
            self.settings_button.setEnabled(True)
            self.animation_active = False
            self.roulette_frame.hide()
            self.placeholder_spacer.show()  # 플레이스홀더 표시
            return
                
        # 선택된 인덱스 저장
        self.selected_index = selected_index
                
        # 최종 배치 조정 (선택된 아이템이 중앙에 오도록)
        final_items = []
        center_idx = len(self.selected_items) // 2
        
        for i in range(len(self.selected_items)):
            idx = (selected_index - center_idx + i) % len(self.selected_items)
            final_items.append(self.selected_items[idx])
        
        # 최종 UI 업데이트
        self.update_roulette_display(final_items)
        
        # 결과 알림 효과
        fixed_slot_count = self.current_profile.display.fixed_slot_count
        if fixed_slot_count > 0 and fixed_slot_count < len(self.selected_items):
            # 고정 슬롯 모드에서는 항상 중앙 위젯이 선택됨
            center_widget_idx = fixed_slot_count // 2
            if center_widget_idx < len(self.item_widgets):
                selected_widget = self.item_widgets[center_widget_idx]
            else:
                selected_widget = self.item_widgets[0] if self.item_widgets else None
        else:
            # 모든 항목 표시 모드에서는 선택된 항목의 인덱스 사용
            center_idx = len(self.selected_items) // 2
            selected_idx = (selected_index - center_idx) % len(self.item_widgets)
            selected_widget = self.item_widgets[selected_idx] if 0 <= selected_idx < len(self.item_widgets) else None
        
        if selected_widget:
            selected_widget.setStyleSheet("background-color: rgba(100, 150, 100, 200); border: 3px solid gold;")
            selected_widget.update()
        
        # 선택된 항목 처리
        selected_item = self.selected_items[selected_index]
        print(f"최종 선택 항목: {selected_item.name}, 배율: {selected_item.multiplier}")
        
        # MCRCON 명령어 실행
        if self.current_profile.mcrcon.enabled and selected_item.command:
            threading.Thread(target=self.execute_mcrcon_command, 
                        args=(selected_item.command,)).start()
        
        # 웹훅 전송
        if self.current_profile.webhook.enabled:
            threading.Thread(target=self.send_webhook_notification, 
                        args=(selected_item,)).start()
        
        # 버튼 다시 활성화
        self.spin_button.setEnabled(True)
        self.settings_button.setEnabled(True)
        self.animation_active = False
        
        # 다음 요청이 있는지 확인
        has_next_request = len(self.request_queue) > 0
        
        # 다음 요청이 있으면 프레임을 숨기지 않고 1초 후 다음 요청 처리
        if has_next_request:
            print(f"다음 요청 준비 중... (남은 요청: {len(self.request_queue)})")
            QTimer.singleShot(1000, self.process_next_request)
        else:
            # 다음 요청이 없을 때만 4초 후 룰렛 프레임과 인디케이터 숨기기
            if self.hide_timer is not None:
                # 기존에 예약된 타이머가 있다면 취소
                self.hide_timer.stop()
                self.hide_timer = None
            
            # 새로운 타이머 설정 (4초)
            self.hide_timer = QTimer()
            self.hide_timer.setSingleShot(True)
            self.hide_timer.timeout.connect(self.hide_elements)
            self.hide_timer.start(4000)  # 4초로 변경
            print("4초 후 요소를 숨기도록 예약됨")

    def copy_profile_link(self):
        """프로필 링크 복사 (닉네임 매개변수 포함)"""
        # 현재 프로필 인덱스 가져오기 (1-기반 번호로 변환 +1)
        profile_number = self.current_profile_index + 1
        
        # 현재 호스트와 포트 가져오기
        host = "127.0.0.1"
        port = 8080
        
        # URL 생성 (닉네임 매개변수 포함)
        url = f"http://{host}:{port}/r{profile_number}?nickname=사용자닉네임"
        
        # 클립보드에 URL 복사
        clipboard = QApplication.clipboard()
        clipboard.setText(url)
        
        # 사용자에게 알림
        QMessageBox.information(self, "링크 복사", 
                             f"프로필 '{self.current_profile.name}'의 URL이 클립보드에 복사되었습니다:\n{url}\n\n"
                             f"이 URL에서 'nickname=' 부분을 수정하여 사용자 닉네임을 지정할 수 있습니다.")

    def add_roulette_request(self, profile_index, nickname=None):
        """룰렛 요청을 큐에 추가하고 처리"""
        # 최대 큐 크기 제한
        MAX_QUEUE_SIZE = 15
        
        # 만약 숨김 타이머가 활성화 상태라면 취소
        if self.hide_timer is not None and self.hide_timer.isActive():
            print("요소 숨기기 타이머 취소됨 - 새 요청 감지")
            self.hide_timer.stop()
            self.hide_timer = None
        
        # 요청 객체 생성
        request = RouletteRequest(profile_index, nickname)
        
        # 큐가 가득 찼을 때
        if len(self.request_queue) >= MAX_QUEUE_SIZE:
            print(f"요청 큐가 가득 찼습니다. 가장 오래된 요청을 제거합니다. (최대 {MAX_QUEUE_SIZE}개)")
            self.request_queue.pop(0)  # 가장 오래된 요청 제거
        
        # 요청을 큐에 추가
        self.request_queue.append(request)
        queue_size = len(self.request_queue)
        
        # 닉네임이 있으면 로그에 표시, 없으면 익명으로 표시
        nickname_display = nickname if nickname else "익명"
        print(f"룰렛 요청 추가: 프로필 {profile_index+1}, 닉네임: {nickname_display}, 대기 중인 요청: {queue_size}")
        
        # 로그에 현재 시간 추가
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"요청 시간: {current_time}")
        
        # 룰렛이 회전 중이 아니면 바로 실행
        if not self.animation_active:
            self.process_next_request()
    
    def process_next_request(self):
        """큐에서 다음 룰렛 요청을 처리 (같은 사용자의 요청은 연속해서)"""
        if not self.request_queue:
            print("처리할 요청이 없습니다.")
            return
        
        if self.animation_active:
            print("이미 애니메이션 실행 중, 3초 후 다시 시도합니다.")
            QTimer.singleShot(3000, self.process_next_request)
            return
        
        # 직전 요청의 닉네임 기억 (연속성 처리용)
        previous_nickname = self._last_nickname
        
        # 같은 사용자의 요청을 찾아서 우선 처리
        next_index = 0
        if previous_nickname:
            for i, req in enumerate(self.request_queue):
                if req.nickname == previous_nickname:
                    next_index = i
                    break
        
        # 선택된 요청 가져오기
        next_request = self.request_queue.pop(next_index)
        
        profile_index = next_request.profile_index
        nickname = next_request.nickname
        
        # 닉네임이 있으면 로그에 표시, 없으면 '익명'으로 표시
        nickname_display = nickname if nickname else "익명"
        print(f"처리 중인 요청: 프로필 {profile_index+1}, 닉네임: {nickname_display}")
        
        # 해당 프로필로 변경
        if 0 <= profile_index < len(self.profiles):
            if profile_index != self.current_profile_index:
                self.current_profile_index = profile_index
                self.current_profile = self.profiles[profile_index]
                self.profile_combo.setCurrentIndex(profile_index)
                self.update_roulette_items()
        
        # 닉네임 표시
        self.update_indicator(nickname)
        
        # 룰렛 프레임이 숨겨져 있으면 표시
        if not self.roulette_frame.isVisible():
            self.roulette_frame.show()
            self.placeholder_spacer.hide()  # 플레이스홀더 숨김
        
        # 룰렛 시작
        self.spin_roulette()

    def execute_mcrcon_command(self, command):
        """MCRCON 명령어 실행 (배율에 따라 반복 실행)"""
        try:
            mcrcon = self.current_profile.mcrcon
            if not mcrcon.enabled or not command:
                return
            
            # 선택된 항목 가져오기
            selected_item = self.selected_items[self.selected_index]
            
            # 배율(반복 횟수) 가져오기
            multiplier_str = getattr(selected_item, 'multiplier', 'X1')
            try:
                repeat_count = min(int(multiplier_str.replace('X', '')), 50)  # 최대 50회로 제한
            except ValueError:
                repeat_count = 1
            
            print(f"MCRCON 명령어 '{command}' {repeat_count}회 반복 실행 시작")
            
            def execute_commands():
                try:
                    with MCRcon(mcrcon.host, mcrcon.password, mcrcon.port) as mcr:
                        for i in range(repeat_count):
                            if i > 0 and i % 10 == 0:  # 10회마다 잠시 대기
                                time.sleep(0.5)
                            
                            response = mcr.command(command)
                            print(f"MCRCON 명령어 실행 결과 ({i+1}/{repeat_count}): {response}")
                            # 적절한 지연
                            time.sleep(0.1)
                            
                    print(f"MCRCON 명령어 {repeat_count}회 반복 실행 완료")
                except Exception as e:
                    print(f"MCRCON 명령어 실행 오류: {e}")
            
            # 별도 스레드에서 실행
            threading.Thread(target=execute_commands, daemon=True).start()
                
        except Exception as e:
            print(f"MCRCON 명령어 실행 준비 오류: {e}")
            
    def send_webhook_notification(self, item):
        """웹훅 알림 전송 (배율에 따라 반복 전송)"""
        try:
            webhook = self.current_profile.webhook
            
            # 항목별 웹훅 URL이 있으면 해당 URL 사용, 없으면 기본 URL 사용
            webhook_url = item.webhook_url if hasattr(item, 'webhook_url') and item.webhook_url else webhook.url
            
            if not webhook.enabled or not webhook_url:
                return
            
            # 배율(반복 횟수) 가져오기
            multiplier_str = getattr(item, 'multiplier', 'X1')
            try:
                repeat_count = min(int(multiplier_str.replace('X', '')), 30)  # 최대 30회로 제한
            except ValueError:
                repeat_count = 1
                
            print(f"웹훅 알림 {repeat_count}회 반복 전송 시작")
            
            def send_webhooks():
                try:
                    
                    username = webhook.username or "룰렛 봇"
                    
                    for i in range(repeat_count):
                        # 웹훅 메시지 작성
                        payload = {
                            "content": f"룰렛 결과: **{item.name}** (반복 {i+1}/{repeat_count})",
                            "username": username,
                            "embeds": [
                                {
                                    "title": "룰렛 결과",
                                    "description": f"**{item.name}** 항목이 선택되었습니다!",
                                    "color": 5814783,  # 보라색
                                    "fields": [
                                        {
                                            "name": "배율(반복 횟수)",
                                            "value": multiplier_str,
                                            "inline": True
                                        },
                                        {
                                            "name": "확률",
                                            "value": f"{item.probability}%",
                                            "inline": True
                                        }
                                    ],
                                    "footer": {
                                        "text": f"제공: 턴스튜디오의 룰렛 시스템"
                                    }
                                }
                            ]
                        }
                        
                        # 현재 요청한 사용자의 닉네임이 있으면 추가
                        if self._last_nickname:
                            payload["embeds"][0]["fields"].append({
                                "name": "요청자",
                                "value": self._last_nickname,
                                "inline": True
                            })
                        
                        # 명령어가 있다면 추가
                        if item.command:
                            payload["embeds"][0]["fields"].append({
                                "name": "명령어",
                                "value": f"`{item.command}`"
                            })
                        
                        # 아바타 URL 추가
                        if webhook.avatar_url:
                            payload["avatar_url"] = webhook.avatar_url
                        
                        # 웹훅 전송
                        try:
                            response = requests.post(webhook_url, json=payload, timeout=3)
                            
                            if response.status_code != 204:
                                print(f"웹훅 전송 실패 ({i+1}/{repeat_count}): {response.status_code}")
                            else:
                                print(f"웹훅 전송 성공 ({i+1}/{repeat_count})")
                        except requests.exceptions.RequestException as e:
                            print(f"웹훅 요청 오류 ({i+1}/{repeat_count}): {e}")
                        
                        # 지연 시간 관리
                        if i > 0 and i % 5 == 0:  # 5회마다 좀 더 긴 대기
                            time.sleep(1.0)
                        elif i < repeat_count - 1:
                            time.sleep(0.3)
                    
                    print(f"웹훅 알림 {repeat_count}회 반복 전송 완료")
                except Exception as e:
                    print(f"웹훅 전송 처리 오류: {e}")
            
            # 별도 스레드에서 실행
            threading.Thread(target=send_webhooks, daemon=True).start()
                
        except Exception as e:
            print(f"웹훅 전송 준비 오류: {e}")
    
    def closeEvent(self, event):
        """창 닫힐 때 설정 저장"""
        self.save_profiles()
        super().closeEvent(event)

class RouletteHandler(BaseHTTPRequestHandler):
    def extract_profile_and_params(self):
        """URL에서 프로필 번호와 쿼리 파라미터 추출"""
        import re
        from urllib.parse import urlparse, parse_qs
        
        # URL 파싱
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        
        # 경로에서 프로필 번호 추출 (예: /r1 -> 1)
        profile_match = re.match(r'/r(\d+)', parsed_url.path)
        profile_number = int(profile_match.group(1)) if profile_match else None
        
        return profile_number, query_params
    
    def do_GET(self):
        try:
            profile_number, query_params = self.extract_profile_and_params()
            
            if profile_number is not None:
                # 닉네임 파라미터 추출 - 빈 문자열이면 None으로 처리
                nickname = query_params.get('nickname', [''])[0] or None
                
                if hasattr(self.server, 'app') and self.server.app:
                    profile_index = profile_number - 1
                    # 룰렛 요청 추가 (닉네임 포함)
                    self.server.app.add_roulette_request(profile_index, nickname)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                
                response_data = {
                    'status': 'success',
                    'message': '요청이 처리되었습니다.',
                    'nickname': nickname or '익명'
                }
                self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
            else:
                self.send_error(404, "경로를 찾을 수 없습니다")
        except Exception as e:
            print(f"GET 요청 처리 중 오류: {e}")
            self.send_error(500, str(e))
    
    def do_POST(self):
        try:
            profile_number, query_params = self.extract_profile_and_params()
            
            if profile_number is not None:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                
                # 닉네임 파라미터 추출 - 빈 문자열이면 None으로 처리
                nickname = query_params.get('nickname', [''])[0] or None
                
                if hasattr(self.server, 'app') and self.server.app:
                    profile_index = profile_number - 1
                    # 룰렛 요청 추가 (닉네임 포함)
                    self.server.app.add_roulette_request(profile_index, nickname)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                
                response_data = {
                    'status': 'success',
                    'message': '요청이 처리되었습니다.',
                    'nickname': nickname or '익명',
                    'queue_size': len(self.server.app.request_queue) if hasattr(self.server, 'app') else 0
                }
                self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
            else:
                self.send_error(404, "경로를 찾을 수 없습니다")
        except Exception as e:
            print(f"POST 요청 처리 중 오류: {e}")
            self.send_error(500, str(e))
    
    # 로그 출력 방지
    def log_message(self, format, *args):
        return

def start_server(app):
    try:
        server = HTTPServer(('127.0.0.1', 8080), RouletteHandler)
        server.app = app  # 서버에 앱 참조 저장
        
        # 사용 가능한 URL 경로 표시
        profile_count = len(app.profiles)
        print(f"서버가 다음 URL에서 실행 중입니다:")
        print(f"사용자: 턴스튜디오")
        for i in range(profile_count):
            profile_name = app.profiles[i].name
            print(f"프로필 {i+1} ({profile_name}): http://127.0.0.1:8080/r{i+1}")
            print(f"닉네임 지정: http://127.0.0.1:8080/r{i+1}?nickname=사용자이름")
            
        server.serve_forever()
    except OSError as e:
        print(f"서버 실행 중 오류 발생: {e}")
        print("다른 포트를 사용하려면 코드의 포트 번호를 변경하세요.")

def main():
    app = QApplication(sys.argv)
    
    # QTimer import 누락 방지
    from PyQt5.QtCore import QTimer
    
    # 스타일 설정
    app.setStyle('Fusion')
    
    # 디버깅 메시지 출력
    print("룰렛 애플리케이션 시작 중...")
    
    # 메인 윈도우 생성
    window = RouletteApp()
    window.show()
    print("메인 윈도우가 표시되었습니다.")
    
    # HTTP 서버 시작 (별도 스레드에서)
    server_thread = threading.Thread(target=start_server, args=(window,), daemon=True)
    server_thread.start()
    
    # 애플리케이션 실행
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
