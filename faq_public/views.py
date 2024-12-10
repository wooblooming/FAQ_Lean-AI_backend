from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.conf import settings
from django.shortcuts import get_object_or_404 
from django.utils import timezone 
from .authentication import PublicUserJWTAuthentication
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
import requests, random, logging, json, os, shutil, qrcode
from exponent_server_sdk import PushClient, PushMessage
from .merged_csv import merge_csv_files
from .models import Public_User, Public, Public_Department, Public_Edit, Public_Complaint
from .serializers import (
    PublicUserSerializer, 
    PublicSerializer, 
    PublicRegisterSerializer,
    PublicUsernameCheckSerializer, 
    PublicPasswordCheckSerializer,
    PublicEditSerializer, 
    PublicComplaintSerializer,
    PublicDepartmentSerializer,
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


# Public Management APIs
# 공공기관 생성 API
class PublicCreateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # 임시로 로고를 제외하고 저장
        logo_file = request.FILES.get('logo', None)  # 로고 파일 별도로 저장
        register_serializer = PublicRegisterSerializer(data=request.data)

        if register_serializer.is_valid():
            try:
                # 데이터베이스에 저장
                public_instance = register_serializer.save()

                # 로고 파일 저장 (public_id가 생성된 후 저장 가능)
                if logo_file:
                    public_instance.logo = logo_file
                    public_instance.save()

                return Response(
                    {
                        "status": "success",
                        "message": "공공기관 정보가 성공적으로 등록되었습니다.",
                        "data": PublicSerializer(public_instance).data,
                    },
                    status=status.HTTP_201_CREATED,
                )
            except ValidationError as e:
                logger.error(f"Validation error during save: {str(e)}")
                return Response(
                    {"error": "데이터 저장 중 오류가 발생했습니다."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        logger.warning(f"Validation errors: {register_serializer.errors}")
        return Response(
            {"status": "error", "errors": register_serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


# 공공기관 및 사용자 출력 API
class UserPublicInfoView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):       
        try:
            # 인증이 통과되었으므로 request.user를 바로 사용할 수 있습니다.
            public_user = request.user

            if not public_user:
                return Response({"error": "가입된 사용자가 아닙니다."}, status=status.HTTP_404_NOT_FOUND)

            #logger.debug(f"Public User retrieved: {public_user}")

            public = public_user.public
            if not public:
                return Response({"error": "공공기관 정보가 없습니다."}, status=status.HTTP_404_NOT_FOUND)

            department = public_user.department
            department_data = {
                "department_id": department.department_id if department else "",
                "department_name": department.department_name if department else ""
            }

            user_data = PublicUserSerializer(public_user).data
            public_data = PublicSerializer(public).data

            response_data = {
                "user": user_data,
                "public": public_data,
                "department":department_data
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Public_User.DoesNotExist:
            logger.error("사용자가 faq_public_db에 존재하지 않습니다.")
            return Response({"error": "가입된 사용자가 아닙니다."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"서버 오류: {e}")
            return Response({"error": "서버 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 공공기관 출력 API
class PublicInfoView(APIView):
    permission_classes = [AllowAny]  # 기본적으로 인증 없이 접근 가능

    def dispatch(self, request, *args, **kwargs):
        data = json.loads(request.body)
        user_type = data.get('type')  # JSON 본문에서 'type'을 추출합니다.
        #logger.debug(f"Received type: {user_type}, slug: {slug}")


        if user_type == 'owner':
            self.authentication_classes = [PublicUserJWTAuthentication]
            self.permission_classes = [IsAuthenticated]

        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        # 요청에서 'type'과 'slug' 가져오기
        data = json.loads(request.body)
        slug = data.get('slug')
        #logger.debug(f"Post method - Received type: {user_type}, slug: {slug}")

        try:
            # slug에 해당하는 공공기관 정보 가져오기
            public = Public.objects.get(slug=slug)
            #logger.debug(f"Public institution found: {public}")

            # 공공기관 데이터 직렬화
            public_data = PublicSerializer(public).data

            # 응답 데이터 생성
            response_data = {
                "public": public_data
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Public.DoesNotExist:
            logger.error(f"No public institution found for slug: {slug}")
            return Response({"error": "해당 공공기관 정보를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Server error occurred: {str(e)}")
            return Response({"error": "서버 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        #logger.debug(f"Received public_id: {public_id}")
        
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
            #logger.debug(f"Fetched institution details: {serializer.data}")
            
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except Public.DoesNotExist:
            # 해당 ID의 기관이 없는 경우 오류 반환
            logger.error(f"기관 ID {public_id}에 해당하는 기관이 없습니다.")
            return Response({"error": "해당 기관을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)


# 공공기관에 있는 모든 부서 출력 API
class DepartmentListView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            slug = request.data.get('slug')
            public_id = request.data.get('publicID')

            if not slug and not public_id:
                return Response({'error': 'slug 또는 publicID 중 하나를 제공해야 합니다.'}, status=400)

            if public_id:
                # publicID를 기반으로 Public_Department 찾기
                departments = list(
                    Public_Department.objects.filter(public_id=public_id)
                    .values_list('department_name', flat=True)
                    .distinct()
                )
            elif slug:
                # slug를 기반으로 Public 객체 찾기
                public = Public.objects.filter(slug=slug).first()
                if not public:
                    return Response({'error': '해당 slug에 일치하는 Public이 없습니다.'}, status=404)

                # slug에 해당하는 Public의 Public_Department 찾기
                departments = list(
                    Public_Department.objects.filter(public=public)
                    .values_list('department_name', flat=True)
                    .distinct()
                )

            # '기타' 항목 추가
            if '기타' not in departments:
                departments.append('기타')

            # 부서가 존재할 경우와 없는 경우 응답 구분
            if departments:
                return Response({'departments': list(departments)}, status=200)
            else:
                return Response({'message': '해당 public_id 또는 slug에 대한 부서가 없습니다.'}, status=404)

        except Exception as e:
            return Response({'error': str(e)}, status=500)


# 부서 생성 API
class DepartmentCreateAPIView(APIView):
    def post(self, request):
        department_name = request.data.get('department_name')
        public_id = request.data.get('public_id')

        if not department_name or not public_id:
            return Response(
                {"error": "부서 이름과 공공기관 ID는 필수입니다."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            public = Public.objects.get(public_id=public_id)
        except Public.DoesNotExist:
            return Response(
                {"error": "유효하지 않은 공공기관 ID입니다."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # 부서 생성
        department = Public_Department.objects.create(department_name=department_name, public=public)
        serializer = PublicDepartmentSerializer(department)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# 사용자 부서 이동 API
class DepartmentUpdateView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        user = request.user
        department_name = request.data.get("department_name")
        public_id = request.data.get("public_id")

        # 요청 데이터 검증
        if not department_name or not public_id:
            return Response(
                {"error": "부서와 공공기관 ID는 필수 항목입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 부서가 해당 공공기관에 존재하는지 확인
            department = Public_Department.objects.get(department_name=department_name, public_id=public_id)

            # 현재 부서와 동일한지 확인
            if user.department == department:
                return Response(
                    {"error": "현재 선택된 부서와 동일합니다."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 유효한 경우 사용자 부서 업데이트
            user.department = department
            user.save()
            return Response({"message": "부서가 성공적으로 변경되었습니다."}, status=status.HTTP_200_OK)

        except Public_Department.DoesNotExist:
            return Response(
                {"error": "해당 부서는 존재하지 않습니다."},
                status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            return Response(
                {"error": f"예상치 못한 오류가 발생했습니다: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
            # 요청 데이터 로깅
            #logger.debug(f"Request data: {request.data}")
            #logger.debug(f"Request user: {request.user}")

            public_id = request.data.get('public_id')  # 요청에서 public_id 가져오기
            if not public_id:
                #logger.debug("public_id가 요청에 없습니다.")
                return Response({'error': 'public_id가 필요합니다.'}, status=400)

            # 사용자의 스토어 정보 가져오기
            public = Public.objects.get(public_id=public_id, public_users=request.user)
            #logger.debug(f"Public object found: {public}")

            if public.qr_code:
                public_name = public.public_name
                qr_code_path = public.qr_code.lstrip('/')  # 경로에서 앞의 '/' 제거
                #logger.debug(f"QR code path: {qr_code_path}")

                if qr_code_path.startswith('media/'):
                    qr_code_url = request.build_absolute_uri(f'/{qr_code_path}')
                else:
                    qr_code_url = request.build_absolute_uri(settings.MEDIA_URL + qr_code_path)

                qr_content_url = f'https://mumulai.com/publicIntroduction/{public.slug}'

                #logger.debug(f"QR code URL: {qr_code_url}, Content URL: {qr_content_url}")

                return Response({
                    'public_name': public_name,
                    'qr_code_image_url': qr_code_url,
                    'qr_content_url': qr_content_url
                }, status=200)
            else:
                #logger.debug("QR 코드가 없습니다.")
                return Response({'qr_code_image_url': None}, status=200)

        except Public.DoesNotExist:
            #logger.debug(f"Public object not found for public_id: {public_id}, user: {request.user}")
            return Response({'error': 'public not found'}, status=404)
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)  # 예외 정보 전체 로깅
            return Response({'error': 'An unexpected error occurred.'}, status=500)


# User Profile APIs
# 사용자 프로필 업데이트 API
class UserProfileView(APIView):
    # 이 뷰는 인증된 사용자만 접근할 수 있도록 설정
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        user = request.user
        logger.debug(f"UserProfileView POST called by user: {user}")

        try:
            public = Public.objects.filter(public_users=user).first()
            logger.debug(f"Store found for user {user.username}: {store}")
        except Public.DoesNotExist:
            public = None
            logger.debug(f"No store found for user {user.username}")

        profile_photo_url = user.profile_photo.url if user.profile_photo else "/media/profile_photos/profile_default_img.jpg"
        qr_code_url = public.qr_code if public and public.qr_code else ""
        logo_url = public.logo.url if public and public.logo else ""

        response_data = {
            'profile_photo': profile_photo_url,
            'name': user.name,
            'email': user.email,
            'phone_number': user.phone,
            'business_name': public.public_name if public else '',
            'business_address': public.public_address if public else '',
            'user_id': user.username,
            'qr_code_url': qr_code_url,
            'logo_url': logo_url,
            'marketing': user.marketing,
            'department': {
                "department_id": user.department.department_id if user.department else "",
                "department_name": user.department.department_name if user.department else ""
            }
        }
        logger.debug(f"Response data: {response_data}")

        return Response(response_data)


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
                # 현재 부서와 요청한 부서가 동일한지 확인
                current_department = user.department.department_name if user.department else None
                if current_department == department_name:
                    return Response({
                        'error': '현재 부서와 동일한 부서로 이동할 수 없습니다.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                try:
                    department, created = Public_Department.objects.get_or_create(
                        department_name=department_name,
                        public=public
                    )
                    user.department = department
                except Exception as e:
                    logger.error(f"부서 생성 또는 가져오기 실패: {e}")
                    return Response({
                        'error': '부서 생성 중 문제가 발생했습니다.'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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


# Statistics APIs
class StatisticsView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
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
                "data": most_common_utterances,
                "image_url": f"/media/statistics/{request.user.user_id}/most_common_utterances.png"
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            # 오류 메시지 로그 출력
            logger.error(f"오류 발생: {str(e)}")
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Service APIs
# 요청 사항 등록 API
class RequestServiceView(APIView):
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
                    #logger.debug(f"에러 메시지 : {edit_serializer.errors}")
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
                #logger.debug(f"에러 메시지 : {edit_serializer.errors}")
                return Response(edit_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(saved_data, status=status.HTTP_201_CREATED)



# Complaint Management APIs
# 민원 출력 API
class ComplaintsView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        user = request.user

        if not user.is_authenticated:
            return Response({"error": "인증되지 않은 사용자입니다."}, status=status.HTTP_401_UNAUTHORIZED)

        public = user.public
        if not public:
            return Response({"error": "해당 사용자는 매장이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        # 사용자의 부서 가져오기
        user_department = user.department
        if not user_department:
            return Response({"error": "사용자가 속한 부서가 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        # 요청된 publicID 확인
        user_public_id = public.public_id
        request_public_id = request.data.get('publicID')

        if str(user_public_id) != str(request_public_id):
            return Response({"error": "권한이 없습니다."}, status=status.HTTP_403_FORBIDDEN)

        # 사용자가 속한 부서의 민원만 가져오기
        complaints = Public_Complaint.objects.filter(
            public_id=request_public_id,
            department=user_department
        )

        serializer = PublicComplaintSerializer(complaints, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# 민원인 측 민원 출력 API
class ComplaintsCustomerView(APIView):
    permission_classes = [AllowAny]  # 인증된 사용자만 접근 가능

    def post(self, request):
        # 요청에서 접수번호와 핸드폰 번호 가져오기
        complaint_number = request.data.get("complaint_number")
        phone = request.data.get("phone")

        if not complaint_number:
            return Response({"success": False, "message": "접수번호를 입력해 주세요."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 접수번호와 핸드폰 번호로 민원 조회
            complaint = get_object_or_404(Public_Complaint, complaint_number=complaint_number, phone=phone)

            # 민원 데이터 JSON 응답
            return Response({
                "success": True,
                "complaint": {
                    "complaint_number": complaint.complaint_number,
                    "title": complaint.title,
                    "name": complaint.name,  # 작성자 이름 필드
                    "created_at": complaint.created_at.strftime("%Y-%m-%d"),
                    "status": complaint.status,
                    "content": complaint.content,  # 민원 내용
                    "answer" : complaint.answer
                }
            }, status=status.HTTP_200_OK)
        
        except Public_Complaint.DoesNotExist:
            return Response({"success": False, "message": "해당 접수번호와 핸드폰 번호에 해당하는 민원이 없습니다."}, status=status.HTTP_404_NOT_FOUND)


# 민원 등록 API
class ComplaintsRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        data = request.data.copy()
        slug = data.get('slug')

        if not slug:
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            public = Public.objects.get(slug=slug)
            data['public'] = public.public_id

        except Public.DoesNotExist:
            return Response({"status": "error", "message": "공공기관이 유효하지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)
        
        # department 설정
        department_name = data.get('department')
        if department_name == '기타':
            department, created = Public_Department.objects.get_or_create(
                department_name='기타',
                public=public
            )
            data['department'] = department.department_id
        elif department_name:
            try:
                department = Public_Department.objects.get(department_name=department_name, public=public)
                data['department'] = department.department_id
            except Public_Department.DoesNotExist:
                return Response({"status": "error", "message": f"{department_name} 부서를 찾을 수 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 데이터를 시리얼라이저에 할당 후 저장
        serializer = PublicComplaintSerializer(data=data)
        
        if serializer.is_valid():
            complaint = serializer.save()
            complaint_number = complaint.complaint_number
            phone_number = complaint.phone

            # 민원 등록자에게 SMS 전송
            sms_data = {
                'key': settings.ALIGO_API_KEY,
                'user_id': settings.ALIGO_USER_ID,
                'sender': settings.ALIGO_SENDER,
                'receiver': phone_number,
                'msg': f'안녕하세요, 접수하신 민원의 접수번호는 [{complaint_number}]입니다.',
                'testmode_yn': 'Y',
            }

            try:
                # 민원 등록자에게 SMS 전송
                response = requests.post('https://apis.aligo.in/send/', data=sms_data)
                response_data = response.json()

                if response_data.get('result_code') != '1':
                    logger.error(f"SMS 전송 실패: {response_data.get('message')}")
                    return Response({"status": "error", "message": "민원이 접수되었지만 SMS 전송에 실패했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                # 부서 사용자들에 대한 문자 알림 전송
                department_users = Public_User.objects.filter(department=department)
                for user in department_users:
                    department_sms_data = {
                        'key': settings.ALIGO_API_KEY,
                        'user_id': settings.ALIGO_USER_ID,
                        'sender': settings.ALIGO_SENDER,
                        'receiver': user.phone,
                        'msg': f'[{department_name}] 부서에 새 민원이 접수되었습니다. 접수번호: [{complaint_number}]',
                        'testmode_yn': 'Y',
                    }

                    try:
                        dept_response = requests.post('https://apis.aligo.in/send/', data=department_sms_data)
                        dept_response_data = dept_response.json()
                        if dept_response_data.get('result_code') != '1':
                            logger.error(f"부서 알림 SMS 전송 실패: {dept_response_data.get('message')}")
                    except requests.RequestException as e:
                        logger.error(f"부서 알림 SMS 전송 중 오류 발생: {str(e)}")

                return Response(
                    {"status": "success", "message": "민원이 성공적으로 접수되었습니다.", 
                     "complaint_number": complaint_number, "public_slug": public.slug},
                    status=status.HTTP_201_CREATED
                )

            except requests.RequestException as e:
                logger.error(f"SMS 전송 중 오류 발생: {str(e)}")
                return Response({"status": "error", "message": "민원이 접수되었지만 SMS 전송에 실패했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        else:
            logger.error(f"민원 접수 실패: 유효하지 않은 데이터 - {serializer.errors}")
            return Response({"status": "error", "message": "유효하지 않은 데이터", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


# 민원 상태 변경 API
class ComplaintUpdateStatusView(APIView):
    permission_classes = [AllowAny]

    def patch(self, request, id, *args, **kwargs): 
        try:
            # ID로 민원 검색
            complaint = Public_Complaint.objects.get(complaint_id=id)  
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
                    'msg': f'안녕하세요, [{complaint.title}]의 민원 처리가 완료되었습니다. ',
                    'testmode_yn': 'Y',  # 테스트 모드 활성화 (실제 발송 시 'N'으로 변경)
                }

                response = requests.post('https://apis.aligo.in/send/', data=sms_data)
                response_data = response.json()

                #logger.debug(f"SMS 전송 데이터: {sms_data}")

                if response_data.get('result_code') != '1':
                    logger.error(f"SMS 전송 실패: {response_data.get('message')}")
                    return Response({"status": "error", "message": "상태는 업데이트되었지만 SMS 전송에 실패했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({"status": "success", "message": f"민원 상태가 '{new_status}'로 업데이트되었습니다."}, status=status.HTTP_200_OK)

        except Public_Complaint.DoesNotExist:
            return Response({"status": "error", "message": "해당 ID의 민원을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"민원 상태 업데이트 중 오류 발생: {str(e)}")
            return Response({"status": "error", "message": "민원 상태 업데이트 중 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 민원 부서 이관 API 
class ComplaintTransferView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # 인증된 사용자 정보 가져오기
            user = request.user
            user_public = user.public

            # 요청 데이터 확인
            complaint_id = request.data.get('complaint_id')
            department_name = request.data.get('department')
            reason = request.data.get('reason')

            if not all([complaint_id, department_name, reason]):
                return Response({'error': '모든 필드를 입력해야 합니다.'}, status=status.HTTP_400_BAD_REQUEST)

            # Public_Complaint 객체 가져오기
            try:
                complaint = Public_Complaint.objects.get(complaint_id=complaint_id, public=user_public)
            except Public_Complaint.DoesNotExist:
                return Response({'error': '민원을 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

            # Public_Department 객체 가져오기
            try:
                new_department = Public_Department.objects.get(
                    department_name=department_name,
                    public=user_public
                )
            except Public_Department.DoesNotExist:
                return Response(
                    {'error': f"부서 '{department_name}'를 {user_public}에서 찾을 수 없습니다."},
                    status=status.HTTP_404_NOT_FOUND
                )
            except Public_Department.MultipleObjectsReturned:
                return Response(
                    {'error': f"'{department_name}' 부서가 중복되어 정확히 찾을 수 없습니다."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 현재 부서와 선택된 부서 비교
            if complaint.department == new_department:
                return Response(
                    {'error': '현재 부서와 동일한 부서로 이관할 수 없습니다.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 부서 업데이트
            previous_department = complaint.department.department_name
            complaint.department = new_department
            complaint.transfer_reason = reason
            complaint.save()

            # 문자 메시지 발송
            # 이관한 부서의 유저들을 대상으로 알림 발송
            users_in_new_department = Public_User.objects.filter(public=user_public, department=new_department)
            receiver_numbers = [user.phone for user in users_in_new_department if user.phone]

            if not receiver_numbers:
                return Response(
                    {"status": "error", "message": "이관된 부서에 유효한 전화번호가 있는 사용자가 없습니다."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            sms_data = {
                'key': settings.ALIGO_API_KEY,
                'user_id': settings.ALIGO_USER_ID,
                'sender': settings.ALIGO_SENDER,
                'receiver': ','.join(receiver_numbers),
                'msg': f'[{previous_department}]에서 [{new_department.department_name}]로 민원을 이관하였습니다.',
                'testmode_yn': 'Y',  # 테스트 모드 활성화 (실제 발송 시 'N'으로 변경)
            }

            response = requests.post('https://apis.aligo.in/send/', data=sms_data)
            response_data = response.json()

            if response_data.get('result_code') != '1':
                logger.error(f"SMS 전송 실패: {response_data.get('message')}")
                return Response(
                    {"status": "error", "message": "민원은 이관되었지만 SMS 전송에 실패했습니다."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            return Response({'success': True, 'message': '민원이 성공적으로 이관되었습니다.'}, status=status.HTTP_200_OK)

        except Public_Complaint.DoesNotExist:
            return Response({'error': '해당 민원을 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"민원 이관 중 오류 발생: {str(e)}")
            return Response(
                {"status": "error", "message": "민원 이관 중 오류가 발생했습니다."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# 민원 답변 API
class ComplaintAnswerView(APIView):
    authentication_classes = [PublicUserJWTAuthentication]  # 커스텀 인증 클래스 사용
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        try:
            # 요청 데이터 확인
            #logger.debug(f"Request data: {request.data}")
            complaint_id = request.data.get('complaint_id')
            answer=request.data.get('answer')

            # Public_Complaint 객체 가져오기
            try:
                complaint = Public_Complaint.objects.get(complaint_id=complaint_id)
                #logger.debug(f"Complaint found: {complaint}")
            except Public_Complaint.DoesNotExist:
                #logger.debug("Complaint not found.")
                return Response({'error': '민원을 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

            # 답변 저장
            complaint.answer = answer
            complaint.save()
            #logger.debug(f"Answer saved: {answer}")

            # 작성자의 핸드폰 번호 확인
            phone_number = complaint.phone  # 민원 작성자의 핸드폰 번호
            if not phone_number:
                #logger.debug("Phone number not found.")
                return Response({'error': '민원 작성자의 핸드폰 번호가 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Aligo API를 통한 문자 발송 데이터 준비
            sms_data = {
                'key': settings.ALIGO_API_KEY,  # Aligo API 키
                'user_id': settings.ALIGO_USER_ID,  # Aligo 사용자 ID
                'sender': settings.ALIGO_SENDER,  # 발신자 번호
                'receiver': phone_number,  # 수신자 번호
                'msg': f'안녕하세요, {complaint.title} 민원에 대한 답변이 등록되었습니다.',  # 메시지 내용
                'testmode_yn': 'Y',  # 테스트 모드 (실제 전송 시 'N'으로 설정)
            }

            # Aligo API 호출
            response = requests.post('https://apis.aligo.in/send/', data=sms_data)

            # Aligo API 응답 확인
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('result_code') == '1':  # Aligo 성공 코드
                    #logger.debug("SMS sent successfully.")
                    return Response({'success': '문자가 성공적으로 발송되었습니다.'}, status=status.HTTP_200_OK)
                else:
                    #logger.debug(f"Aligo error: {response_data.get('message')}")
                    return Response({'error': response_data.get('message')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                #logger.debug(f"HTTP error: {response.status_code}")
                return Response({'error': '문자 발송 중 오류가 발생했습니다.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            #logger.debug(f"Unexpected error: {str(e)}")
            return Response({'error': '예기치 못한 오류가 발생했습니다.', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Push Notification APIs
# 사용자 푸시 토큰 저장 API
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


# 사용자에게 푸시 알림 전송 API
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


# Deactivate Account APIs
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
        user.phone = f'000-0000-0000_{user.user_id}'  # 핸드폰 번호 삭제 또는 익명화
        user.email = f'deleted_{user.user_id}@example.com'  # 이메일을 익명화
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
        publics = Public.objects.filter(public_users=user)
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
        user_folder_path = os.path.join(settings.MEDIA_ROOT, 'uploads', str(user.user_id))
        
        # 폴더가 존재하면 삭제
        if os.path.exists(user_folder_path):
            shutil.rmtree(user_folder_path)

 