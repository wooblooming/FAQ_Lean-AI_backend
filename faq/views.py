from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import UserSerializer, LoginSerializer, UsernameCheckSerializer
from .models import User
from django.core.cache import cache
import requests
import json
import random
from django.conf import settings

class SignupView(APIView):
    def post(self, request):
        # 클라이언트에서 보낸 데이터를 바탕으로 UserSerializer 인스턴스를 만듭니다.
        serializer = UserSerializer(data=request.data)
        # 데이터가 유효한지 확인합니다.
        if serializer.is_valid():
            # 데이터가 유효하면 저장하고, 성공 응답을 반환합니다.
            serializer.save()
            return Response(
                {'success': True, 'message': 'User created successfully.'},  # 성공 메시지와 함께
                status=status.HTTP_201_CREATED  # HTTP 201 상태 코드를 반환합니다.
            )
        # 데이터가 유효하지 않다면, 오류 메시지를 포함한 응답을 반환합니다.
        return Response(
            {'success': False, 'message': serializer.errors},  # 오류 메시지와 함께
            status=status.HTTP_400_BAD_REQUEST  # HTTP 400 상태 코드를 반환합니다.
        )
        
class LoginView(APIView):
    def post(self, request):
        # 시리얼라이저로 데이터 검증
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']

            # 사용자 존재 및 비밀번호 검증
            try:
                user = User.objects.get(username=username)
                if user.password == password:
                    return Response({'success': True, 'message': 'Login successful'}, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                pass
            
            # 사용자 존재하지 않거나 비밀번호가 틀린 경우
            return Response({'success': False, 'message': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # 시리얼라이저 검증 실패 시
        return Response({'success': False, 'message': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
    
class UsernameCheckView(APIView):
    def post(self, request):
        serializer = UsernameCheckSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            if User.objects.filter(username=username).exists():
                return Response({'is_duplicate': True, 'message': 'This username is already taken.'}, status=status.HTTP_200_OK)
            else:
                return Response({'is_duplicate': False, 'message': 'This username is available.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class SendVerificationCodeView(APIView):
    def generate_verification_code(self):
        """6자리 인증 번호 생성"""
        return str(random.randint(100000, 999999))

    def post(self, request):
        phone_number = request.data.get('phone')

        if not phone_number:
            return Response({'success': False, 'message': '전화번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        # 인증 번호 생성
        verification_code = self.generate_verification_code()
        print(verification_code)  # 테스트용으로 터미널에 출력

        # 인증 번호를 캐시에 저장 (5분간 유효)
        cache.set(f'verification_code_{phone_number}', verification_code, timeout=300)

        # 알리고 API로 SMS 발송
        sms_data = {
            'key': settings.ALIGO_API_KEY,
            'user_id': settings.ALIGO_USER_ID,
            'sender': settings.ALIGO_SENDER,
            'receiver': phone_number,
            'msg': f'회원가입 인증 번호는 [{verification_code}]입니다.',
            'testmode_yn': 'Y',  # 테스트 모드 'Y'로 설정하면 실제로 메시지가 발송되지 않습니다.
        }

        response = requests.post('https://apis.aligo.in/send/', data=sms_data)

        if response.status_code == 200:
            return Response({'success': True, 'message': '인증 번호가 발송되었습니다.'})
        else:
            return Response({'success': False, 'message': '인증 번호 발송에 실패했습니다.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyCodeView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone')
        entered_code = request.data.get('code')

        if not phone_number or not entered_code:
            return Response({'success': False, 'message': '전화번호와 인증 번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        # 저장된 인증 번호 가져오기
        saved_code = cache.get(f'verification_code_{phone_number}')

        if saved_code and saved_code == entered_code:
            return Response({'success': True, 'message': '인증이 완료되었습니다.'})
        else:
            return Response({'success': False, 'message': '인증 번호가 일치하지 않습니다.'}, status=status.HTTP_400_BAD_REQUEST)
