from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import UserSerializer,StoreSerializer , LoginSerializer, UsernameCheckSerializer
from .models import User, Store
from django.core.cache import cache
import requests
import random
from django.conf import settings

class SignupView(APIView):
    def post(self, request):
        # User와 Store 데이터를 받아옵니다.
        user_data = {
            'username': request.data.get('username'),
            'password': request.data.get('password'),
            'name': request.data.get('name'),
            'dob': request.data.get('dob'),
            'phone': request.data.get('phone'),
            'email': request.data.get('email')
        }
        store_data = {
            'store_name': request.data.get('store_name'),
            'store_address': request.data.get('store_address'),
            'user': None  # 나중에 연결할 user를 위한 자리
        }

        # User 생성 및 검증
        user_serializer = UserSerializer(data=user_data)
        if user_serializer.is_valid():
            user = user_serializer.save()
            store_data['user'] = user.user_id  # Store 데이터에 user 연결

            # Store 생성 및 검증
            store_serializer = StoreSerializer(data=store_data)
            if store_serializer.is_valid():
                store_serializer.save()
                return Response({'success': True, 'message': 'User and Store created successfully.'}, status=status.HTTP_201_CREATED)
            user.delete()  # Store 생성 실패 시, 사용자 삭제
            return Response({'success': False, 'message': store_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'success': False, 'message': user_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        
class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']

            try:
                user = User.objects.get(username=username)
                if user.password == password:
                    return Response({'success': True, 'message': 'Login successful'}, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                pass
            
            return Response({'success': False, 'message': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        
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
        return str(random.randint(100000, 999999))

    def post(self, request):
        phone_number = request.data.get('phone')
        code_type = request.data.get('type')  # 'signup' 또는 'findidpw' 값을 가질 수 있음

        if not phone_number or not code_type:
            return Response({'success': False, 'message': '전화번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        verification_code = self.generate_verification_code()
        print(verification_code)

        cache_key = f'{code_type}_verification_code_{phone_number}'
        cache.set(cache_key, verification_code, timeout=300)

        sms_data = {
            'key': settings.ALIGO_API_KEY,
            'user_id': settings.ALIGO_USER_ID,
            'sender': settings.ALIGO_SENDER,
            'receiver': phone_number,
            'msg': f'인증 번호는 [{verification_code}]입니다.',
            'testmode_yn': 'Y',
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
        code_type = request.data.get('type')  # 'signup' 또는 'findidpw' 값을 가질 수 있음

        if not phone_number or not entered_code or not code_type:
            return Response({'success': False, 'message': '전화번호, 인증 번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f'{code_type}_verification_code_{phone_number}'
        saved_code = cache.get(cache_key)

        if saved_code and saved_code == entered_code:
            if code_type == 'findidpw':
                try:
                    user = User.objects.get(phone=phone_number)
                    return Response({
                        'success': True,
                        'message': '인증이 완료되었습니다.',
                        'user_id': user.username,
                        'user_password' : user.password,
                        'date_joined': user.dateJoined.strftime('%Y.%m.%d')
                    }, status=status.HTTP_200_OK)
                except User.DoesNotExist:
                    return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'success': True, 'message': '회원가입 인증이 완료되었습니다.'}, status=status.HTTP_200_OK)
        else:
            return Response({'success': False, 'message': '인증 번호가 일치하지 않습니다.'}, status=status.HTTP_400_BAD_REQUEST)
