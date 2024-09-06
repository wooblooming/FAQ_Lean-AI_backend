import os
import shutil
from datetime import datetime

# Django 프로젝트의 SQLite3 데이터베이스 파일 경로
DATABASE_PATH = '/home/lean-ai/FAQ_PJ/backend/db.sqlite3'  # 실제 SQLite3 파일 경로

# 백업 파일을 저장할 경로
BACKUP_DIR = '/home/lean-ai/FAQ_PJ/backend/backups'  # 백업 파일을 저장할 디렉토리
os.makedirs(BACKUP_DIR, exist_ok=True)

# 백업 파일명 설정 (날짜와 시간 포함)
backup_filename = f"db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
backup_path = os.path.join(BACKUP_DIR, backup_filename)

# 백업 수행
shutil.copy(DATABASE_PATH, backup_path)
print(f"백업 완료: {backup_path}")
