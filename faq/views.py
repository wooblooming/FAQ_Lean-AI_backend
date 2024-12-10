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
import requests, random, logging, json, os, shutil, uuid , qrcode
from exponent_server_sdk import PushClient, PushMessage
from .merged_csv import merge_csv_files
from .excel_processor import process_excel_and_save_to_db
from .models import User, Store, Edit, Menu
from .serializers import (
    UserSerializer, StoreSerializer, UsernameCheckSerializer, 
    PasswordCheckSerializer, EditSerializer, MenuSerializer
)

logger = logging.getLogger('faq')

# Helper Function for Menu Price Update
def update_menu_price_field(store):
    menus = Menu.objects.filter(store=store)
    menu_price_data = [
        {
            'name': menu.name,
            'price': float(menu.price),
            'category': menu.category,
            'image': str(menu.image.url) if menu.image else None,
            'allergy': menu.allergy if menu.allergy is not None else ""
        }
        for menu in menus
    ]
    store.menu_price = json.dumps(menu_price_data, ensure_ascii=False)
    store.save()


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


# Store Management APIs
# 매장 정보 반환 API
class StoreView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = json.loads(request.body)
        slug = data.get('slug')
        store_id = data.get('store_id')

        try:
            if store_id:
                store = Store.objects.get(store_id=store_id)
            elif slug:
                store = Store.objects.get(slug=slug)
            else:
                return Response({'error': 'store_id 또는 slug가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

            store_data = StoreSerializer(store).data
            return Response({'store': store_data}, status=status.HTTP_200_OK)

        except Store.DoesNotExist:
            return Response({'error': '해당 매장 정보를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"스토어 조회 오류: {str(e)}")
            return Response({'error': '서버 오류 발생'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StoreUpdateView(APIView):
    authentication_classes = [JWTAuthentication] 
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def put(self, request, store_id):
        logger.debug(f"StoreUpdateView PUT called with store_id: {store_id}")
        logger.debug(f"Request user: {request.user}")
        logger.debug(f"Request data: {request.data}")

        # 주어진 store_id, 사용자로 스토어 정보 가져오기
        try:
            store = Store.objects.get(store_id=store_id, user=request.user)
            logger.debug(f"Store found: {store.store_name}")
        except Store.DoesNotExist:
            logger.error(f"Store with store_id {store_id} not found for user {request.user}")
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        
        # 배너 필드가 빈 문자열인 경우 null로 처리
        if 'banner' in data and data['banner'] == '':
            logger.debug("Banner field is empty, setting it to None")
            data['banner'] = None

        logger.debug(f"Data after processing: {data}")

        serializer = StoreSerializer(store, data=data, partial=True)
        if serializer.is_valid():
            logger.debug(f"Validated data: {serializer.validated_data}")
            store = serializer.save()
            logger.debug(f"Store introduction after save: {store.store_introduction}")  # 저장 후 값 확인
            logger.debug(f"Store updated successfully: {store.store_name}")
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            logger.error(f"Validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



# QR 코드 생성 하는 API
class GenerateQrCodeView(APIView):
    authentication_classes = [JWTAuthentication] 
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        store_id = request.data.get('store_id')  # 요청에서 store_id 받기
        #logger.debug(f"Request data store_id: {store_id}")

        if not store_id:
            #logger.debug("No store_id provided in the request")
            return Response({'error': '스토어 ID가 필요합니다.'}, status=400)

        try:
            # 주어진 store_id로 스토어 정보 가져오기
            store = Store.objects.get(store_id=store_id, user=request.user)
            #logger.debug(f"Store found for store_id: {store_id}, user: {request.user.username}")
        except Store.DoesNotExist:
            #logger.debug(f"Store not found for store_id: {store_id}, user: {request.user.username}")
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=404)

        qr_url = f'https://mumulai.com/storeIntroduction/{store.slug}'
        #logger.debug(f"QR Content URL to encode: {qr_url}")

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
            qr_directory = os.path.join(settings.MEDIA_ROOT, 'qr_codes')
            qr_path = os.path.join(qr_directory, qr_filename)

            #logger.debug(f"QR code directory path: {qr_directory}")
            #logger.debug(f"QR code file path: {qr_path}")

            # 디렉토리가 없으면 생성
            if not os.path.exists(qr_directory):
                os.makedirs(qr_directory)
                #logger.debug(f"QR code directory created at: {qr_directory}")

            # QR 코드 이미지 저장
            img = qr.make_image(fill='black', back_color='white')
            img.save(qr_path)
            #logger.debug(f"QR code image saved at: {qr_path}")

            # 데이터베이스에 QR 코드 경로를 저장
            store.qr_code = f'/media/qr_codes/{qr_filename}'
            store.save()
            #logger.debug(f"Store updated with QR code path: {store.qr_code}")

            return Response({
                'message': 'QR 코드가 성공적으로 생성되었습니다.',
                'qr_code_url': store.qr_code,  # 저장된 경로 반환
                'qr_content_url': qr_url  # QR 코드에 인코딩된 실제 URL 반환
            }, status=201)
        except Exception as e:
            logger.error(f"Error while generating QR code: {e}")
            return Response({'error': '서버 내부 오류가 발생했습니다. 관리자에게 문의하세요.'}, status=500)


# QR 코드 이미지를 반환하는 API
class QrCodeImageView(APIView):
    authentication_classes = [JWTAuthentication] 
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        try:
            # 사용자의 스토어 정보 가져오기
            store = Store.objects.get(user=request.user)
            #logger.debug(f"Store found for user: {request.user.username}, store name: {store.store_name}")

            if store.qr_code:
                #logger.debug(f"Store has QR code: {store.qr_code}")

                # QR 코드 경로 처리
                qr_code_path = store.qr_code.lstrip('/')  # 앞의 '/' 제거
                if qr_code_path.startswith('media/'):
                    qr_code_url = request.build_absolute_uri(f'/{qr_code_path}')
                else:
                    qr_code_url = request.build_absolute_uri(settings.MEDIA_URL + qr_code_path)

                #logger.debug(f"Final QR code URL: {qr_code_url}")

                # QR 코드에 인코딩된 실제 URL 생성
                qr_content_url = f'https://mumulai.com/storeIntroduction/{store.slug}'
                #logger.debug(f"QR Content URL: {qr_content_url}")

                return Response({
                    'store_name': store.store_name,
                    'qr_code_image_url': qr_code_url,
                    'qr_content_url': qr_content_url
                }, status=200)
            else:
                logger.debug(f"No QR code found for store: {store.store_name}")
                return Response({'qr_code_image_url': None}, status=200)

        except Store.DoesNotExist:
            logger.debug(f"Store not found for user: {request.user.username}")
            return Response({'error': 'Store not found'}, status=404)
        except Exception as e:
            logger.error(f"Unexpected error occurred in QrCodeImageView: {e}")
            return Response({'error': 'An unexpected error occurred.'}, status=500)

# Menu Management APIs
class MenuListView(APIView):
    authentication_classes = [JWTAuthentication] 
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

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
            store_id = request.data.get('store_id')
            type_ = request.data.get('type')  # type을 받음, 기본값은 'owner'
            return self.view_menus(request, slug, store_id, type_)

        if action == 'view_category':  
            slug = request.data.get('slug')
            return self.view_category(request, slug)  # view_category 호출

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

    
    def create_menus(self, request, menus):
        """
        메뉴 생성 
        """
        if not request.user.is_authenticated:
            return Response({'error': '인증이 필요합니다.'}, status=status.HTTP_401_UNAUTHORIZED)

        created_menus = []
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

                menu_data['store'] = store.store_id
                menu_data['menu_number'] = new_menu_number

                serializer = MenuSerializer(data=menu_data)
                if serializer.is_valid():
                    menu = serializer.save()
                    created_menus.append(serializer.data)
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Store의 menu_price 필드 업데이트
            update_menu_price_field(store)

        return Response({'created_menus': created_menus}, status=status.HTTP_201_CREATED)

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
    
    def update_menus(self, request, menus):
        """
        메뉴 수정
        """
        updated_menus = []

        with transaction.atomic():  # 트랜잭션 시작
            for menu_data in menus:
                store_slug = unquote(menu_data.get('slug'))
                menu_number = menu_data.get('menu_number')

                try:
                    store = Store.objects.get(slug=store_slug, user=request.user)
                except Store.DoesNotExist:
                    return Response(
                        {'error': f'{store_slug}에 해당하는 스토어를 찾을 수 없습니다.'},
                        status=status.HTTP_404_NOT_FOUND
                    )

                try:
                    menu = Menu.objects.get(store=store, menu_number=menu_number)
                except Menu.DoesNotExist:
                    return Response(
                        {'error': f'{menu_number}에 해당하는 메뉴를 찾을 수 없습니다.'},
                        status=status.HTTP_404_NOT_FOUND
                    )

                # 이미지 처리: 이미지가 전송되지 않았으면 기존 이미지 유지
                if 'image' not in menu_data or not menu_data.get('image'):
                    menu_data['image'] = menu.image  # 기존 이미지 유지

                # 메뉴 데이터를 업데이트
                serializer = MenuSerializer(menu, data=menu_data, partial=True)
                if serializer.is_valid():
                    updated_menu = serializer.save()
                    updated_menus.append(serializer.data)
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Store의 menu_price 필드 업데이트 (필요 시)
            update_menu_price_field(store)

        return Response({'updated_menus': updated_menus}, status=status.HTTP_200_OK)

    def view_menus(self, request, slug, store_id, type_):
        """
        특정 스토어의 메뉴 목록을 조회
        """
        try:
            if slug:
                store = Store.objects.get(slug=slug)
            elif store_id:
                store = Store.objects.get(store_id=store_id)
            else:
                return Response({'error': 'slug 또는 store_id가 제공되지 않았습니다.'}, status=status.HTTP_400_BAD_REQUEST)
        except Store.DoesNotExist:
            return Response({'error': '해당 스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

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
        try:
            # 인증되지 않은 사용자 처리
            if not request.user.is_authenticated:
                store = Store.objects.get(slug=slug)
            else:
                store = Store.objects.get(slug=slug, user=request.user)
        except Store.DoesNotExist:
            return Response(
                {'error': f'{slug}에 해당하는 스토어를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # store와 연결된 메뉴를 필터링하여 메뉴 목록 가져오기
        menus = Menu.objects.filter(store=store)

        # 메뉴에서 카테고리 리스트 추출 및 중복 제거
        categories = menus.values_list('category', flat=True).distinct()

        # 카테고리 옵션 변환
        category_options = [{'value': category, 'label': category} for category in categories if category]

        return Response(category_options, status=status.HTTP_200_OK)





# Feed Management APIs
# 피드 이미지 목록을 조회 API
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


# 피드 이미지를 업로드 API
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


# 피드 이미지를 삭제 API
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
    

# 피드 이미지 이름을 변경 API
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


# Statistics APIs
# FAQ 통계 API
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


# Service and Data APIs
# 매장 정보 등록 API
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


# User Profile APIs
# 사용자 프로필 조회 및 업데이트 API
class UserProfileView(APIView):
    # 이 뷰는 인증된 사용자만 접근할 수 있도록 설정
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]  # 인증된 사용자만 접근 가능

    def post(self, request):
        user = request.user
        logger.debug(f"UserProfileView POST called by user: {user}")

        try:
            store = Store.objects.get(user=user)
            logger.debug(f"Store found for user {user.username}: {store}")
        except Store.DoesNotExist:
            store = None
            logger.debug(f"No store found for user {user.username}")

        profile_photo_url = user.profile_photo.url if user.profile_photo else ""
        qr_code_url = store.qr_code if store and store.qr_code else ""
        banner_url = store.banner.url if store and store.banner else ""

        response_data = {
            'profile_photo': profile_photo_url,
            'name': user.name,
            'email': user.email,
            'phone_number': user.phone,
            'business_name': store.store_name if store else '',
            'business_address': store.store_address if store else '',
            'user_id': user.username,
            'qr_code_url': qr_code_url,
            'banner_url': banner_url,
            'marketing': user.marketing,
        }
        logger.debug(f"Response data: {response_data}")

        return Response(response_data)


    def put(self, request):
        user = request.user
        data = request.data
        logger.debug(f"UserProfileView PUT called by user: {user} with data: {data}")

        user.name = data.get('name', user.name)
        user.email = data.get('email', user.email)
        user.phone = data.get('phone_number', user.phone)
        user.marketing = data.get('marketing', user.marketing)
        user.save()
        logger.debug(f"User profile updated for user {user.username}")

        try:
            store = Store.objects.get(user=user)
            logger.debug(f"Store found for user {user.username}: {store}")
        except Store.DoesNotExist:
            store = None
            logger.debug(f"No store found for user {user.username}")

        if store:
            store.store_name = data.get('business_name', store.store_name)
            store.store_address = data.get('business_address', store.store_address)
            store.save()
            logger.debug(f"Store updated for user {user.username}: {store}")

        response_data = {
            'message': 'User profile updated successfully',
            'profile_photo': user.profile_photo.url if user.profile_photo else "/media/profile_default_img.jpg",
            'name': user.name,
            'user_id': user.username,
            'email': user.email,
            'phone_number': user.phone,
            'business_name': store.store_name if store else "",
            'business_address': store.store_address if store else "",
            'marketing': user.marketing,
            'store_introduction': store.store_introduction if store else '',
        }
        logger.debug(f"Response data after update: {response_data}")

        return Response(response_data, status=status.HTTP_200_OK)



class UserProfilePhotoUpdateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        logger.debug(f"UserProfilePhotoUpdateView POST called by user: {user}")

        # 요청에서 파일 가져오기
        profile_photo = request.FILES.get('profile_photo', None)

        if profile_photo:
            # 새 이미지 파일 업로드
            user.profile_photo = profile_photo
            logger.debug(f"Profile photo updated for user {user.username}: {profile_photo.name}")
        else:
            profile_photo_url = request.data.get('profile_photo')
            if profile_photo_url == "default":
                # 기본 이미지로 설정
                default_image_path = os.path.join(settings.MEDIA_ROOT, "profile_photos/profile_defalut.jpg")
                if os.path.exists(default_image_path):
                    with open(default_image_path, "rb") as f:
                        user.profile_photo.save("profile_default.jpg", f)
                    logger.debug(f"Profile photo for user {user.username} set to default.")
                else:
                    logger.error(f"Default image not found at {default_image_path}")
                    return Response(
                        {"error": "기본 이미지를 찾을 수 없습니다."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                logger.debug(f"No profile photo provided for user {user.username}.")

        user.save()

        # 응답 데이터 생성
        response_data = {
            "message": "프로필 사진이 성공적으로 업데이트되었습니다.",
            "profile_photo_url": user.profile_photo.url if user.profile_photo else None,
        }
        logger.debug(f"Response data: {response_data}")

        return Response(response_data, status=status.HTTP_200_OK)



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
        # 사용자 파일이 저장된 경로
        user_folder_path = os.path.join(settings.MEDIA_ROOT, 'uploads', str(user.user_id))
        
        # 폴더가 존재하면 삭제
        if os.path.exists(user_folder_path):
            shutil.rmtree(user_folder_path)

