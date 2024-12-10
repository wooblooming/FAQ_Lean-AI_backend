# pdf_process.py (Django 프로젝트 루트 디렉토리에 위치)

import os
import django

# Django 설정 로드
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'faq_backend.settings')
django.setup()

from webhook.views import process_local_pdf

# 로컬 PDF 파일 학습시키기
process_local_pdf()
