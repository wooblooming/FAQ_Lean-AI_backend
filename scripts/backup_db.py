import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MY_SETTINGS_PATH = os.path.join(BASE_DIR, 'my_settings.py')
sys.path.append(os.path.dirname(MY_SETTINGS_PATH))

try:
    from my_settings import DATABASE_PATH, BACKUP_DIR
except ImportError:
    raise ImportError("my_settings.py 파일이 누락되었습니다. 올바르게 설정해 주세요.")

# 백업 디렉토리 생성
os.makedirs(BACKUP_DIR, exist_ok=True)

# 백업 파일명 설정 (날짜와 시간 포함)
backup_filename = f"db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
backup_path = os.path.join(BACKUP_DIR, backup_filename)

# 백업 수행 및 예외 처리
try:
    shutil.copy(DATABASE_PATH, backup_path)
    print(f"백업 완료: {backup_path}")
except FileNotFoundError:
    print("데이터베이스 파일을 찾을 수 없습니다. DATABASE_PATH를 확인하세요.")
except shutil.Error as e:
    print(f"백업 중 오류 발생: {e}")
