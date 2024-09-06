from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
import requests
import random
import logging

# QR 코드 생성에 필요한 라이브러리
import qrcode
import os
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator

# 모델과 시리얼라이저 임포트
from .models import User, Store, Edit
from .serializers import (
    UserSerializer, 
    StoreSerializer, 
    LoginSerializer, 
    UsernameCheckSerializer, 
    PasswordCheckSerializer,
    EditSerializer
)

# 디버깅을 위한 로거 설정
logger = logging.getLogger('faq')

# 회원가입 API 뷰
class SignupView(APIView):
    def post(self, request):
        # 요청 데이터에서 유저와 스토어 정보 가져오기
        user_data = {
            'username': request.data.get('username'),
            'password': request.data.get('password'),
            'name': request.data.get('name'),
            'dob': request.data.get('dob'),
            'phone': request.data.get('phone'),
            'email': request.data.get('email') if request.data.get('email') else None  
        }
        store_data = {
            'store_name': request.data.get('store_name'),
            'store_address': request.data.get('store_address'),
        }

        # 트랜잭션을 사용하여 유저와 스토어 생성
        with transaction.atomic():
            user_serializer = UserSerializer(data=user_data)
            if user_serializer.is_valid():
                user = user_serializer.save()

                store_data['user'] = user.user_id
                store_serializer = StoreSerializer(data=store_data)
                if store_serializer.is_valid():
                    store_serializer.save()
                    return Response({'success': True, 'message': '사용자와 스토어가 성공적으로 생성되었습니다.'}, status=status.HTTP_201_CREATED)
                return Response({'success': False, 'message': '스토어 생성 실패', 'errors': store_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'success': False, 'message': '회원가입에 실패했습니다.', 'errors': user_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

# 로그인 API 뷰
class LoginView(APIView):
    def post(self, request):
        # 사용자명과 비밀번호 가져오기
        username = request.data.get('username')
        password = request.data.get('password')
        
        logger.debug(f"Login attempt for username: {username}")  # 로그인 시도 로깅
        
        try:
            # 사용자 확인
            user = User.objects.get(username=username)
            logger.debug(f"User found for username: {username}")  # 사용자가 발견되었을 때 로깅
            
            # 비밀번호 확인
            if check_password(password, user.password):
                logger.debug(f"Password check passed for username: {username}")  # 비밀번호 검증 통과
                refresh = RefreshToken.for_user(user)
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }, status=status.HTTP_200_OK)
            else:
                logger.warning(f"Password check failed for username: {username}")  # 비밀번호 검증 실패
                return Response({"error": "아이디 또는 비밀번호가 일치하지 않습니다.\n 다시 시도해 주세요."}, status=status.HTTP_401_UNAUTHORIZED)

        except User.DoesNotExist:
            logger.warning(f"User does not exist for username: {username}")  # 사용자가 존재하지 않음
            return Response({"error": "아이디 또는 비밀번호가 일치하지 않습니다.\n 다시 시도해 주세요."}, status=status.HTTP_401_UNAUTHORIZED)
        
        except Exception as e:
            # 기타 예외 처리
            logger.error(f"Unexpected error during login for username: {username}: {str(e)}", exc_info=True)  
            return Response({"error": "로그인 처리 중 문제가 발생했습니다. 관리자에게 문의하세요."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# 사용자명 중복 확인 API
class UsernameCheckView(APIView):
    def post(self, request):
        serializer = UsernameCheckSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']

            if User.objects.filter(username=username).exists():
                return Response({'is_duplicate': True, 'message': '이미 사용 중인 사용자 이름입니다.'}, status=status.HTTP_409_CONFLICT)
            
            return Response({'is_duplicate': False, 'message': '사용 가능한 사용자 이름입니다.'}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 인증 코드 전송 API
class SendVerificationCodeView(APIView):
    def generate_verification_code(self):
        # 6자리 인증 코드 생성
        return str(random.randint(100000, 999999))

    def post(self, request):
        # 인증 코드 유형에 따라 유저 확인
        user_id = request.data.get('id')
        phone_number = request.data.get('phone')
        code_type = request.data.get('type')

        if code_type == 'findID':
            # 전화번호로 사용자 확인
            if not phone_number:
                return Response({'success': False, 'message': '전화번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                user = User.objects.get(phone=phone_number)
            except User.DoesNotExist:
                return Response({'success': False, 'message': '회원 가입시 입력한 전화번호가 아닙니다.'}, status=status.HTTP_404_NOT_FOUND)
            
        elif code_type == 'findPW':
            # 사용자명과 전화번호로 사용자 확인
            if not user_id or not phone_number:
                return Response({'success': False, 'message': '아이디와 전화번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                user = User.objects.get(username=user_id, phone=phone_number)
            except User.DoesNotExist:
                return Response({'success': False, 'message': '회원 가입시 입력한 아이디 또는 전화번호가 아닙니다.'}, status=status.HTTP_404_NOT_FOUND)
            
        else:
            # 회원가입 시 전화번호 중복 확인
            if not phone_number or not code_type:
                return Response({'success': False, 'message': '전화번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)
            if User.objects.filter(phone=phone_number).exists():
                return Response({'success': False, 'message': '이미 가입한 전화번호입니다.'}, status=status.HTTP_400_BAD_REQUEST)

        # 인증 코드 생성 및 캐시에 저장
        verification_code = self.generate_verification_code()
        cache_key = f'{code_type}_verification_code_{phone_number}'
        cache.set(cache_key, verification_code, timeout=300)

        # SMS 전송 API 호출
        sms_data = {
            'key': settings.ALIGO_API_KEY,
            'user_id': settings.ALIGO_USER_ID,
            'sender': settings.ALIGO_SENDER,
            'receiver': phone_number,
            'msg': f'인증 번호는 [{verification_code}]입니다.',
        }
        response = requests.post('https://apis.aligo.in/send/', data=sms_data)

        if response.status_code == 200:
            return Response({'success': True, 'message': '인증 번호가 발송되었습니다.'})
        else:
            return Response({'success': False, 'message': '인증 번호 발송에 실패했습니다.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# 인증 코드 검증 API
class VerifyCodeView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone')
        entered_code = request.data.get('code')
        code_type = request.data.get('type')

        if not phone_number or not entered_code or not code_type:
            return Response({'success': False, 'message': '전화번호, 인증 번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f'{code_type}_verification_code_{phone_number}'
        saved_code = cache.get(cache_key)

        if saved_code and saved_code == entered_code:
            if code_type == 'findID' or code_type == 'findPW':
                try:
                    # 사용자 정보 반환
                    user = User.objects.get(phone=phone_number)
                    return Response({
                        'success': True,
                        'message': '인증이 완료되었습니다.',
                        'user_id': user.username,
                        'user_password': user.password,
                        'date_joined': user.created_at.strftime('%Y.%m.%d')
                    }, status=status.HTTP_200_OK)
                except User.DoesNotExist:
                    return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'success': True, 'message': '회원가입 인증이 완료되었습니다.'}, status=status.HTTP_200_OK)
        else:
            return Response({'success': False, 'message': '인증 번호가 일치하지 않습니다.'}, status=status.HTTP_400_BAD_REQUEST)

# 비밀번호 재설정 API
class PasswordResetView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone')
        new_password = request.data.get('new_password')

        if not phone_number or not new_password:
            return Response({'success': False, 'message': '전화번호와 새 비밀번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        # 비밀번호 정규식 검증
        serializer = PasswordCheckSerializer(data={'new_password': new_password})
        if not serializer.is_valid():
            return Response({'success': False, 'message': serializer.errors['new_password'][0]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 사용자 비밀번호 업데이트
            user = User.objects.get(phone=phone_number)
            user.password = make_password(new_password)
            user.save()

            return Response({'success': True, 'message': '비밀번호가 성공적으로 변경되었습니다.'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

# 유저의 스토어 목록을 반환하는 API
class UserStoresListView(APIView):
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        # 유저와 연관된 모든 스토어 반환
        user = request.user
        stores = Store.objects.filter(user=user)
        serializer = StoreSerializer(stores, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

# 특정 스토어 정보를 업데이트하는 API
class UserStoreDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, store_id):
        # 주어진 store_id와 사용자로 스토어 정보 가져오기
        try:
            store = Store.objects.get(pk=store_id, user=request.user)
        except Store.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        
        # 배너 필드가 빈 문자열인 경우 null로 처리
        if 'banner' in data and data['banner'] == '':
            data['banner'] = None

        serializer = StoreSerializer(store, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 사용자 게시물 등록 API
class EditView(APIView):
       # 이 뷰는 로그인된 사용자만 접근 가능하도록 설정
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # 클라이언트에서 전달받은 데이터를 사용하여 'Edit' 객체를 생성
        # 요청으로부터 사용자의 ID, 제목, 내용, 파일 정보를 추출
        data = {
            'user': request.user.user_id,  # 요청을 보낸 사용자
            'title': request.data.get('title', ''),  # 제목, 없을 경우 빈 문자열
            'content': request.data.get('content', ''),  # 내용, 없을 경우 빈 문자열
            'file': request.FILES.get('file', None)  # 파일, 없을 경우 None
        }

        # EditSerializer를 사용하여 데이터 검증 및 직렬화
        edit_serializer = EditSerializer(data=data)
        
        # 유효성 검증을 통과한 경우 데이터 저장
        if edit_serializer.is_valid():
            edit_serializer.save()
            # 저장된 데이터를 반환하며, HTTP 상태 코드 201(Created) 반환
            return Response(edit_serializer.data, status=status.HTTP_201_CREATED)
        
        # 유효성 검증 실패 시 에러 메시지와 함께 HTTP 상태 코드 400(Bad Request) 반환
        return Response(edit_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 사용자 프로필 조회 및 업데이트 API
class UserProfileView(APIView):
    # 이 뷰는 인증된 사용자만 접근할 수 있도록 설정
    permission_classes = [IsAuthenticated]

    # 유저 프로필 정보를 조회하는 메서드
    def post(self, request):
        # 현재 요청을 보낸 사용자 객체
        user = request.user
        
        try:
            # 현재 사용자의 스토어 정보를 가져옵니다.
            store = Store.objects.get(user=user)
        except Store.DoesNotExist:
            # 스토어가 없는 경우 None으로 설정
            store = None

        # 사용자의 프로필 사진 URL, 없을 경우 빈 문자열 반환
        profile_photo_url = user.profile_photo.url if user.profile_photo else ""

        # 스토어가 있으면 QR 코드 URL, 없으면 빈 문자열 반환
        qr_code_url = store.qr_code if store and store.qr_code else ""

        # 스토어가 있으면 배너 이미지 URL, 없으면 빈 문자열 반환
        banner_url = store.banner.url if store and store.banner else "" 

        # 사용자와 스토어 정보를 응답으로 반환
        return Response({
            'profile_photo': profile_photo_url,  # 사용자 프로필 사진 URL
            'name': user.name,  # 사용자 이름
            'email': user.email,  # 사용자 이메일
            'phone_number': user.phone,  # 사용자 전화번호
            'business_name': store.store_name if store else '',  # 스토어 이름 (없으면 빈 문자열)
            'business_address': store.store_address if store else '',  # 스토어 주소 (없으면 빈 문자열)
            'user_id' : user.username,  # 사용자 아이디
            'qr_code_url': qr_code_url,  # 스토어 QR 코드 URL (없으면 빈 문자열)
            'banner_url': banner_url  # 스토어 배너 이미지 URL (없으면 빈 문자열)
        })
    
    # 유저 프로필을 업데이트하는 메서드
    def put(self, request):
        # 현재 요청을 보낸 사용자 객체
        user = request.user
        # 요청 데이터에서 업데이트할 정보를 추출
        data = request.data

        # 요청 데이터에서 전달된 정보로 사용자의 정보를 업데이트, 없으면 기존 값 유지
        user.name = data.get('name', user.name)  # 이름 업데이트
        user.email = data.get('email', user.email)  # 이메일 업데이트
        user.phone = data.get('phone_number', user.phone)  # 전화번호 업데이트
        user.save()  # 변경 사항을 저장

        try:
            # 현재 사용자와 연결된 스토어 정보 가져오기
            store = Store.objects.get(user=user)
        except Store.DoesNotExist:
            # 스토어가 없으면 None으로 설정
            store = None

        if store:
            # 스토어가 있는 경우, 요청 데이터를 통해 스토어 정보를 업데이트
            store.store_name = data.get('business_name', store.store_name)  # 스토어 이름 업데이트
            store.store_address = data.get('business_address', store.store_address)  # 스토어 주소 업데이트
            store.save()  # 변경 사항을 저장

        # 프로필 업데이트 완료 후 응답
        return Response({
            'message': 'User profile updated successfully',  # 업데이트 성공 메시지
            'profile_photo': user.profile_photo.url if user.profile_photo else "/media/profile_default_img.jpg",  # 프로필 사진 URL
            'name': user.name,  # 업데이트된 사용자 이름
            'email': user.email,  # 업데이트된 이메일
            'phone_number': user.phone,  # 업데이트된 전화번호
            'business_name': store.store_name if store else "",  # 업데이트된 스토어 이름
            'business_address': store.store_address if store else "",  # 업데이트된 스토어 주소
        }, status=status.HTTP_200_OK)  # 성공적으로 업데이트되었음을 나타내는 응답 코드 200 반환


# 프로필 사진 업데이트 API
class UserProfilePhotoUpdateView(APIView):
    permission_classes = [IsAuthenticated]

# POST 요청으로 프로필 사진을 업데이트
    def post(self, request):
        # 프로필 사진 업데이트
        user = request.user
        # 요청 데이터에서 'profile_photo'라는 키로 전달된 프로필 사진 URL을 가져옴
        profile_photo_url = request.data.get('profile_photo')

        # 클라이언트가 빈 문자열("")을 전달한 경우, 프로필 사진을 삭제 (None으로 설정)
        if profile_photo_url == "":
            user.profile_photo = None
        else:
            # 프로필 사진이 정상적으로 전달된 경우, 해당 URL로 프로필 사진을 업데이트
            user.profile_photo = profile_photo_url
        
        # 변경 사항을 데이터베이스에 저장
        user.save() 
        return Response({"message": "프로필 사진이 성공적으로 업데이트되었습니다."}, status=status.HTTP_200_OK)

# 스토어 목록 조회 및 단일 스토어 조회 API
class CustomerStoreView(APIView):

    def get(self, request):
        # 사용자의 타입에 따라 다르게 응답
        user_type = request.query_params.get('type')  # 'owner' 또는 'customer' 받기
        if user_type == 'owner':
            # 소유자라면 로그인된 사용자만 조회 가능
            if not request.user.is_authenticated:
                return Response({'error': '로그인이 필요합니다.'}, status=status.HTTP_401_UNAUTHORIZED)

            # 로그인된 사용자의 모든 스토어 가져오기
            stores = Store.objects.filter(user=request.user)
            stores_data = [
                {
                    'store_id': store.store_id,
                } for store in stores
            ]
            return Response(stores_data, status=status.HTTP_200_OK)
        
        elif user_type == 'customer':
            # 고객일 경우 모든 스토어 목록 제공
            stores = Store.objects.all()  # 모든 스토어 가져오기
            stores_data = [
                {
                    'store_id': store.store_id,
                } for store in stores
            ]
            return Response(stores_data, status=status.HTTP_200_OK)
        
        else:
            return Response({'error': '유효하지 않은 요청입니다.'}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        # 단일 스토어 정보 조회
        user_type = request.data.get('type')  # 'owner' 또는 'customer' 받기
        store_id = request.data.get('store_id')

        if not store_id:
            return Response({'error': '스토어 ID가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

        # 스토어 정보 조회
        try:
            store = Store.objects.get(store_id=store_id)
        except Store.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        store_data = {
            'store_name': store.store_name,
            'store_image': store.banner.url if store.banner else '',
            'store_hours': store.opening_hours,
            'store_address': store.store_address,
            'store_tel': store.store_tel,
            'menu_prices': store.menu_price,
            'agent_id': store.agent_id,
        }

        # 소유자라면 추가적인 정보 제공 가능
        if user_type == 'owner' and not request.user.is_authenticated:
            return Response({'error': '로그인이 필요합니다.'}, status=status.HTTP_401_UNAUTHORIZED)
        
        return Response(store_data, status=status.HTTP_200_OK)

# QR 코드 생성 및 저장 API
class GenerateQrCodeView(APIView):
    permission_classes = [IsAuthenticated]  # 로그인된 사용자만 접근 가능

    @method_decorator(require_POST)
    def post(self, request):
        store_id = request.data.get('store_id')  # 요청에서 store_id 받기

        if not store_id:
            return Response({'error': '스토어 ID가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

        # 주어진 store_id로 스토어 정보 가져오기
        try:
            store = Store.objects.get(store_id=store_id, user=request.user)
        except Store.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=404)

        # QR 코드에 포함할 URL 설정
        qr_url = f'https://mumulai.com/storeIntroduction?id={store.store_id}'

        try:
            # QR 코드 생성
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4
            )
            qr.add_data(qr_url)
            qr.make(fit=True)

            # QR 코드 이미지 저장 경로 설정
            qr_filename = f'qr_{store.store_id}.png'
            qr_directory = os.path.join(settings.MEDIA_ROOT, 'qr_codes')
            qr_path = os.path.join(qr_directory, qr_filename)

            # 디렉토리가 없으면 생성
            os.makedirs(qr_directory, exist_ok=True)

            # QR 코드 이미지 저장
            img = qr.make_image(fill='black', back_color='white')
            img.save(qr_path)

            # 데이터베이스에 QR 코드 URL 저장
            store.qr_code = f'{settings.MEDIA_URL}qr_codes/{qr_filename}'
            store.save()

            return Response({
                'message': 'QR 코드가 성공적으로 생성되었습니다.',
                'qr_code_url': store.qr_code
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': '서버 내부 오류가 발생했습니다. 관리자에게 문의하세요.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# QR 코드 이미지를 반환하는 API
class QrCodeImageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # 사용자의 스토어 정보 가져오기
            store = Store.objects.get(user=request.user)
            if store.qr_code:
                store_name = store.store_name
                qr_code_url = store.qr_code  # QR 코드 URL

                return Response({'store_name': store_name, 'qr_code_image_url': qr_code_url}, status=200)
            else:
                return Response({'qr_code_image_url': None}, status=200)
        except Store.DoesNotExist:
            return Response({'error': 'Store not found'}, status=404)
        except Exception as e:
            return Response({'error': 'An unexpected error occurred.'}, status=500)
