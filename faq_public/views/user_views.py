# user_views.py
# 사용자 프로필 관리, 푸시 알림
from django.conf import settings
from ..authentication import PublicUserJWTAuthentication
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import logging, os
from exponent_server_sdk import PushClient, PushMessage
from ..models import Public, Public_Department

# 디버깅을 위한 로거 설정
logger = logging.getLogger('faq')

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
            logger.debug(f"Store found for user {user.username}")
        except Public.DoesNotExist:
            public = None
            logger.debug(f"No store found for user {user.username}")

        profile_photo_url = user.profile_photo.url if user.profile_photo else ""
        qr_code_path = os.path.join(settings.MEDIA_ROOT, f"qr_codes/public_qr_{public.public_id}.png") if public else None
        qr_code_url = (
            f"/media/qr_codes/qr_{public.public_id}.png"
            if qr_code_path and os.path.exists(qr_code_path)
            else ""
        )
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
        department_name = data.get('department_name') 
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
            'profile_photo': user.profile_photo.url if user.profile_photo else "",
            'name': user.name,
            'user_id': user.username,
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
