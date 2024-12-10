# utils.py
from slack_sdk.webhook import WebhookClient
import logging

logger = logging.getLogger('faq')

def send_slack_notification(message):
    """
    Slack 채널로 메시지를 전송하는 함수.
    """
    from django.conf import settings  # settings에서 SLACK_WEBHOOK_URL 가져오기
    slack_webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', None)
    if not slack_webhook_url:
        logger.error("SLACK_WEBHOOK_URL이 설정되지 않았습니다.")
        return

    try:
        webhook = WebhookClient(slack_webhook_url)
        response = webhook.send(text=message)
        if response.status_code != 200:
            logger.error(f"Slack 메시지 전송 실패: {response.status_code}, {response.body}")
    except Exception as e:
        logger.error(f"Slack 메시지 전송 중 오류 발생: {str(e)}")
