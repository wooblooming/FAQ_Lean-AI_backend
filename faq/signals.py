# signals.py
import os
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, Edit
import requests, logging
from .excel_processor import process_excel_and_save_to_db  # 엑셀 처리 함수 import

# 디버깅을 위한 로거 설정
logger = logging.getLogger('faq')

@receiver(post_save, sender=User)
def send_notification(sender, instance, created, **kwargs):
    if created:
        logger.debug(f"User {instance.username} created!")  # 디버깅용 로그
        slack_webhook_url = "https://hooks.slack.com/services/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"
        slack_message = {
            "text": f"새로운 사용자 {instance.username}가 가입했습니다!"
        }
        response = requests.post(slack_webhook_url, json=slack_message)

        if response.status_code != 200:
            logger.debug(f"Slack webhook failed: {response.status_code}, {response.text}")


@receiver(post_save, sender=Edit)
def handle_file_upload(sender, instance, created, **kwargs):
    if created and instance.file:
        try:
            file_path = instance.file.path
            # 파일 이름이 '무물_초기_데이터_입력_양식'으로 시작하는지 확인
            if os.path.basename(file_path).startswith('무물_초기_데이터_입력_양식'):
                store_id = instance.user.stores.first().store_id
                process_excel_and_save_to_db(file_path, store_id)
                logger.debug(f"Excel file processed for store_id: {store_id}")
        except Exception as e:
            logger.error(f"Error processing Excel file: {e}")

