import os
import django

# Django 설정 로드
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'faq_backend.settings')
django.setup()

from webhook.utils import create_rag_chain

# RAG 체인 생성
rag_chain = create_rag_chain()

if rag_chain:
    # 질문 예시
    user_question = "소녀가 처음 나올 때, 소녀가 안고있던 꽃이 뭐야?"
    
    print(f"user_question: {user_question}, type: {type(user_question)}")

    try:
        # 질문에 대한 응답을 RAG 체인에서 생성
        response = rag_chain.invoke(user_question)  # 직접 문자열 전달

        # 결과 출력
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error during chain invocation: {e}")
else:
    print("RAG Chain creation failed.")