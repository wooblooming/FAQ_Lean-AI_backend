from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.conf import settings
from django.shortcuts import get_object_or_404 
from django.utils.text import slugify
from urllib.parse import unquote, quote
from django.utils import timezone 
from .authentication import PublicUserJWTAuthentication
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
import requests, random, logging, json, os, shutil
from .analyze_utterances import get_most_common_utterances, save_most_common_utterances_graph
from .merged_csv import merge_csv_files


# QR 코드 생성에 필요한 라이브러리
import qrcode
import os
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator

# 모델과 시리얼라이저 임포트
from .models import Public_User, Public, Public_Department, Public_Edit, Public_Complaint
from .serializers import (
    PublicUserSerializer, 
    PublicSerializer, 
    PublicRegisterSerializer,
    PublicUsernameCheckSerializer, 
    PublicPasswordCheckSerializer,
    PublicEditSerializer, 
    PublicComplaintSerializer
)

# 디버깅을 위한 로거 설정
logger = logging.getLogger('faq')

from django.db import transaction
import logging

logger = logging.getLogger('faq')

class SignupView(APIView):
    permission_classes = [AllowAny]
     
    def post(self, request):
        # 사용자 정보 받아오기
        user_data = {
            'username': request.data.get('username'),
            'password': request.data.get('password'),
            'name': request.data.get('name'),
            'dob': request.data.get('dob'),
            'phone': request.data.get('phone'),
            'email': request.data.get('email') if request.data.get('email') else None,
            'marketing': request.data.get('marketing'),
        }

        institution_id = request.data.get('institution_id')
        department_name = request.data.get('department')
        user_data['department'] = department_name
        
        # 기관 ID가 없는 경우 오류 반환
        if not institution_id:
            return Response({'success': False, 'message': '기관 ID가 제공되지 않았습니다.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 기관 조회
            public_institution = Public.objects.get(public_id=institution_id)
            logger.debug(f"공공기관 조회 성공: {public_institution}")

            # 사용자 생성과 기관 및 부서 연결을 트랜잭션으로 처리
            with transaction.atomic():
                # department 이름으로 부서 조회 또는 생성
                department, created = Public_Department.objects.get_or_create(
                    department_name=department_name,
                    public=public_institution  # 이 부분에서 public_institution을 public 필드로 지정
                )
                logger.debug(f"부서 생성/조회 성공: {department}, 생성 여부: {created}")

                # 사용자 생성
                user_serializer = PublicUserSerializer(data=user_data)
                
                # 사용자 데이터 검증
                if not user_serializer.is_valid():
                    logger.debug(f"회원가입 유효성 검사 실패: {user_serializer.errors}")
                    return Response({
                        'success': False, 
                        'message': '회원가입에 실패했습니다.', 
                        'errors': user_serializer.errors
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # 사용자 저장
                user = user_serializer.save()

                # 생성한 사용자에 기관 및 부서 할당
                user.public = public_institution
                user.department = department  # department_id 저장
                user.save()

                return Response({
                    'success': True, 
                    'message': '사용자와 공공기관 및 부서가 성공적으로 연결되었습니다.'
                }, status=status.HTTP_201_CREATED)

        except Public.DoesNotExist:
            logger.error("해당 ID의 공공기관이 존재하지 않습니다.")
            return Response({'success': False, 'message': '해당 ID의 공공기관이 존재하지 않습니다.'}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error(f"서버 오류 발생: {str(e)}")
            return Response({
                'success': False, 
                'message': '서버 오류가 발생했습니다. 다시 시도해주세요.',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




# 로그인 API 뷰
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        try:
            user = Public_User.objects.get(username=username)
            
            if check_password(password, user.password):
                # Refresh 및 Access 토큰 생성
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)
                
                # 사용자의 public_id 반환
                if user.public:
                    public_id = user.public.public_id
                else:
                    return Response({"error": "기관이 없습니다."}, status=status.HTTP_404_NOT_FOUND)
                
                # 토큰 정보 출력
                #logger.debug(f"Generated Access Token for Public_User ID {user.user_id}: {access_token}")
                
                return Response({'access': access_token, 'public_id': public_id})
            else:
                return Response({"error": "아이디 또는 비밀번호가 일치하지 않습니다.\n 다시 시도해 주세요."}, status=status.HTTP_401_UNAUTHORIZED)

        except Public_User.DoesNotExist:
            return Response({"error": "아이디 또는 비밀번호가 일치하지 않습니다.\n 다시 시도해 주세요."}, status=status.HTTP_401_UNAUTHORIZED)
        
        except Exception as e:
            print(f"Unhandled error: {e}")
            return Response({"error": "로그인 처리 중 문제가 발생했습니다. 관리자에게 문의하세요."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class UserPublicInfoView(APIView):
    # 기본적으로 인증을 설정하지 않음
    permission_classes = [AllowAny]

    def dispatch(self, request, *args, **kwargs):
        # type이 owner일 때만 인증 설정 적용
        user_type = request.query_params.get('type')  # 쿼리 파라미터로 type을 전달받는다고 가정
        if user_type == 'owner':
            self.authentication_classes = [PublicUserJWTAuthentication]
            self.permission_classes = [IsAuthenticated]
        
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):       
        try:
            # 인증이 필요한 경우, `request.user`를 바로 사용할 수 있습니다.
            public_user = request.user

            if not public_user and request.query_params.get('type') == 'owner':
                return Response({"error": "가입된 사용자가 아닙니다."}, status=status.HTTP_404_NOT_FOUND)

            # 공공기관 정보 조회
            public = public_user.public if request.query_params.get('type') == 'owner' else None
            if not public and request.query_params.get('type') == 'owner':
                return Response({"error": "공공기관 정보가 없습니다."}, status=status.HTTP_404_NOT_FOUND)

            # 부서 정보 조회
            department = public_user.department if public_user else None
            department_data = {
                "department_id": department.department_id if department else "",
                "department_name": department.department_name if department else ""
            }

            user_data = PublicUserSerializer(public_user).data if public_user else {}
            public_data = PublicSerializer(public).data if public else {}

            response_data = {
                "user": user_data,
                "public": public_data,
                "department": department_data
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Public_User.DoesNotExist:
            return Response({"error": "가입된 사용자가 아닙니다."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"서버 오류가 발생했습니다: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 사용자명 중복 확인 API
class UsernameCheckView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PublicUsernameCheckSerializer(data=request.data)
        #logger.debug(f"Received data for username check: {request.data}")
        if serializer.is_valid():
            username = serializer.validated_data['username']
            #logger.debug(f"Validated username: {username}")

            if Public_User.objects.filter(username=username, is_active=True).exists():
                return Response({'is_duplicate': True, 'message': '이미 사용 중인 사용자 아이디입니다.'}, status=status.HTTP_409_CONFLICT)
            
            return Response({'is_duplicate': False, 'message': '사용 가능한 사용자 아이디입니다.'}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 인증 코드 전송 API
class SendVerificationCodeView(APIView):
    permission_classes = [AllowAny]

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
                user = Public_User.objects.get(phone=phone_number)
            except Public_User.DoesNotExist:
                return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        elif code_type == 'findPW':
            # 사용자 ID와 전화번호로 사용자 확인
            try:
                user = Public_User.objects.get(username=user_id, phone=phone_number)
            except Public_User.DoesNotExist:
                return Response({'success': False, 'message': '아이디 또는 전화번호가 잘못되었습니다.'}, status=status.HTTP_404_NOT_FOUND)

        elif code_type == 'mypage':
            # mypage에서 전화번호가 이미 등록된 번호인지 확인
            try:
                user = Public_User.objects.get(username=user_id)
                if user.phone == phone_number:
                    return Response({'success': False, 'message': '이미 등록된 핸드폰 번호입니다.'}, status=status.HTTP_400_BAD_REQUEST)
            except Public_User.DoesNotExist:
                return Response({'success': False, 'message': '해당 ID로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        else:
            # 회원가입 등 기타 경우: 전화번호 중복 확인
            if Public_User.objects.filter(phone=phone_number, is_active=True).exists():
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
    permission_classes = [AllowAny]

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
                    user = Public_User.objects.get(username=user_id)
                    # 사용자의 전화번호를 입력받은 phone_number로 업데이트
                    user.phone = phone_number
                    user.save()

                    return Response({'success': True, 'message': '인증이 완료되었으며, 전화번호가 업데이트되었습니다.'}, status=status.HTTP_200_OK)
                except Public_User.DoesNotExist:
                    return Response({'success': False, 'message': '해당 ID로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

            elif code_type == 'findID' or code_type == 'findPW':
                try:
                    # 사용자 정보 반환
                    user = Public_User.objects.get(phone=phone_number)
                    return Response({
                        'success': True,
                        'message': '인증이 완료되었습니다.',
                        'user_id': user.username,
                        'user_password': user.password,
                        'date_joined': user.created_at.strftime('%Y.%m.%d')
                    }, status=status.HTTP_200_OK)
                except Public_User.DoesNotExist:
                    return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'success': True, 'message': '회원가입 인증이 완료되었습니다.'}, status=status.HTTP_200_OK)
        else:
            return Response({'success': False, 'message': '인증 번호가 일치하지 않습니다.'}, status=status.HTTP_400_BAD_REQUEST)


# 비밀번호 재설정 API
class PasswordResetView(APIView):
    permission_classes = [AllowAny]

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
            user = Public_User.objects.get(phone=phone_number)
            user.password = make_password(new_password)
            user.save()

            return Response({'success': True, 'message': '비밀번호가 성공적으로 변경되었습니다.'}, status=status.HTTP_200_OK)
        except Public_User.DoesNotExist:
            return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

# 유저의 스토어 목록을 반환하는 API
class UserPublicListView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        #logger.debug(f"Authenticated user: {request.user}, Auth: {request.auth}")
        # 유저와 연관된 모든 스토어 반환
        user = request.user
        public = Public.objects.filter(user=user)
        serializer = PublicSerializer(public, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request):

        # 퍼센트 인코딩된 slug를 디코딩
        decoded_slug = unquote(requests.slug)

        # 주어진 slug와 사용자로 스토어 정보 가져오기
        try:
            public = Public.objects.get(slug=decoded_slug, user=request.user) 
        except Public.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        
        # 배너 필드가 빈 문자열인 경우 null로 처리
        if 'banner' in data and data['banner'] == '':
            data['banner'] = None

        serializer = PublicSerializer(public, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 특정 스토어 정보를 업데이트하는 API
class UserPublicDetailView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능
    
    def put(self, request, public_id):
         # 주어진 public_id, 사용자로 스토어 정보 가져오기
        try:
            public = Public.objects.get(public_id=public_id, user=request.user)
        except Public.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        
        # 배너 필드가 빈 문자열인 경우 null로 처리
        if 'banner' in data and data['banner'] == '':
            data['banner'] = None

        serializer = PublicSerializer(public, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
   

# 사용자 게시물 등록 API
class EditView(APIView):
    # 이 뷰는 로그인된 사용자만 접근 가능하도록 설정
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

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

                edit_serializer = PublicEditSerializer(data=data)
                
                if edit_serializer.is_valid():
                    edit_serializer.save()
                    saved_data.append(edit_serializer.data)
                else:
                    logger.debug(f"에러 메시지 : {edit_serializer.errors}")
                    return Response(edit_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            # 파일이 없을 경우, 제목과 내용만 처리
            data = {
                'user': request.user.user_id,
                'title': request.data.get('title', ''),
                'content': request.data.get('content', '')
            }

            edit_serializer = PublicEditSerializer(data=data)

            if edit_serializer.is_valid():
                edit_serializer.save()
                saved_data.append(edit_serializer.data)
            else:
                logger.debug(f"에러 메시지 : {edit_serializer.errors}")
                return Response(edit_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(saved_data, status=status.HTTP_201_CREATED)


# 사용자 프로필 업데이트 API
class UserProfileView(APIView):
    # 이 뷰는 인증된 사용자만 접근할 수 있도록 설정
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    # 유저 프로필을 업데이트하는 메서드
    def put(self, request):
        user = request.user
        data = request.data

        # 사용자 정보 업데이트
        user.name = data.get('name', user.name)
        user.email = data.get('email', user.email)
        user.phone = data.get('phone_number', user.phone)
        user.marketing = data.get('marketing', user.marketing)

        # 부서 정보 업데이트
        department_name = data.get('department')
        if department_name:
            public = user.public  # 사용자와 연결된 Public 객체
            if public:
                department, created = Public_Department.objects.get_or_create(
                    department_name=department_name, public=public
                )
                user.department = department

        user.save()

        return Response({
            'message': 'User profile updated successfully',
            'profile_photo': user.profile_photo.url if user.profile_photo else "/media/profile_default_img.jpg",
            'name': user.name,
            'email': user.email,
            'phone_number': user.phone,
            'marketing': user.marketing,
            'department': {
                "department_id": user.department.department_id if user.department else "",
                "department_name": user.department.department_name if user.department else ""
            }
        }, status=status.HTTP_200_OK)


        
# 프로필 사진 업데이트 API
class UserProfilePhotoUpdateView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        # 프로필 사진 업데이트
        user = request.user
        profile_photo_url = request.data.get('profile_photo')

        if profile_photo_url == "":  # 빈 문자열일 경우 프로필 사진을 None으로 설정
            user.profile_photo = None
        elif profile_photo_url == "default":  # 특정 키워드를 기본 이미지 설정을 위한 트리거로 사용
            user.profile_photo = 'profile_photos/profile_default_img.jpg'
        else:  # 다른 경우, 전달된 URL을 프로필 사진으로 설정
            user.profile_photo = profile_photo_url

        # 변경 사항을 데이터베이스에 저장
        user.save()
        return Response({"message": "프로필 사진이 성공적으로 업데이트되었습니다."}, status=status.HTTP_200_OK)


# 스토어 목록 조회 및 단일 스토어 조회 API
class CustomerPublicView(APIView):
    permission_classes = [AllowAny]  # 인증 없이 접근 가능하도록 설정

    def get(self, request):
        # 사용자의 타입에 따라 다르게 응답
        user_type = request.query_params.get('type')  # 'owner' 또는 'customer' 받기
        slug = request.query_params.get('slug')  # 슬러그도 쿼리 파라미터에서 받기

        if slug:
            # 슬러그가 존재할 경우 디코딩
            decoded_slug = unquote(slug)
        else:
            decoded_slug = None

        if user_type == 'owner':
            # 소유자라면 로그인된 사용자만 조회 가능
            if not request.user.is_authenticated:
                return Response({'error': '로그인이 필요합니다.'}, status=status.HTTP_401_UNAUTHORIZED)

            # 로그인된 사용자의 모든 스토어 가져오기
            publics = Public.objects.filter(user=request.user)
            publics_data = [
                {
                    'slug': public.slug,
                } for public in publics
            ]
            return Response(publics_data, status=status.HTTP_200_OK)
        
        elif user_type == 'customer':
            # 고객일 경우 모든 스토어 목록 제공
            if decoded_slug:
                # 디코딩된 슬러그로 특정 스토어 조회
                try:
                    public = Public.objects.get(slug=decoded_slug)
                    public_data = {
                        'public_name': public.public_name,
                        'slug': public.slug,
                        'public_address': public.public_address,
                        'public_hours': public.opening_hours,
                        'agent_id': public.agent_id,

                    }
                    return Response(public_data, status=status.HTTP_200_OK)
                except Public.DoesNotExist:
                    return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

            # 슬러그가 없는 경우 모든 스토어 목록을 반환
            publics = Public.objects.all()
            publics_data = [
                {
                    'slug': public.slug,
                } for public in publics
            ]
            return Response(publics_data, status=status.HTTP_200_OK)

        else:
            return Response({'error': '유효하지 않은 요청입니다.'}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        # 단일 스토어 정보 조회
        user_type = request.data.get('type')  # 'owner' 또는 'customer' 받기
        slug = request.data.get('slug')

        if not slug:
            return Response({'error': '스토어 slug 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

        # 슬러그를 디코딩
        decoded_slug = unquote(slug)

        # 스토어 정보 조회
        try:
            public = Public.objects.get(slug=decoded_slug)
        except Public.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        public_data = {
            'public_id' : public.public_id,
            'public_name': public.public_name,
            'public_image': public.banner.url if public.banner else '',
            'public_hours': public.opening_hours,
            'public_tel': public.public_tel,
            'agent_id': public.agent_id,
        }

        # 소유자라면 추가적인 정보 제공 가능
        if user_type == 'owner' and not request.user.is_authenticated:
            return Response({'error': '로그인이 필요합니다.'}, status=status.HTTP_401_UNAUTHORIZED)
        
        return Response(public_data, status=status.HTTP_200_OK)


class GenerateQrCodeView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        public_id = request.data.get('public_id')

        if not public_id:
            return Response({'error': '스토어 ID가 필요합니다.'}, status=400)

        try:
            public = Public.objects.get(public_id=public_id, public_users=request.user)
        except Public.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=404)

        # QR 코드에 포함할 URL 설정
        qr_url = f'https://mumulai.com/publicIntroduction/{public.slug}'

        try:
            # 고유한 파일명 생성
            qr_filename = f'public_qr_{public_id}.png'
            qr_relative_path = os.path.join('qr_codes', qr_filename)
            qr_absolute_path = os.path.join(settings.MEDIA_ROOT, 'qr_codes')

            # QR 코드 디렉토리 생성
            os.makedirs(qr_absolute_path, exist_ok=True)

            # QR 코드 생성 및 설정
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4
            )
            qr.add_data(qr_url)
            qr.make(fit=True)

            # QR 코드 이미지 생성 및 저장
            img = qr.make_image(fill_color='black', back_color='white')
            
            # 전체 경로 생성
            full_path = os.path.join(qr_absolute_path, qr_filename)
            img.save(full_path)

            # 데이터베이스에 저장할 상대 경로
            db_path = os.path.join(settings.MEDIA_URL.strip('/'), qr_relative_path)
            
            # 기존 QR 코드 파일이 있다면 삭제
            if public.qr_code:
                old_path = os.path.join(settings.MEDIA_ROOT, public.qr_code.name)
                if os.path.exists(old_path):
                    os.remove(old_path)

            # 새 QR 코드 경로 저장
            public.qr_code = db_path
            public.save()

            return Response({
                'message': 'QR 코드가 성공적으로 생성되었습니다.',
                'qr_code_url': request.build_absolute_uri(public.qr_code),
                'qr_content_url': qr_url
            }, status=201)

        except Exception as e:
            logger.error(f"QR 코드 생성 중 오류 발생: {str(e)}")
            return Response({
                'error': '서버 내부 오류가 발생했습니다.',
                'detail': str(e)
            }, status=500)


# QR 코드 이미지를 반환하는 API
class QrCodeImageView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            public_id = request.data.get('public_id')  # 요청에서 public_id 가져오기
            if not public_id:
                return Response({'error': 'public_id가 필요합니다.'}, status=400)

            # 사용자의 스토어 정보 가져오기
            public = Public.objects.get(public_id=public_id, public_users=request.user)

            if public.qr_code:
                public_name = public.public_name
                qr_code_path = public.qr_code.lstrip('/')  # 경로에서 앞의 '/' 제거

                if qr_code_path.startswith('media/'):
                    qr_code_url = request.build_absolute_uri(f'/{qr_code_path}')
                else:
                    qr_code_url = request.build_absolute_uri(settings.MEDIA_URL + qr_code_path)

                qr_content_url = f'https://mumulai.com/publicIntroduction/{public.slug}'

                return Response({
                    'public_name': public_name,
                    'qr_code_image_url': qr_code_url,
                    'qr_content_url': qr_content_url
                }, status=200)
            else:
                return Response({'qr_code_image_url': None}, status=200)

        except Public.DoesNotExist:
            return Response({'error': 'public not found'}, status=404)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return Response({'error': 'An unexpected error occurred.'}, status=500)


class StatisticsView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request, *args, **kwargs):
        try:
            # 사용자별 CSV 파일 폴더 경로 지정
            folder_path = f'conversation_history/{request.user.user_id}'

            # 사용자 폴더가 존재하는지 확인
            if not os.path.exists(folder_path):
                logger.debug(f"{folder_path} 경로가 존재하지 않습니다.")
                return Response({"status": "no folder", "message": "사용자 데이터 폴더가 존재하지 않습니다."})
            
            # CSV 파일 병합 함수 호출
            merged_file_path = merge_csv_files(folder_path)
            
            # 병합된 파일이 없으면 파일 없음 메시지 반환
            if not merged_file_path or not os.path.exists(merged_file_path):
                logger.debug("병합된 파일이 존재하지 않습니다.")
                return Response({"status": "no file", "message": "해당 파일이 존재하지 않습니다."}, status=status.HTTP_404_NOT_FOUND)

            # 최다 언급 질문 3개 얻기
            most_common_utterances = get_most_common_utterances(merged_file_path)

            # 이미지 파일 저장 경로 생성
            image_folder_path = f'faq_backend/media/statistics/{request.user.user_id}'
            os.makedirs(image_folder_path, exist_ok=True)  # 폴더가 없으면 생성
            output_image_path = os.path.join(image_folder_path, 'most_common_utterances.png')

            # 그래프 이미지 생성 및 저장
            save_most_common_utterances_graph(most_common_utterances, output_image_path)

            # 이미지 URL을 응답에 포함
            response_data = {
                "status": "success",
                "data": most_common_utterances,
                "image_url": f"/media/statistics/{request.user.user_id}/most_common_utterances.png"
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            # 오류 메시지 로그 출력
            logger.error(f"오류 발생: {str(e)}")
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ComplaintsView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request, *args, **kwargs):
        logger.debug(f"Authorization Header: {request.headers.get('Authorization')}")

        if not request.user.is_authenticated:
            return Response({"error": "인증되지 않은 사용자입니다."}, status=status.HTTP_401_UNAUTHORIZED)

        user_public = request.user.publics.first()
        if not user_public:
            return Response({"error": "해당 사용자는 매장이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        user_public_id = user_public.public_id
        request_public_id = request.data.get('publicID')
        
        # 받은 데이터 로그 확인
        logger.debug(f"user_public_id: {user_public_id}, request_public_id: {request_public_id}")

        # 문자열 비교로 일치 여부 확인
        if str(user_public_id) != str(request_public_id):
            logger.debug(f"권한 오류: user_public_id({user_public_id}) != request_public_id({request_public_id})")
            return Response({"error": "권한이 없습니다."}, status=status.HTTP_403_FORBIDDEN)

        complaints = Public_Complaint.objects.filter(public_id=request_public_id)
        serializer = PublicComplaintSerializer(complaints, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)



class ComplaintsRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # 전달된 데이터를 시리얼라이저를 통해 검증 및 직렬화
        data = request.data.copy()
        slug = data.get('slug')  # slug를 받아옴

        # slug가 제공되지 않으면 에러 반환
        if not slug:
            return Response({"status": "error", "message": "slug 필드는 필수 항목입니다."}, status=status.HTTP_400_BAD_REQUEST)

        # slug로 Public 객체를 조회하거나 에러 반환
        try:
            public = Public.objects.get(slug=slug)  # slug를 사용하여 조회
            data['public'] = public.public_id  # 시리얼라이저에 사용할 public_id 설정

        except Public.DoesNotExist:
            return Response({"status": "error", "message": "유효하지 않은 publicID입니다."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PublicComplaintSerializer(data=data)
        
        if serializer.is_valid():
            # 데이터가 유효한 경우, DB에 저장
            complaint = serializer.save()
            complaint_number = complaint.complaint_number  # 저장된 접수번호
            
            # 민원인의 전화번호 가져오기
            phone_number = complaint.phone

            # Aligo SMS 전송 데이터 구성
            sms_data = {
                'key': settings.ALIGO_API_KEY,
                'user_id': settings.ALIGO_USER_ID,
                'sender': settings.ALIGO_SENDER,
                'receiver': phone_number,
                'msg': f'안녕하세요, 접수하신 민원의 접수번호는 [{complaint_number}]입니다.',
                'testmode_yn': 'Y',  # 테스트 모드 활성화 (실제 발송 시 'N'으로 변경)
            }

            # SMS 전송 API 호출
            try:
                response = requests.post('https://apis.aligo.in/send/', data=sms_data)
                response_data = response.json()

                # SMS 전송 성공 여부 확인
                if response_data.get('result_code') == '1':
                    logger.info(f"SMS 전송 성공: 접수번호 [{complaint_number}]")
                    return Response(
                        {"status": "success", "message": "민원이 성공적으로 접수되었습니다.", "complaint_number": complaint_number, "public_slug": public.slug},
                        status=status.HTTP_201_CREATED
                    )
                else:
                    logger.error(f"SMS 전송 실패: {response_data.get('message')}")
                    return Response({"status": "error", "message": "민원이 접수되었지만 SMS 전송에 실패했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            except requests.RequestException as e:
                logger.error(f"SMS 전송 중 오류 발생: {str(e)}")
                return Response({"status": "error", "message": "민원이 접수되었지만 SMS 전송에 실패했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        else:
            # 유효하지 않은 경우, 검증 실패한 필드 정보 기록
            logger.error(f"민원 접수 실패: 유효하지 않은 데이터 - {serializer.errors}")
            return Response({"status": "error", "message": "유효하지 않은 데이터", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class UpdateComplaintStatusView(APIView):
    permission_classes = [AllowAny]

    def patch(self, request, id, *args, **kwargs): 
        try:
            # ID로 민원 검색
            complaint = Public_Complaint.objects.get(id=id)  
            new_status = request.data.get('status')
            
            # 상태 업데이트
            if new_status not in dict(Public_Complaint.STATUS_CHOICES):
                return Response({"status": "error", "message": "유효하지 않은 상태입니다."}, status=status.HTTP_400_BAD_REQUEST)

            complaint.status = new_status
            complaint.save()

            # 상태가 "완료"로 변경되었을 때 SMS 전송
            if new_status == "완료":
                sms_data = {
                    'key': settings.ALIGO_API_KEY,
                    'user_id': settings.ALIGO_USER_ID,
                    'sender': settings.ALIGO_SENDER,
                    'receiver': complaint.phone,
                    'msg': f'안녕하세요, 접수번호 [{complaint.complaint_number}]의 민원 처리가 완료되었습니다.',
                    'testmode_yn': 'Y',  # 테스트 모드 활성화 (실제 발송 시 'N'으로 변경)
                }
                response = requests.post('https://apis.aligo.in/send/', data=sms_data)
                response_data = response.json()

                if response_data.get('result_code') != '1':
                    logger.error(f"SMS 전송 실패: {response_data.get('message')}")
                    return Response({"status": "error", "message": "상태는 업데이트되었지만 SMS 전송에 실패했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({"status": "success", "message": f"민원 상태가 '{new_status}'로 업데이트되었습니다."}, status=status.HTTP_200_OK)

        except Public_Complaint.DoesNotExist:
            return Response({"status": "error", "message": "해당 ID의 민원을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"민원 상태 업데이트 중 오류 발생: {str(e)}")
            return Response({"status": "error", "message": "민원 상태 업데이트 중 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 계정 비활성화
class DeactivateAccountView(APIView):
    """
    사용자를 탈퇴시키는 뷰. 
    사용자 계정을 비활성화하고 개인정보를 익명화 처리.
    """
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

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
        self.anonymize_publics(user)

        # 사용자와 관련된 Edit 데이터 익명화
        self.anonymize_edits(user)

        # 사용자 폴더 삭제
        self.delete_user_folder(user)

    def anonymize_publics(self, user):
        """
        탈퇴한 사용자의 가게 데이터를 익명화 처리.
        """
        publics = Public.objects.filter(user=user)
        for public in publics:
            public.public_name = f'익명화된 가게_{public.public_id}'  # 가게 이름 익명화
            public.slug = f'deleted-public_{public.public_id}'  # 간단한 익명화 처리
            public.save()

    
    def anonymize_edits(self, user):
        """
        탈퇴한 사용자의 Edit 데이터를 익명화 처리.
        """
        edits = Public_Edit.objects.filter(user=user)
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

            
# 공공기관 정보 저장 API
class PublicCreateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        logger.debug(f"Request data: {request.data}")

        # 회원가입 과정에서 사용하는 PublicRegisterSerializer를 통해 데이터 검증 및 저장
        register_serializer = PublicRegisterSerializer(data=request.data)
        
        if register_serializer.is_valid():
            try:
                register_serializer.save()  # 유효한 경우, 데이터베이스에 저장
                return Response({"status": "success", "message": "공공기관 정보가 성공적으로 등록되었습니다.", "data": register_serializer.data}, status=status.HTTP_201_CREATED)
            
            except ValidationError as e:
                # 유효하지 않은 경우, 오류 메시지 출력
                logger.debug(f"Validation errors: {register_serializer.errors}")
                return Response(register_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 모든 공공기관 출력 API
class PublicListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            public_list = Public.objects.all()
            serializer = PublicSerializer(public_list, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"PublicListView 오류 발생: {str(e)}")
            return Response({"error": "기관 목록을 불러오는 중 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# 선택한 공공기관 정보 출력
class PublicDetailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # POST 요청의 본문에서 'id'를 가져옴
        public_id = request.data.get('id', None)
        
        # 디버깅을 위한 로그 추가
        logger.debug(f"Received public_id: {public_id}")
        
        # public_id가 없는 경우 오류 메시지 반환
        if public_id is None:
            logger.error("기관 ID가 제공되지 않았습니다.")
            return Response({"error": "기관 ID가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 해당 public_id로 Public 객체를 가져옴
            public_institution = Public.objects.get(public_id=public_id)
            # 가져온 Public 객체를 시리얼라이즈
            serializer = PublicSerializer(public_institution)
            
            # 성공적으로 데이터를 반환할 때 로그 추가
            logger.debug(f"Fetched institution details: {serializer.data}")
            
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except Public.DoesNotExist:
            # 해당 ID의 기관이 없는 경우 오류 반환
            logger.error(f"기관 ID {public_id}에 해당하는 기관이 없습니다.")
            return Response({"error": "해당 기관을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

class DepartmentListView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            # 요청에서 slug 가져오기
            slug = request.data.get('slug')
            if not slug:
                return Response({'error': 'slug가 제공되지 않았습니다.'}, status=400)

            # slug에 해당하는 Public 객체 찾기
            public = Public.objects.filter(slug=slug).first()
            if not public:
                return Response({'error': '해당 slug에 일치하는 Public이 없습니다.'}, status=404)

            # Public_Department에서 해당 public_id에 대한 부서 목록 가져오기
            departments = (
                Public_Department.objects.filter(public=public)
                .values_list('department_name', flat=True)
                .distinct()
            )

            # 부서가 존재할 경우와 없는 경우 응답 구분
            if departments:
                return Response({'departments': list(departments)}, status=200)
            else:
                return Response({'message': '해당 public_id에 대한 부서가 없습니다.'}, status=404)

        except Exception as e:
            return Response({'error': str(e)}, status=500)

