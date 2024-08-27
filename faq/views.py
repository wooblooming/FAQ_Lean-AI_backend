from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import check_password
from .serializers import UserSerializer, StoreSerializer, LoginSerializer, UsernameCheckSerializer, StoreSerializer, EditSerializer
from .models import User, Store, Edit
from django.core.cache import cache
import requests
import random
from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListAPIView
from rest_framework.exceptions import NotAuthenticated
from django.contrib.auth.hashers import make_password


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
        username = request.data.get('username')
        password = request.data.get('password')
        
        try:
            user = User.objects.get(username=username)
            
            if check_password(password, user.password):
                # JWT 토큰 생성
                refresh = RefreshToken.for_user(user)
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }, status=status.HTTP_200_OK)
            else:
                return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        except User.DoesNotExist:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    
class UsernameCheckView(APIView):
    def post(self, request):
        serializer = UsernameCheckSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            if User.objects.filter(username=username).exists():
                return Response({'is_duplicate': True, 'message': 'This username is already taken.'}, status=status.HTTP_409_CONFLICT)
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
                        'date_joined': user.created_at.strftime('%Y.%m.%d')
                    }, status=status.HTTP_200_OK)
                except User.DoesNotExist:
                    return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'success': True, 'message': '회원가입 인증이 완료되었습니다.'}, status=status.HTTP_200_OK)
        else:
            return Response({'success': False, 'message': '인증 번호가 일치하지 않습니다.'}, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone')
        new_password = request.data.get('new_password')

        if not phone_number or not new_password:
            return Response({'success': False, 'message': '전화번호와 새 비밀번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(phone=phone_number)
            user.password = make_password(new_password)
            user.save()

            return Response({'success': True, 'message': '비밀번호가 성공적으로 변경되었습니다.'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

class UserStoresListView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        stores = Store.objects.filter(user=user)
        serializer = StoreSerializer(stores, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class UserStoreDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, store_id):
        try:
            store = Store.objects.get(pk=store_id, user=request.user)
        except Store.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = StoreSerializer(store, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class EditView(APIView):
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        # Edit 데이터를 받아옵니다.
        data = {
            'user': request.user.user_id,  # 현재 요청을 보낸 사용자 ID를 저장
            'title': request.data.get('title', ''),  # 기본값으로 빈 문자열
            'content': request.data.get('content', ''),  # 기본값으로 빈 문자열
            'file': request.data.get('file', None)  # 파일이 없을 수도 있음
        }

        # Edit 생성 및 검증
        edit_serializer = EditSerializer(data=data)
        if edit_serializer.is_valid():
            edit_serializer.save()
            return Response(edit_serializer.data, status=status.HTTP_201_CREATED)
        return Response(edit_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        if user.profile_photo:
            profile_photo_url = request.build_absolute_uri(user.profile_photo.url)
        else:
            # profile_photos 디렉토리 내의 기본 이미지를 정확히 지정
            profile_photo_url = request.build_absolute_uri('/media/profile_photos/user_img.jpg')
        
        return Response({
            'user_id': user.user_id,
            'name': user.name,
            'profile_photo': profile_photo_url,
        })

class UserProfilePhotoUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        profile_photo = request.FILES.get('profile_photo')
        profile_photo_url = request.data.get('profile_photo')  # 문자열 경로도 허용

        if profile_photo:
            user.profile_photo = profile_photo  # 파일로 업로드된 경우
        elif profile_photo_url:
            user.profile_photo = profile_photo_url  # 문자열 경로로 전달된 경우

        if profile_photo or profile_photo_url:
            user.save()
            return Response({"message": "프로필 사진이 성공적으로 업데이트되었습니다."}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "파일이 제공되지 않았습니다."}, status=status.HTTP_400_BAD_REQUEST)
        
class CustomerStoreView(APIView):
    def post(self, request):
        store_id = request.data.get('store_id')
        if not store_id:
            return Response({'error': 'Store ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            store = Store.objects.get(store_id=store_id)  # store_id 필드를 사용하여 매장 조회
        except Store.DoesNotExist:
            return Response({'error': 'Store not found'}, status=status.HTTP_404_NOT_FOUND)
        store_data = {
            'store_name': store.store_name,
            'store_image': store.banner.url if store.banner else '',  # banner 필드 사용
            'store_hours': store.opening_hours,  # opening_hours 필드 사용
            'menu_prices': store.menu_price,  # menu_price 필드 사용
            'agent_id' : store.agent_id,
        }
        return Response(store_data, status=status.HTTP_200_OK)