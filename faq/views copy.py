from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.conf import settings
from django.utils.text import slugify
from urllib.parse import unquote, quote
from django.utils import timezone 
from django.utils.timezone import now
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
import requests, random, logging, json, os, shutil, uuid
from exponent_server_sdk import PushClient, PushMessage
from .merged_csv import merge_csv_files
from .excel_processor import process_excel_and_save_to_db  


# QR 코드 생성에 필요한 라이브러리
import qrcode
import os

# 모델과 시리얼라이저 임포트
from .models import User, Store, Edit, Menu
from .serializers import (
    UserSerializer, 
    StoreSerializer, 
    UsernameCheckSerializer, 
    PasswordCheckSerializer,
    EditSerializer, MenuSerializer
)

# 디버깅을 위한 로거 설정
logger = logging.getLogger('faq')

# 회원가입 API 뷰
class SignupView(APIView):
    def post(self, request):
        #logger.debug("백엔드로 전달된 요청 데이터: %s", request.data)

        # 요청 데이터에서 유저와 스토어 정보 가져오기
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
            'slug': slugify(quote(request.data.get('store_name', '')))  # 한글 인코딩
        }

        #logger.debug("User data: %s", user_data)
        #logger.debug("Store data: %s", store_data)

        # 스토어 이름이나 슬러그가 중복되는지 확인
        if Store.objects.filter(store_name=store_data['store_name']).exists():
            return Response({'success': False, 'message': '이미 존재하는 스토어 이름입니다.'}, status=status.HTTP_400_BAD_REQUEST)
        if Store.objects.filter(slug=store_data['slug']).exists():
            return Response({'success': False, 'message': '이미 존재하는 스토어 슬러그입니다.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                user_serializer = UserSerializer(data=user_data)
                if not user_serializer.is_valid():
                    #logger.debug("User serializer errors: %s", user_serializer.errors)
                    return Response({'success': False, 'message': '회원가입에 실패했습니다.', 'errors': user_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

                user = user_serializer.save()

                # store_data에 user_id 추가
                store_data['user'] = user.user_id
                store_serializer = StoreSerializer(data=store_data)
                if not store_serializer.is_valid():
                    #logger.debug("Store serializer errors: %s", store_serializer.errors)
                    return Response({'success': False, 'message': '스토어 생성 실패', 'errors': store_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

                store_serializer.save()

                return Response({'success': True, 'message': '사용자와 스토어가 성공적으로 생성되었습니다.'}, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error("예기치 않은 오류 발생: %s", str(e))
            return Response({'success': False, 'message': '서버 오류가 발생했습니다. 다시 시도해주세요.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# 로그인 API 뷰
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # 사용자명과 비밀번호 가져오기
        username = request.data.get('username')
        password = request.data.get('password')
        
        #logger.debug(f"Login attempt for username: {username}")  # 로그인 시도 로깅
        
        try:
            # 사용자 확인
            user = User.objects.get(username=username)
            #logger.debug(f"User found for username: {username}")  # 사용자가 발견되었을 때 로깅
            
            # 비밀번호 확인
            if check_password(password, user.password):
                #logger.debug(f"Password check passed for username: {username}")  # 비밀번호 검증 통과
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)

                # 사용자와 연결된 첫 번째 Store 가져오기
                store = user.stores.first()
                if store:
                    store_id = store.store_id
                else:
                    return Response({"error": "등록되지 않은 회원입니다."}, status=status.HTTP_404_NOT_FOUND)
                
                return Response({'access': access_token, 'store_id': store_id})
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

            # 중복 여부를 확인할 때 is_active가 True인 사용자만 확인
            if User.objects.filter(username=username, is_active=True).exists():
                return Response({'is_duplicate': True, 'message': '이미 사용 중인 사용자 아이디입니다.'}, status=status.HTTP_409_CONFLICT)
            
            return Response({'is_duplicate': False, 'message': '사용 가능한 사용자 아이디입니다.'}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



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

        #logger.debug(verification_code)

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


# 사용자 데이터 등록 API
class RegisterDataView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        files = request.FILES.getlist('files') if 'files' in request.FILES else []

        if not files:
            return Response({"error": "파일을 업로드 해주세요."}, status=status.HTTP_400_BAD_REQUEST)

        results = []

        for file in files:
            try:
                # 파일을 임시 저장
                temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads')
                os.makedirs(temp_dir, exist_ok=True)
                file_path = os.path.join(temp_dir, file.name)
                with open(file_path, 'wb') as temp_file:
                    for chunk in file.chunks():
                        temp_file.write(chunk)

                # Store ID, 등록 시간 가져오기
                store_id = request.user.stores.first().store_id
                created_at = now().strftime('%Y-%m-%d %H:%M')
                
                # Excel 처리
                result = process_excel_and_save_to_db(file_path, store_id, request.user, file.name, created_at)
                results.append({"file": file.name, **result})

            except Exception as e:
                logger.error(f"Error processing file: {file.name}, Error: {e}")
                results.append({"file": file.name, "status": "error", "message": str(e)})

        return Response({"results": results}, status=status.HTTP_200_OK)


# 사용자 서비스 요청 API
class RequestServiceView(APIView):
    # 이 뷰는 로그인된 사용자만 접근 가능하도록 설정
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        #logger.debug(f"Request data: {request.data}")
        #logger.debug(f"Request files: {request.FILES}")

        files = request.FILES.getlist('files') if 'files' in request.FILES else []

        # 제목, 내용 또는 파일 중 하나는 있어야 함
        if not request.data.get('title') and not request.data.get('content') and not files:
            return Response({"error": "제목, 내용 또는 파일 중 하나는 반드시 입력해야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 여러 파일을 처리하기 위한 빈 리스트 준비
        saved_data = []

        # 클라이언트에서 전달받은 데이터를 사용하여 'Edit' 객체를 생성
        if files:
            for file in files:
                data = {
                    'user': request.user.user_id,
                    'title': request.data.get('title', ''),
                    'content': request.data.get('content', ''),
                    'file': file  # 각각의 파일을 데이터에 추가
                }

                edit_serializer = EditSerializer(data=data)
                
                if edit_serializer.is_valid():
                    edit_serializer.save()
                    saved_data.append(edit_serializer.data)
                else:
                    #logger.debug(f"에러 메시지 : {edit_serializer.errors}")
                    return Response(edit_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            # 파일이 없을 경우, 제목과 내용만 처리
            data = {
                'user': request.user.user_id,
                'title': request.data.get('title', ''),
                'content': request.data.get('content', '')
            }

            edit_serializer = EditSerializer(data=data)

            if edit_serializer.is_valid():
                edit_serializer.save()
                saved_data.append(edit_serializer.data)
            else:
                #logger.debug(f"에러 메시지 : {edit_serializer.errors}")
                return Response(edit_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(saved_data, status=status.HTTP_201_CREATED)



# 사용자 프로필 조회 및 업데이트 API
class UserProfileView(APIView):
    # 이 뷰는 인증된 사용자만 접근할 수 있도록 설정
    authentication_classes = [JWTAuthentication] 
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

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
            'banner_url': banner_url,  # 스토어 배너 이미지 URL (없으면 빈 문자열)
            'marketing': user.marketing,  # 마케팅 동의 여부 추가
            'store_introduction':store.store_introduction,
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
        user.marketing = data.get('marketing', user.marketing)  # 마케팅 동의 여부 업데이트
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
            'marketing': user.marketing, # 업데이트된 마케팅 상태
            'store_introduction':store.store_introduction,

        }, status=status.HTTP_200_OK)  # 성공적으로 업데이트되었음을 나타내는 응답 코드 200 반환
    
    
# 프로필 사진 업데이트 API
class UserProfilePhotoUpdateView(APIView):
    authentication_classes = [JWTAuthentication] 
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

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
class StoreView(APIView):
    permission_classes = [AllowAny]  # 인증 없이 접근 가능하도록 설정

    def dispatch(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            user_type = data.get('type')  # JSON 본문에서 'type'을 추출합니다.
            #logger.debug(f"[Dispatch] User type received: {user_type}")

            if user_type == 'owner':
                self.authentication_classes = [JWTAuthentication]
                self.permission_classes = [IsAuthenticated]

        except Exception as e:
            logger.error(f"[Dispatch] Error parsing request body: {e}")

        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        #logger.debug("[POST] Request received for StoreView")
        try:
            # 요청에서 'type', 'slug', 'store_id' 가져오기
            data = json.loads(request.body)
            slug = data.get('slug')
            store_id = data.get('store_id')

            #logger.debug(f"[POST] Data received - slug: {slug}, store_id: {store_id}")

            if store_id:
                # store_id가 있을 경우 이를 기준으로 검색
                #logger.debug(f"[POST] Searching store by store_id: {store_id}")
                store = Store.objects.get(store_id=store_id)
            elif slug:
                # slug가 있을 경우 이를 기준으로 검색
                #logger.debug(f"[POST] Searching store by slug: {slug}")
                store = Store.objects.get(slug=slug)
            else:
                # store_id와 slug 둘 다 없을 경우 에러 반환
                logger.warning("[POST] store_id and slug are both missing in the request")
                return Response({"error": "store_id 또는 slug가 제공되지 않았습니다."}, status=status.HTTP_400_BAD_REQUEST)

            # Store 데이터를 직렬화
            #logger.debug(f"[POST] Store found: {store}")
            store_data = StoreSerializer(store).data

            # 응답 데이터 생성
            response_data = {
                "store": store_data
            }
            #logger.debug(f"[POST] Response data: {response_data}")
            return Response(response_data, status=status.HTTP_200_OK)

        except Store.DoesNotExist:
            # Store를 찾지 못한 경우
            error_message = f"Store not found for {'store_id: ' + str(store_id) if store_id else 'slug: ' + str(slug)}"
            logger.error(error_message)
            return Response({"error": "해당 매장 정보를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        except json.JSONDecodeError as e:
            logger.error(f"[POST] JSON decoding error: {e}")
            return Response({"error": "잘못된 요청 데이터 형식입니다."}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # 기타 서버 에러 처리
            logger.error(f"[POST] Server error occurred: {str(e)}")
            return Response({"error": "서버 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class GenerateQrCodeView(APIView):
    authentication_classes = [JWTAuthentication] 
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        store_id = request.data.get('store_id')  # 요청에서 store_id 받기

        if not store_id:
            return Response({'error': '스토어 ID가 필요합니다.'}, status=400)

        # 주어진 store_id로 스토어 정보 가져오기
        try:
            store = Store.objects.get(store_id=store_id, user=request.user)
        except Store.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=404)

        # QR 코드에 포함할 URL 설정
        qr_url = f'https://mumulai.com/storeIntroduction/{store.slug}'

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
            qr_filename = f'qr_{store_id}.png'
            qr_directory = os.path.join(settings.MEDIA_ROOT, 'qr_codes')  # 상대 경로에서 앞에 '/' 제거
            qr_path = os.path.join(qr_directory, qr_filename)

            # 디렉토리가 없으면 생성
            if not os.path.exists(qr_directory):
                os.makedirs(qr_directory)

            # QR 코드 이미지 저장
            img = qr.make_image(fill='black', back_color='white')
            img.save(qr_path)

            # 데이터베이스에 QR 코드 경로를 저장 (앞에 '/'를 추가하여 절대 경로처럼 보이게 함)
            store.qr_code = f'/media/qr_codes/{qr_filename}'
            store.save()

            # 로그 출력
            #logger.debug(f"Generated QR Code URL (store.qr_code): {store.qr_code}")
            #logger.debug(f"QR Content URL (qr_url): {qr_url}")

            return Response({
                'message': 'QR 코드가 성공적으로 생성되었습니다.',
                'qr_code_url': store.qr_code,  # 저장된 경로 반환
                'qr_content_url': qr_url  # QR 코드에 인코딩된 실제 URL 반환
            }, status=201)
        except Exception as e:
            logger.error(f"QR 코드 생성 중 오류 발생: {e}")
            return Response({'error': '서버 내부 오류가 발생했습니다. 관리자에게 문의하세요.'}, status=500)

# QR 코드 이미지를 반환하는 API
class QrCodeImageView(APIView):
    authentication_classes = [JWTAuthentication] 
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        try:
            # 사용자의 스토어 정보 가져오기
            store = Store.objects.get(user=request.user)

            if store.qr_code:
                store_name = store.store_name

                # store.qr_code에 중복된 /media/가 포함되었는지 확인
                qr_code_path = store.qr_code.lstrip('/')  # 앞의 '/' 제거
                if qr_code_path.startswith('media/'):
                    qr_code_url = request.build_absolute_uri(f'/{qr_code_path}')
                else:
                    qr_code_url = request.build_absolute_uri(settings.MEDIA_URL + qr_code_path)

                # QR 코드에 인코딩된 실제 URL 생성
                qr_content_url = f'https://mumulai.com/storeIntroduction/{store.slug}'

                return Response({
                    'store_name': store_name,
                    'qr_code_image_url': qr_code_url,
                    'qr_content_url': qr_content_url
                }, status=200)
            else:
                return Response({'qr_code_image_url': None}, status=200)

        except Store.DoesNotExist:
            return Response({'error': 'Store not found'}, status=404)
        except Exception as e:
            return Response({'error': 'An unexpected error occurred.'}, status=500)



# Store 모델의 menu_price 필드를 업데이트하는 헬퍼 함수
def update_menu_price_field(store):
    menus = Menu.objects.filter(store=store)
    #logger.debug(f'메뉴 데이터 : {menus}')
    # 메뉴의 이미지, 이름, 가격, 카테고리를 리스트 형식으로 저장
    menu_price_data = [
        {
            'name': menu.name,
            'price': float(menu.price),
            'category': menu.category,
            'image': str(menu.image.url) if menu.image else None,  # 이미지가 있을 경우 URL로 변환
            'allergy': menu.allergy if menu.allergy is not None else ""  # 기본값 처리
        }
        for menu in menus
    ]
    # menu_price 필드를 JSON 문자열로 저장
    store.menu_price = json.dumps(menu_price_data, ensure_ascii=False)
    store.save()

# 메뉴 상세 조회, 수정 및 삭제 API
class MenuListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """
        POST 요청의 action과 type 파라미터에 따라 권한을 설정.
        'view' 액션 및 'customer' 타입의 경우 인증 없이 접근 가능하도록 설정.
        """
        if self.request.method == 'POST':
            action = self.request.data.get('action')
            type = self.request.data.get('type')
            
            # action이 'view'이고 type이 'customer'인 경우 인증 불필요
            if action == 'view' and type == 'customer':
                return []
        
        # 그 외의 경우는 기본 권한 설정
        return super().get_permissions()


    def post(self, request):
        """
        POST 요청을 처리하여 메뉴를 조회, 생성, 수정, 삭제 또는 카테고리 보기.
        요청 데이터의 'action'에 따라 적절한 메서드를 호출하여 처리.
        """
        action = request.data.get('action')  # 'create', 'update', 'delete', 'view', 'view_category'

        # 각 action에 따라 적절한 메서드를 호출
        if action == 'view':
            slug = request.data.get('slug')
            type_ = request.data.get('type')  # type을 받음, 기본값은 'owner'
            return self.view_menus(request, slug, type_)
        
        if action == 'view_category':  
            slug = request.data.get('slug')
            return self.view_category(request, slug)

        if action == 'delete':
            menus = request.data.get('menus', [])
            return self.delete_menus(request, menus)

        # 'create'와 'update' 요청 처리
        menus = self.extract_menus_from_request(request, action)
        if not menus:
            return Response({'error': '메뉴 데이터가 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)

        if action == 'create':
            return self.create_menus(request, menus)
        elif action == 'update':
            return self.update_menus(request, menus)

        return Response({'error': '유효하지 않은 요청입니다.'}, status=status.HTTP_400_BAD_REQUEST)

    def extract_menus_from_request(self, request, action):
        """
        요청에서 메뉴 데이터를 추출하고 단일 또는 다중 메뉴를 처리합니다.
        """
        #logger.debug(f"요청 데이터: {request.data}")
        #logger.debug(f"요청 파일: {request.FILES}")

        # 단일 메뉴와 다중 메뉴 처리
        menus = []

        if 'slug' in request.data:  # 단일 메뉴 처리
            menu_data = {
                'slug': request.data.get('slug'),
                'name': request.data.get('name'),
                'price': int(request.data.get('price', 0)),
                'category': request.data.get('category'),
                'image': request.FILES.get('image')
            }
            # 수정 요청일 경우에만 menu_number 추가
            if action == 'update':
                menu_data['menu_number'] = request.data.get('menu_number')
            menus.append(menu_data)

        else:  # 다중 메뉴 처리
            index = 0
            while f'menus[{index}][slug]' in request.data:
                menu_data = {
                    'slug': request.data.get(f'menus[{index}][slug]'),
                    'name': request.data.get(f'menus[{index}][name]'),
                    'price': int(request.data.get(f'menus[{index}][price]', 0)),
                    'category': request.data.get(f'menus[{index}][category]'),
                    'image': request.FILES.get(f'menus[{index}][image]')
                }
                # 수정 요청일 경우에만 menu_number 추가
                if action == 'update':
                    menu_data['menu_number'] = request.data.get(f'menus[{index}][menu_number]')
                
                menus.append(menu_data)
                index += 1 # 메뉴 인덱스를 증가시켜 반복 처리

        if not menus:
            logger.error(f"메뉴 데이터가 없습니다. 요청 데이터: {request.data}")
            return None

        #logger.debug(f"추출된 메뉴 데이터: {menus}")
        return menus

    def create_menus(self, request, menus):
        """
        메뉴 생성 
        """
        created_menus = []

        #logger.debug(f"create : {request.data}")

        with transaction.atomic():  # 트랜잭션 범위 설정
            for menu_data in menus:
                store_slug = unquote(menu_data.get('slug'))
                try:
                    store = Store.objects.get(slug=store_slug, user=request.user)
                except Store.DoesNotExist:
                    return Response(
                        {'error': f'{store_slug}에 해당하는 스토어를 찾을 수 없습니다.'},
                        status=status.HTTP_404_NOT_FOUND
                    )

                last_menu = Menu.objects.filter(store=store).order_by('-menu_number').first()
                new_menu_number = last_menu.menu_number + 1 if last_menu else 1
                #logger.debug(f"New menu_number: {new_menu_number} for store: {store_slug}")

                menu_data['store'] = store.store_id
                menu_data['menu_number'] = new_menu_number

                serializer = MenuSerializer(data=menu_data)
                if serializer.is_valid():
                    #logger.debug("Serializer is valid, saving the menu")
                    menu = serializer.save()
                    #logger.debug(f"Menu saved: {menu}")
                    created_menus.append(serializer.data)
                else:
                    #logger.debug(f"Menu serializer errors: {serializer.errors}")
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Store의 menu_price 필드 업데이트
            update_menu_price_field(store)

        return Response({'created_menus': created_menus}, status=status.HTTP_201_CREATED)

    
    def update_menus(self, request, menus):
        """
        메뉴 수정
        """
        updated_menus = []

        for menu_data in menus:
            store_slug = unquote(menu_data.get('slug'))
            try:
                store = Store.objects.get(slug=store_slug, user=request.user)
            except Store.DoesNotExist:
                return Response(
                    {'error': f'{store_slug}에 해당하는 스토어를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            menu_number = menu_data.get('menu_number')
            try:
                menu = Menu.objects.get(store=store, menu_number=menu_number)
            except Menu.DoesNotExist:
                return Response(
                    {'error': f'{menu_number}에 해당하는 메뉴를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # 이미지 파일이 존재하면 업데이트, 그렇지 않으면 기존 이미지 유지
            if 'image' in request.FILES:
                menu_data['image'] = request.FILES['image']
            else:
                menu_data.pop('image', None)  # 이미지가 없으면 해당 필드 삭제

            serializer = MenuSerializer(menu, data=menu_data, partial=True)

            if serializer.is_valid():
                updated_menu = serializer.save()
                updated_menus.append(serializer.data)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        # Store의 menu_price 필드 업데이트
        update_menu_price_field(store)

        return Response({'updated_menus': updated_menus}, status=status.HTTP_200_OK)

    
    def delete_menus(self, request, menus):
        """
        메뉴 삭제 
        """
        deleted_menus = []

        for menu_data in menus:
            store_slug = unquote(menu_data.get('slug'))
            menu_number = menu_data.get('menu_number')

            if not store_slug or not menu_number:
                return Response(
                    {'error': 'Slug 또는 menu_number가 제공되지 않았습니다.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                store = Store.objects.get(slug=store_slug, user=request.user)
            except Store.DoesNotExist:
                return Response(
                    {'error': f'{store_slug}에 해당하는 스토어를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            try:
                menu = Menu.objects.get(store=store, menu_number=menu_number)
                menu.delete()
                deleted_menus.append(menu_number)
            except Menu.DoesNotExist:
                return Response(
                    {'error': f'{menu_number}에 해당하는 메뉴를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
        # Store의 menu_price 필드 업데이트
        update_menu_price_field(store)

        return Response({'deleted_menus': deleted_menus}, status=status.HTTP_200_OK)

    def view_menus(self, request, slug, type_):
        """
        특정 스토어의 메뉴 목록을 조회
        """
        store_slug = slug

        try:
            # store를 조회 (소유자 상관 없이 모든 사용자에게 보여줌)
            store = Store.objects.get(slug=store_slug)
        except Store.DoesNotExist:
            return Response(
                {'error': f'{store_slug}에 해당하는 스토어를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # type이 'owner'일 경우에만 권한 체크
        if type_ == 'owner':
            if not request.user.is_authenticated:
                return Response({'error': '인증이 필요합니다.'}, status=status.HTTP_401_UNAUTHORIZED)

            # 인증된 경우에도 store 소유자인지 확인
            if store.user != request.user:
                return Response({'error': '권한이 없습니다.'}, status=status.HTTP_403_FORBIDDEN)

        # 메뉴 목록 조회 (type이 'customer'일 경우 권한 체크 없이 조회 가능)
        menus = Menu.objects.filter(store=store)
        serializer = MenuSerializer(menus, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

        
    def view_category(self, request, slug):
        """
        카테고리 목록 조회 메서드
        주어진 스토어의 카테고리 목록을 조회하여 반환
        """
        store_slug = (slug)
        try:
            # 해당 가게를 조회
            store = Store.objects.get(slug=store_slug, user=request.user)
        except Store.DoesNotExist:
            return Response(
                {'error': f'{store_slug}에 해당하는 스토어를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # store와 연결된 메뉴들을 필터링하여 메뉴 목록을 가져옴
        menus = Menu.objects.filter(store=store)

        # 메뉴에서 카테고리 리스트 추출 및 중복 제거
        categories = menus.values_list('category', flat=True).distinct()

        # 카테고리 옵션을 프론트엔드에 맞게 변환
        category_options = [{'value': category, 'label': category} for category in categories if category]

        # 카테고리 리스트 반환
        return Response(category_options, status=status.HTTP_200_OK)
    


class StatisticsView(APIView):
    authentication_classes = [JWTAuthentication] 
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request, *args, **kwargs):
        try:
            # 사용자별 CSV 파일 폴더 경로 지정
            folder_path = f'conversation_history/{request.user.user_id}'

            # 사용자 폴더가 존재하는지 확인
            if not os.path.exists(folder_path):
                #logger.debug(f"{folder_path} 경로가 존재하지 않습니다.")
                return Response({"status": "no folder", "message": "사용자 데이터 폴더가 존재하지 않습니다."})
            
            # CSV 파일 병합 함수 호출
            merged_file_path = merge_csv_files(folder_path)
            
            # 병합된 파일이 없으면 파일 없음 메시지 반환
            if not merged_file_path or not os.path.exists(merged_file_path):
                #logger.debug("병합된 파일이 존재하지 않습니다.")
                return Response({"status": "no file", "message": "해당 파일이 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)


            # 이미지 URL을 응답에 포함
            response_data = {
                "status": "success",
                "data": "",
                "image_url": f"/media/statistics/{request.user.user_id}/most_common_utterances.png"
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            # 오류 메시지 로그 출력
            logger.error(f"오류 발생: {str(e)}")
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class FeedListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            #logger.debug(f"Request body: {request.body}")
            data = json.loads(request.body)
            slug = data.get('slug')
            store_id = data.get('store_id')

            # slug 또는 store_id가 없으면 에러 반환
            if not slug and not store_id:
                return Response({'error': 'slug 또는 store_id 중 하나가 필요합니다.'}, status=400)
            
            if store_id:
                if not request.user.is_authenticated:
                    return Response({'error': '인증이 필요합니다.'}, status=401)

                # 인증된 사용자만 store_id 접근 허용
                #logger.debug(f"Authenticated user: {request.user.username}")
                #logger.debug(f"Using provided store_id: {store_id}")

            # slug를 기반으로 store_id 조회
            if slug:
                try:
                    store = Store.objects.get(slug=slug)
                    store_id = store.store_id
                    #logger.debug(f"Found store_id from slug: {store_id}")
                except Store.DoesNotExist:
                    #logger.debug(f"Store with slug '{slug}' not found.")
                    return Response({'error': f'슬러그 "{slug}"에 해당하는 매장을 찾을 수 없습니다.'}, status=404)

            # store_id에 해당하는 디렉토리 경로
            store_dir = os.path.join(settings.MEDIA_ROOT, 'uploads', f'store_{store_id}/feed')
            #logger.debug(f"Generated store directory: {store_dir}")

            # 디렉토리 존재 여부 확인
            if not os.path.exists(store_dir):
                #logger.debug(f"Directory does not exist. Creating directory: {store_dir}")
                os.makedirs(store_dir, exist_ok=True)  # 디렉토리 생성

            # 디렉토리 내 파일 목록 가져오기
            files = os.listdir(store_dir)
            #logger.debug(f"Files in directory: {files}")

            # 파일 정보를 파싱하여 ID, 이름, 경로로 매핑
            image_files = []
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    # 파일 이름에서 ID와 이름 추출
                    base_name, ext = os.path.splitext(file)
                    parts = base_name.rsplit('_', 1)  # 마지막 '_' 기준으로 분리
                    name = parts[0] if len(parts) > 1 else 'Unnamed'
                    file_id = parts[1] if len(parts) > 1 else None

                    image_files.append({
                        'id': file_id,
                        'name': name,
                        'path': os.path.join('uploads', f"store_{store_id}/feed", file).replace("\\", "/"),
                        'ext' : ext
                    })

            #logger.debug(f"Image files: {image_files}")

            if not image_files:
                return Response({'message': f'{store_id}번 매장에서 이미지 파일을 찾을 수 없습니다.'}, status=200)

            return Response({'success': True, 'data': {'images': image_files}}, status=200)

        except Exception as e:
            #logger.debug(f"Error: {str(e)}")
            return Response({'error': f'오류가 발생했습니다: {str(e)}'}, status=500)


class FeedUploadView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request, *args, **kwargs):
        store_id = request.data.get('store_id')  # 프론트엔드에서 전달된 store_id 가져오기
        if not store_id:
            return Response({'error': 'store_id가 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)

        upload_dir = os.path.join(settings.MEDIA_ROOT, f"uploads/store_{store_id}/feed")

        # 폴더가 없으면 생성
        os.makedirs(upload_dir, exist_ok=True)

        file = request.FILES.get('file')
        if not file:
            return Response({'error': '파일이 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)

        original_name = os.path.splitext(file.name)[0]  # 파일명에서 확장자를 제외한 원래 이름
        _, ext = os.path.splitext(file.name)  # 확장자 분리

        # 고유 ID 생성 (UUID 사용)
        new_id = str(uuid.uuid4())  # UUID를 문자열로 변환

        # 고유 파일 이름 생성
        unique_filename = f"{original_name}_{new_id}{ext}"  # 원래 이름 + 고유 ID + 확장자

        file_path = os.path.join(upload_dir, unique_filename)

        with open(file_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        relative_path = os.path.relpath(file_path, settings.MEDIA_ROOT).replace("\\", "/")  # MEDIA_ROOT 기준 상대 경로 반환

        return Response({
            'success': True,
            'message': '이미지 업로드 성공',
            'id': new_id,  # UUID를 ID로 반환
            'file_path': relative_path,  # 저장된 상대 경로
            'stored_name': unique_filename,  # 저장된 파일 이름
            'ext' : ext # 확장자 
        }, status=status.HTTP_201_CREATED)


class FeedDeleteView(APIView):
    authentication_classes = [JWTAuthentication] 
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def delete(self, request, *args, **kwargs):
        #logger.debug("===== FeedDeleteView Debug Start =====")

        # 요청 데이터 디버깅
        #logger.debug(f"Request data: {request.data}")
        image_id = request.data.get('id')  # 이미지 ID (예: 20241120-001)
        store_id = request.data.get('store_id')  # store_id 가져오기

        if not image_id or not store_id:
            #logger.debug("Error: Missing required parameters (id or store_id)")
            return Response({
                'success': False,
                'message': 'id와 store_id는 필수 항목입니다.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 파일 경로 생성 디버깅
        file_path = os.path.join(settings.MEDIA_ROOT, f"uploads/store_{store_id}/feed/{image_id}")
        #logger.debug(f"Generated file path: {file_path}")

        try:
            # 파일 존재 여부 확인
            if os.path.exists(file_path):
                #logger.debug(f"File exists. Deleting file: {file_path}")
                os.remove(file_path)  # 파일 삭제
                #logger.debug("File deleted successfully.")
                return Response({'success': True, 'message': '이미지 삭제 성공'}, status=status.HTTP_200_OK)
            else:
                #logger.debug("Error: File does not exist.")
                return Response({'success': False, 'message': '이미지를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            #logger.debug(f"Error during file deletion: {str(e)}")
            return Response({
                'success': False,
                'message': f'오류 발생: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

class FeedRenameView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def put(self, request, *args, **kwargs):

        # 요청 데이터 디버깅
        #logger.debug(f"Request data: {request.data}")
        image_id = request.data.get('id')  # 기존 파일 ID
        new_name = request.data.get('name')  # 새 파일 이름
        store_id = request.data.get('store_id')  # store_id 가져오기

        if not image_id or not new_name or not store_id:
            #logger.debug("Error: Missing required parameters (id, name, store_id)")
            return Response(
                {'success': False, 'message': 'id, name, store_id는 필수 항목입니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 경로 디버깅
        base_dir = os.path.join(settings.MEDIA_ROOT, f"uploads/store_{store_id}/feed")
        #logger.debug(f"Base directory: {base_dir}")
        
        old_file_path = os.path.join(base_dir, image_id)
        #logger.debug(f"Old file path: {old_file_path}")

        # 새로운 파일 이름 생성 디버깅
        base_name, ext = os.path.splitext(image_id)
        uuid_part = base_name.rsplit('_', 1)[-1]  # 기존 UUID 추출
        new_file_name = f"{new_name}_{uuid_part}{ext}"
        new_file_path = os.path.join(base_dir, new_file_name)
        
        #logger.debug(f"New file name: {new_file_name}")
        #logger.debug(f"New file path: {new_file_path}")

        try:
            # 기존 파일 확인 및 이름 변경 디버깅
            if os.path.exists(old_file_path):
                #logger.debug("Old file exists. Proceeding to rename.")
                os.rename(old_file_path, new_file_path)  # 파일 이름 변경
                #logger.debug("File renamed successfully.")
                return Response(
                    {
                        'success': True,
                        'message': '이미지 이름 변경 성공',
                        'new_name': new_file_name,  # 새 파일 이름 반환
                        'id': uuid_part,  # UUID는 변경하지 않음
                    },
                    status=status.HTTP_200_OK
                )
            else:
                #logger.debug("Error: Old file does not exist.")
                return Response(
                    {'success': False, 'message': '파일을 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        except Exception as e:
            #logger.debug(f"Error during file rename: {str(e)}")
            return Response(
                {'success': False, 'message': f'오류 발생: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



# 계정 비활성화
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
        user.username = f'deleted_user_{user.id}'  # 사용자 아이디를 익명화
        user.phone = f'000-0000-0000_{user.id}'  # 핸드폰 번호 삭제 또는 익명화
        user.email = f'deleted_{user.id}@example.com'  # 이메일을 익명화
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
        # 사용자 파일이 저장된 경로
        user_folder_path = os.path.join(settings.MEDIA_ROOT, 'uploads', str(user.id))
        
        # 폴더가 존재하면 삭제
        if os.path.exists(user_folder_path):
            shutil.rmtree(user_folder_path)


class PushTokenView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            user = request.user
            push_token = request.data.get('push_token')
            
            # 푸시 토큰을 사용자 모델에 저장
            user.push_token = push_token
            user.save()
            
            return Response({'success': True})
        except Exception as e:
            return Response({'error': str(e)}, status=400)


class SendPushNotificationView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            user = request.user
            message = request.data.get('message')
            
            if not user.push_token:
                return Response({'error': 'Push token not found'}, status=400)
                
            # Expo 푸시 서버로 메시지 전송
            push_client = PushClient()
            push_message = PushMessage(
                to=user.push_token,
                body=message,
                data={'type': 'preview_notification'}
            )
            push_client.publish(push_message)
            
            return Response({'success': True})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

