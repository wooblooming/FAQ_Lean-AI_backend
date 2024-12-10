# auth_views.py
# 로그인, 회원가입, 비밀번호 재설정, 계정 비활성화
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.conf import settings
from django.utils.text import slugify
from urllib.parse import quote
from django.utils import timezone 
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
import requests, random, logging, json, os, shutil
from ..models import User, Store, Edit, Menu
from ..serializers import (
    UserSerializer, StoreSerializer, UsernameCheckSerializer, 
    PasswordCheckSerializer
)

# 디버깅을 위한 로거 설정
logger = logging.getLogger('faq')


# User Management APIs
# 회원가입 API
class SignupView(APIView):
    def post(self, request):
        user_data = {
            'username': request.data.get('username'),
            'password': request.data.get('password'),
            'name': request.data.get('name'),
            'dob': request.data.get('dob'),
            'phone': request.data.get('phone'),
            'email': request.data.get('email') if request.data.get('email') else None,
            'marketing': request.data.get('marketing')
        }
        store_data = {
            'store_category': request.data.get('store_category'),
            'store_name': request.data.get('store_name'),
            'store_address': request.data.get('store_address'),
            'slug': slugify(quote(request.data.get('store_name', '')))
        }

        if Store.objects.filter(store_name=store_data['store_name']).exists() or Store.objects.filter(slug=store_data['slug']).exists():
            return Response({'success': False, 'message': '이미 존재하는 스토어 이름 또는 슬러그입니다.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                user_serializer = UserSerializer(data=user_data)
                if not user_serializer.is_valid():
                    return Response({'success': False, 'message': '회원가입 실패', 'errors': user_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

                user = user_serializer.save()

                store_data['user'] = user.user_id
                store_serializer = StoreSerializer(data=store_data)
                if not store_serializer.is_valid():
                    return Response({'success': False, 'message': '스토어 생성 실패', 'errors': store_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

                store_serializer.save()
                return Response({'success': True, 'message': '회원가입 성공'}, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"회원가입 오류: {str(e)}")
            return Response({'success': False, 'message': '서버 오류 발생'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 로그인 API
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        try:
            user = User.objects.get(username=username)
            if check_password(password, user.password):
                refresh = RefreshToken.for_user(user)
                store = user.stores.first()
                if store:
                    return Response({'access': str(refresh.access_token), 'store_id': store.store_id})
                return Response({'error': '등록되지 않은 회원입니다.'}, status=status.HTTP_404_NOT_FOUND)

            return Response({'error': '아이디 또는 비밀번호가 잘못되었습니다.'}, status=status.HTTP_401_UNAUTHORIZED)

        except User.DoesNotExist:
            return Response({'error': '아이디 또는 비밀번호가 잘못되었습니다.'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.error(f"로그인 오류: {str(e)}")
            return Response({'error': '서버 오류 발생'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Other User APIs
# 아이디 중복 검사 API
class UsernameCheckView(APIView):
    def post(self, request):
        serializer = UsernameCheckSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            if User.objects.filter(username=username, is_active=True).exists():
                return Response({'is_duplicate': True, 'message': '이미 사용 중인 사용자 아이디입니다.'}, status=status.HTTP_409_CONFLICT)
            return Response({'is_duplicate': False, 'message': '사용 가능한 사용자 아이디입니다.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 비밀번호 재설정 API
class PasswordResetView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone')
        new_password = request.data.get('new_password')

        if not phone_number or not new_password:
            return Response({'success': False, 'message': '전화번호와 새 비밀번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PasswordCheckSerializer(data={'new_password': new_password})
        if not serializer.is_valid():
            return Response({'success': False, 'message': serializer.errors['new_password'][0]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(phone=phone_number)
            user.password = make_password(new_password)
            user.save()
            return Response({'success': True, 'message': '비밀번호가 성공적으로 변경되었습니다.'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)


# User Verification APIs
# 인증 코드 전송 API
class SendVerificationCodeView(APIView):
    def generate_verification_code(self):
        # 6자리 인증 코드 생성
        return str(random.randint(100000, 999999))

    def post(self, request):
        # 인증 코드 유형에 따라 유저 확인
        user_id = request.data.get('user_id')
        phone_number = request.data.get('phone')
        code_type = request.data.get('type')

        #logger.debug(f"phone_number: {phone_number}, code_type: {code_type}, user_id: {user_id}")

        # 필수 정보가 없으면 오류 반환
        if not phone_number or not code_type or (code_type not in ['findID','signup'] and not user_id):
            return Response({'success': False, 'message': '필수 정보를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        # 인증 코드 유형별 처리
        if code_type == 'findID':
            # 전화번호로 사용자 확인
            try:
                user = User.objects.get(phone=phone_number)
            except User.DoesNotExist:
                return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        elif code_type == 'findPW':
            # 사용자 ID와 전화번호로 사용자 확인
            try:
                user = User.objects.get(username=user_id, phone=phone_number)
            except User.DoesNotExist:
                return Response({'success': False, 'message': '아이디 또는 전화번호가 잘못되었습니다.'}, status=status.HTTP_404_NOT_FOUND)

        elif code_type == 'mypage':
            # mypage에서 전화번호가 이미 등록된 번호인지 확인
            try:
                user = User.objects.get(username=user_id)
                if user.phone == phone_number:
                    return Response({'success': False, 'message': '이미 등록된 핸드폰 번호입니다.'}, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                return Response({'success': False, 'message': '해당 ID로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        else:
            # 회원가입 등 기타 경우: 전화번호 중복 확인
            if User.objects.filter(phone=phone_number, is_active=True).exists():
                return Response({'success': False, 'message': '이미 가입된 전화번호입니다.'}, status=status.HTTP_400_BAD_REQUEST)

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
            'testmode_yn': 'Y',
        }
        response = requests.post('https://apis.aligo.in/send/', data=sms_data)

        logger.debug(verification_code)

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
        user_id = request.data.get('user_id') 

        # 전송된 데이터 로깅
        #logger.debug(f"Received Data - phone_number: {phone_number}, entered_code: {entered_code}, code_type: {code_type}, user_id: {user_id}")

        if not phone_number or not code_type or (code_type not in ['findID', 'signup'] and not user_id):
            return Response({'success': False, 'message': '필수 정보(전화번호, 인증 번호, 사용자 ID)를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f'{code_type}_verification_code_{phone_number}'
        saved_code = cache.get(cache_key)

        if saved_code and saved_code == entered_code:
            if code_type == 'mypage':
                try:
                    # user_id에 해당하는 사용자 검색
                    user = User.objects.get(username=user_id)
                    # 사용자의 전화번호를 입력받은 phone_number로 업데이트
                    user.phone = phone_number
                    user.save()

                    return Response({'success': True, 'message': '인증이 완료되었으며, 전화번호가 업데이트되었습니다.'}, status=status.HTTP_200_OK)
                except User.DoesNotExist:
                    return Response({'success': False, 'message': '해당 ID로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

            elif code_type == 'findID' or code_type == 'findPW':
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




# Deactivate Account APIs
class DeactivateAccountView(APIView):
    """
    사용자를 탈퇴시키는 뷰. 
    사용자 계정을 비활성화하고 개인정보를 익명화 처리.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        계정을 비활성화하고 익명화
        """
        user = request.user

        # 사용자 탈퇴(비활성화 + 익명화) 처리
        self.deactivate_and_anonymize_user(user)

        return Response({"message": "계정이 성공적으로 탈퇴되었습니다."}, status=status.HTTP_200_OK)

    def deactivate_and_anonymize_user(self, user):
        """
        사용자 탈퇴 시 개인정보를 익명화하고 계정을 비활성화.
        """
        # 사용자 정보 익명화
        user.username = f'deleted_user_{user.user_id}'  # 사용자 아이디를 익명화
        user.phone = f'000-0000-0000_{user.user_id}'  # 핸드폰 번호 삭제 또는 익명화
        user.email = f'deleted_{user.user_id}@example.com'  # 이메일을 익명화
        user.name = '탈퇴한 사용자'  # 이름 익명화

        # 사용자 비활성화
        user.is_active = False
        user.deactivated_at = timezone.now()  # 비활성화 시간 기록
        user.save()

        # 사용자가 소유한 가게 및 관련된 데이터 익명화
        self.anonymize_stores(user)

        # 사용자와 관련된 Edit 데이터 익명화
        self.anonymize_edits(user)

        # 사용자 폴더 삭제
        self.delete_user_folder(user)

    def anonymize_stores(self, user):
        """
        탈퇴한 사용자의 가게 데이터를 익명화 처리.
        """
        stores = Store.objects.filter(user=user)
        for store in stores:
            store.store_name = f'익명화된 가게_{store.store_id}'  # 가게 이름 익명화
            store.slug = f'deleted-store_{store.store_id}'  # 간단한 익명화 처리
            store.save()

            # 가게의 메뉴 익명화 처리
            menus = Menu.objects.filter(store=store)
            for menu in menus:
                menu.name = f'익명화된 메뉴_{menu.menu_number}'
                menu.price = 0  # 가격을 0으로 설정하여 의미가 없도록 처리
                menu.image=''
                menu.save()

    
    def anonymize_edits(self, user):
        """
        탈퇴한 사용자의 Edit 데이터를 익명화 처리.
        """
        edits = Edit.objects.filter(user=user)
        for edit in edits:
            edit.title = f'익명화된 제목_{edit.id}'
            edit.content = '익명화된 내용'
            edit.file = None  # 파일 삭제
            edit.save()

    def delete_user_folder(self, user):
        """
        탈퇴한 사용자의 파일이 저장된 폴더를 삭제.
        """

        stores = Store.objects.filter(user=user)
        for store in stores:

            # 업로드 폴더 경로
            store_uploads_folder_path = os.path.join(settings.MEDIA_ROOT, 'uploads', f'store_{store.store_id}')
            # 업로드 폴더 경로 존재하면 삭제
            if os.path.exists(store_uploads_folder_path):
                shutil.rmtree(store_uploads_folder_path)

            # 메뉴 이미지 폴더 경로
            store_menu_images_folder_path = os.path.join(settings.MEDIA_ROOT, 'menu_images', f'store_{store.store_id}')
            # 메뉴 이미지 폴더 경로 존재하면 삭제
            if os.path.exists(store_menu_images_folder_path):
                shutil.rmtree(store_menu_images_folder_path)

            # banner 폴더 경로
            store_banner_folder_path = os.path.join(settings.MEDIA_ROOT, 'banner', f'store_{store.store_id}')
            # banner 폴더 경로 존재하면 삭제
            if os.path.exists(store_banner_folder_path):
                shutil.rmtree(store_banner_folder_path)

            # profile 폴더 경로
            store_profile_folder_path = os.path.join(settings.MEDIA_ROOT, 'profile', f'store_{store.store_id}')
            # profile 폴더 경로 존재하면 삭제
            if os.path.exists(store_profile_folder_path):
                shutil.rmtree(store_profile_folder_path)

            # statistics 폴더 경로
            store_statistics_folder_path = os.path.join(settings.MEDIA_ROOT, 'statistics', f'store_{store.store_id}')
            # statistics 폴더 경로 존재하면 삭제
            if os.path.exists(store_statistics_folder_path):
                shutil.rmtree(store_statistics_folder_path)

            # QR 코드 파일 경로
            store_qrcodes_path = os.path.join(settings.MEDIA_ROOT, 'qrcodes', f'qr_{store.store_id}.png')
            # QR 코드 파일이 존재하면 삭제
            if os.path.exists(store_qrcodes_path):
                os.remove(store_qrcodes_path)

