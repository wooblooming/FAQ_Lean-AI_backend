from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json
import os

# BASE_DIR은 프로젝트의 루트 디렉토리를 나타냄
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 서비스 계정 키 파일 경로 설정: 해당 경로에 서비스 계정 키 파일이 저장되어 있어야 함
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, 'chatbot', 'lean-ai-faq-54a04f14f2f0.json').replace('\\', '/') 
SCOPES = ['https://www.googleapis.com/auth/cloud-platform']

# Google Cloud 서비스 계정 자격 증명 설정
try:
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    print("Service account credentials loaded successfully.")
except Exception as e:
    print(f"Failed to load service account credentials: {str(e)}")

@method_decorator(csrf_exempt, name='dispatch')
class DialogflowRequestView(View):

    def post(self, request, *args, **kwargs):
        try:
            # 클라이언트에서 전송한 JSON 데이터를 파싱
            data = json.loads(request.body)
            user_message = data.get('message')  # 사용자가 입력한 메시지를 가져옴
            print(f"Received user message: {user_message}")

            # Dialogflow CX API 클라이언트 생성
            # api endpoint 설정시 location-id와 일치시켜야 함 
            # location이 global인 경우 api-endpoint 없어도 됨!!
            
            try:
                service = build('dialogflow', 'v3', credentials=credentials, client_options={
                    'api_endpoint': 'https://asia-northeast1-dialogflow.googleapis.com'
                })
                print("Dialogflow CX service created successfully.")
            except Exception as e:
                print(f"Failed to create Dialogflow CX service: {str(e)}")
                return JsonResponse({"error": "Failed to create Dialogflow CX service."}, status=500)

            # 고정된 세션 ID를 사용 (여기서는 'my_fixed_session_id'로 고정)
            session_id = 'my_fixed_session_id'
            print(f"Using session ID: {session_id}")
            
            # Google Cloud 프로젝트 ID 및 위치
            project_id = 'lean-ai-faq'
            location_id = 'asia-northeast1'  # 또는 해당하는 위치 (예: 'us-central1')
            agent_id = '32293af4-f3fd-4102-8416-169801a34840'  # Dialogflow CX 에이전트 ID
            print(f"Using project ID: {project_id}")

            # Dialogflow CX의 detectIntent 메소드 호출
            # 사용자의 메시지를 Dialogflow CX로 전송하여 의도를 감지하고, 응답을 받음
            try:
                session_path = f'projects/{project_id}/locations/{location_id}/agents/{agent_id}/sessions/{session_id}'
                response = service.projects().locations().agents().sessions().detectIntent(
                    session=session_path,
                    body={
                        'queryInput': {
                            'text': {
                                'text': user_message
                            },
                            'languageCode': 'ko' 
                        }
                    }
                ).execute()
                print("Detect intent request sent successfully.")
            except Exception as e:
                print(f"Failed to detect intent: {str(e)}")
                return JsonResponse({"error": "Failed to detect intent."}, status=500)

            # Dialogflow CX의 응답에서 결과(fulfillmentText)를 추출
            try:
                bot_response = response.get('queryResult').get('responseMessages')[0].get('text').get('text')[0]
                print(f"Received bot response: {bot_response}")
            except Exception as e:
                print(f"Failed to parse Dialogflow CX response: {str(e)}")
                return JsonResponse({"error": "Failed to parse Dialogflow CX response."}, status=500)

            # 응답을 JSON 형태로 클라이언트에 반환
            return JsonResponse({"response": bot_response})

        except Exception as e:
            # 오류 발생 시 콘솔에 에러 메시지를 출력하고, 클라이언트에 에러 메시지와 함께 500 상태 코드를 반환
            print(f"Error: {str(e)}")
            return JsonResponse({"error": str(e)}, status=500)

    def get(self, request, *args, **kwargs):
        # GET 요청이 들어올 경우, 잘못된 요청임을 나타내는 405 상태 코드를 반환
        return JsonResponse({"error": "Invalid request method"}, status=405)
