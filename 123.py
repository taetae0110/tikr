import pygame
import time
from pygame.locals import *
from flask import Flask
from threading import Thread
from werkzeug.serving import run_simple
class GameVariables:
    def __init__(self):
        self.count = 0
        self.target_count = 0
        self.animation_speed = 0.1
        self.animation_duration = 1
        self.start_time = 0
        self.animation_active = False
        self.original_count = 0
game_vars = GameVariables()
app = Flask(__name__)
# 서버 실행 함수
def run_server():
    run_simple('127.0.0.1', 8080, app)  # 80 포트 대신 5000 포트 사용
# 서버 실행 스레드 생성 및 실행
server_thread = Thread(target=run_server)
server_thread.start()
# Flask 라우트 함수
def increase_score(value):
    global game_vars
    game_vars.target_count += value
    game_vars.animation_active = False
    if not game_vars.animation_active:
        game_vars.start_time = time.time()
        game_vars.animation_active = True
        game_vars.original_count = game_vars.count
    return 'Success', 405
@app.route('/a', methods=['POST'])
def increase_score1():
    return increase_score(1)
@app.route('/s', methods=['POST'])
def increase_score11():
    return increase_score(-1)
@app.route('/f', methods=['POST'])
def increase_score10():
    return increase_score(-10)
@app.route('/g', methods=['POST'])
def increase_score1010():
    return increase_score(10)
@app.route('/q', methods=['POST'])
def increase_score100():
    return increase_score(-100)
@app.route('/w', methods=['POST'])
def increase_score100100():
    return increase_score(100)
@app.route('/e', methods=['POST'])
def increase_score1000():
    return increase_score(-1000)
@app.route('/r', methods=['POST'])
def increase_score10001000():
    return increase_score(1000)
@app.route('/z', methods=['POST'])
def increase_score10000():
    return increase_score(-10000)
@app.route('/x', methods=['POST'])
def increase_score1000010000():
    return increase_score(10000)
@app.route('/c', methods=['POST'])
def increase_score20000():
    return increase_score(-20000)
@app.route('/v', methods=['POST'])
def increase_score2000020000():
    return increase_score(20000)    
@app.route('/u', methods=['POST'])
def increase_score5000():
    return increase_score(-5000)
@app.route('/i', methods=['POST'])
def increase_score50005000():
    return increase_score(5000)  
@app.route('/o', methods=['POST'])
def increase_score15000():
    return increase_score(-15000)
@app.route('/p', methods=['POST'])
def increase_score1500015000():
    return increase_score(15000)  
pygame.display.init()
pygame.init()
# 윈도우 설정
WINDOW_WIDTH, WINDOW_HEIGHT = 300, 200
WINDOW_TITLE = '자동먹먹 MADE BY TURN_STUDIO'
BLACK = (0, 0, 0)
pygame.font.init()
font = pygame.font.SysFont("여기어때잘난체2", 26)
window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption(WINDOW_TITLE)
unit = '코인'
# 버튼 사각형 영역 정의
button_rect = pygame.Rect(10, 10, 112, 30)
# 게임 루프
running = True
while running:
    window.fill(BLACK)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            game_vars.original_count = game_vars.count
    # 단위 변경 버튼 클릭 시 처리
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # 마우스 왼쪽 버튼 클릭 시
                if button_rect.collidepoint(event.pos):
                # 단위 변경
                    if unit == '코인':
                        unit = '스탯'
                    elif unit == '스탯':
                        unit = 'coins'
                    elif unit == 'coins':
                        unit = 'stack'
                    elif unit == 'stack':
                        unit = 'COINS'
                    elif unit == 'COINS':
                        unit = 'STACK'
                    elif unit == 'STACK':
                        unit = '코인'
    # 이벤트 처리와 렌더링을 분리
    if game_vars.animation_active:
        elapsed_time = time.time() - game_vars.start_time
        if elapsed_time < game_vars.animation_duration:
            progress = elapsed_time / game_vars.animation_duration
            game_vars.count = int(game_vars.original_count + (game_vars.target_count - game_vars.original_count) * progress)
        else:
            game_vars.count = game_vars.target_count
    pygame.draw.rect(window, (100, 100, 100), button_rect)  # 버튼 그리기
    button_text = font.render('단위변경', True, (255, 255, 255))
    window.blit(button_text, (15, 15))
    # 단위에 따라 표시할 문자열 생성
    text_surface = font.render(f'{game_vars.count}{unit}', True, (255, 255, 255))
    text_rect = text_surface.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
    window.blit(text_surface, text_rect)
    pygame.display.update()  
