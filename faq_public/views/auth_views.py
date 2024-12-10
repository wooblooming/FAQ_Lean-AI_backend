# auth_views.py
# 로그인, 회원가입, 비밀번호 재설정, 계정 비활성화
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.conf import settings
from django.utils import timezone 
from ..authentication import PublicUserJWTAuthentication
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
import requests, random, logging, os, shutil

from ..models import Public_User, Public, Public_Department, Public_Edit, Public_Complaint
from ..serializers import (
    PublicUserSerializer, 
    PublicUsernameCheckSerializer, 
    PublicPasswordCheckSerializer,
)

# 디버깅을 위한 로거 설정
logger = logging.getLogger('faq')


# User Management APIs
# 회원가입 API
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
            user_data['public'] = public_institution.public_id  
            #logger.debug(f"공공기관 조회 성공: {public_institution}")

            # 사용자 생성과 기관 및 부서 연결을 트랜잭션으로 처리
            with transaction.atomic():
                # department 이름으로 부서 조회 또는 생성
                department, created = Public_Department.objects.get_or_create(
                    department_name=department_name,
                    public=public_institution  # 이 부분에서 public_institution을 public 필드로 지정
                )
                #logger.debug(f"부서 생성/조회 성공: {department}, 생성 여부: {created}")

                # 사용자 생성
                user_serializer = PublicUserSerializer(data=user_data)
                
                # 사용자 데이터 검증
                if not user_serializer.is_valid():
                    #logger.debug(f"회원가입 유효성 검사 실패: {user_serializer.errors}")
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
            #logger.debug(f"Unhandled error: {e}")
            return Response({"error": "로그인 처리 중 문제가 발생했습니다. 관리자에게 문의하세요."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
               

# Other User APIs
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


# 비밀번호 재설정 API
class PasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone_number = request.data.get('phone')
        new_password = request.data.get('new_password')

        if not phone_number or not new_password:
            return Response({'success': False, 'message': '전화번호와 새 비밀번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        # 비밀번호 정규식 검증
        serializer = PublicPasswordCheckSerializer(data={'new_password': new_password})
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
        

# User Verification APIs
# 인증 코드 전송 API
class SendVerificationCodeView(APIView):
    permission_classes = [AllowAny]

    def generate_verification_code(self):
        # 6자리 인증 코드 생성
        return str(random.randint(100000, 999999))

    def post(self, request):
        # 요청 데이터 가져오기
        user_id = request.data.get('user_id')
        phone_number = request.data.get('phone')
        code_type = request.data.get('type')

        #logger.debug(f"phone_number: {phone_number}, code_type: {code_type}, user_id: {user_id}")

        # 필수 정보가 없으면 오류 반환
        if not phone_number or not code_type or (code_type not in ['findID', 'signup', 'complaint'] and not user_id):
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

        elif code_type == 'complaint':
            # 전화번호와 민원 번호로 민원 확인
            complaint_number = request.data.get('complaintNum')  # 추가된 필드
            if not complaint_number:
                return Response({'success': False, 'message': '민원 번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                user = Public_Complaint.objects.get(phone=phone_number, complaint_number=complaint_number)
            except Public_Complaint.DoesNotExist:
                return Response({'success': False, 'message': '해당 정보로 접수된 민원이 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

            
        else:
            # 회원가입 등 기타 경우: 전화번호 중복 확인
            if Public_User.objects.filter(phone=phone_number, is_active=True).exists():
                return Response({'success': False, 'message': '이미 가입된 전화번호입니다.'}, status=status.HTTP_400_BAD_REQUEST)

        # 인증 코드 생성 및 캐시에 저장
        cache_key = f'{code_type}_verification_code_{phone_number}'
        verification_code = self.generate_verification_code()
        cache.set(cache_key, verification_code, timeout=300)  # 항상 새 값 저장
        #logger.debug(f"New Verification Code Set: {verification_code}")



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

        # 입력받은 데이터 로깅
        #logger.debug(f"Received Data - phone_number: {phone_number}, entered_code: {entered_code}, code_type: {code_type}, user_id: {user_id}")
        #logger.debug(f"Request Data: {request.data}")
        
        # 필수 정보 확인
        if not phone_number or not code_type or (code_type not in ['findID', 'signup', 'complaint'] and not user_id):
            #logger.debug("필수 정보 누락")
            return Response({'success': False, 'message': '필수 정보(전화번호, 인증 번호, 사용자 ID)를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        # 캐시에서 인증 코드 가져오기
        cache_key = f'{code_type}_verification_code_{phone_number}'
        saved_code = cache.get(cache_key)
        #logger.debug(f"Cache Key: {cache_key}, Saved Code: {saved_code}")
        #logger.debug(f"Entered Code: {entered_code}")

        # 인증 코드 일치 확인
        if saved_code and str(saved_code).strip() == str(entered_code).strip():
            #logger.debug("Verification successful.")
            # 유형별 처리
            if code_type == 'mypage':
                try:
                    user = Public_User.objects.get(username=user_id)
                    user.phone = phone_number
                    user.save()
                    #logger.debug("전화번호 업데이트 완료")
                    return Response({'success': True, 'message': '인증이 완료되었으며, 전화번호가 업데이트되었습니다.'}, status=status.HTTP_200_OK)
                except Public_User.DoesNotExist:
                    #logger.debug("ID에 해당하는 사용자 없음")
                    return Response({'success': False, 'message': '해당 ID로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

            elif code_type in ['findID', 'findPW']:
                try:
                    user = Public_User.objects.get(phone=phone_number)
                    #logger.debug("사용자 정보 반환")
                    return Response({
                        'success': True,
                        'message': '인증이 완료되었습니다.',
                        'user_id': user.username,
                        'date_joined': user.created_at.strftime('%Y.%m.%d')
                    }, status=status.HTTP_200_OK)
                except Public_User.DoesNotExist:
                    #logger.debug("전화번호에 해당하는 사용자 없음")
                    return Response({'success': False, 'message': '해당 전화번호로 등록된 사용자가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
                
            elif code_type == 'complaint':
                # 전화번호와 민원 번호로 민원 확인
                complaint_number = request.data.get('complaintNum')  # 추가된 필드
                #logger.debug(f"complaintNum: {request.data.get('complaintNum')}")
                #logger.debug(f"complaint_number: {complaint_number}")


                if not complaint_number:
                    #logger.debug("Complaint number not provided.")
                    return Response({'success': False, 'message': '민원 번호를 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

                try:
                    user = Public_Complaint.objects.get(phone=phone_number, complaint_number=complaint_number)
                    #logger.debug(f"Complaint verification successful for complaint number: {complaint_number}")
                    return Response({'success': True, 'message': '민원이 확인되었습니다.', 'complaint': user.complaint_number}, status=status.HTTP_200_OK)
                except Public_Complaint.DoesNotExist:
                    #logger.debug(f"No complaint found for phone: {phone_number}, complaintNum: {complaint_number}")
                    return Response({'success': False, 'message': '해당 정보로 접수된 민원이 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
                
            elif code_type == 'signup':
                #logger.debug("회원가입 인증 성공")
                return Response({'success': True, 'message': '회원가입 인증이 완료되었습니다.'}, status=status.HTTP_200_OK)
            
        else:
            # 인증 실패 처리
            #logger.debug("인증 번호 불일치")
            return Response({'success': False, 'message': '인증 번호가 일치하지 않습니다.'}, status=status.HTTP_400_BAD_REQUEST)


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
        user.username = f'deleted_user_{user.user_id}'  # 사용자 아이디를 익명화
        user.phone = f'010-0000-0000_{user.user_id}'  # 핸드폰 번호 삭제 또는 익명화
        user.email = f'deleted_{user.user_id}@example.com'  # 이메일을 익명화
        user.name = '탈퇴한 사용자'  # 이름 익명화

        # 사용자 비활성화
        user.is_active = False
        user.deactivated_at = timezone.now()  # 비활성화 시간 기록
        user.save()

        # 사용자와 관련된 Edit 데이터 익명화
        self.anonymize_edits(user)

    
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

 