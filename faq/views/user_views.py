# user_views.py
# 사용자 프로필 관리, 푸시 알림
from django.conf import settings
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from exponent_server_sdk import PushClient, PushMessage
import logging, os
from ..models import Store

logger = logging.getLogger('faq')

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
        qr_code_path = os.path.join(settings.MEDIA_ROOT, f"qr_codes/qr_{store.store_id}.png") if store else None
        qr_code_url = (
            f"/media/qr_codes/qr_{store.store_id}.png"
            if qr_code_path and os.path.exists(qr_code_path)
            else ""
        )
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
        update_type = request.data.get('type', None)  # 요청에서 'type' 필드 가져오기

        # `store_{store_id}` 경로에 기본 이미지 확인
        store_id = user.stores.first().store_id if user.stores.exists() else None
        store_specific_default_image_relative_path = f"profile_photos/store_{store_id}/profile_default_img.jpg"
        store_specific_default_image_path = os.path.join(
            settings.MEDIA_ROOT, store_specific_default_image_relative_path
        ) if store_id else None

        if update_type == "defaultProfile":
            # 기본 프로필 이미지로 설정하는 경우
            if user.profile_photo.name == store_specific_default_image_relative_path:
                # 기본 이미지가 이미 설정되어 있는 경우
                logger.debug(f"기본 이미지가 이미 설정되어 있습니다. - {user.username}")
            elif store_specific_default_image_path and os.path.exists(store_specific_default_image_path):
                # Store-specific 기본 이미지를 설정
                with open(store_specific_default_image_path, "rb") as f:
                    user.profile_photo.save(f"profile_default_store_{store_id}.jpg", f)
                logger.debug(f"Store-specific 기본 이미지를 설정했습니다. - {user.username}")
            else:
                # 프론트에서 보낸 기본 이미지를 저장
                if profile_photo:
                    user.profile_photo = profile_photo
                    logger.debug(f"프론트에서 보낸 기본 이미지를 저장했습니다. - {user.username}")
                else:
                    logger.error("기본 이미지 파일이 없으며 프론트에서 제공된 이미지도 없습니다.")
                    return Response(
                        {"error": "기본 이미지를 설정할 수 없습니다."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        elif profile_photo:
            # 새 이미지를 업로드하는 경우
            user.profile_photo = profile_photo
            logger.debug(f"프로필 사진을 업데이트했습니다. - {user.username}: {profile_photo.name}")
        else:
            # 잘못된 요청 처리
            logger.error("유효한 프로필 사진 또는 type이 제공되지 않았습니다.")
            return Response(
                {"error": "유효한 프로필 사진 또는 type이 제공되지 않았습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.save()

        # 응답 데이터 생성
        response_data = {
            "message": "프로필 사진이 성공적으로 업데이트되었습니다.",
            "profile_photo_url": user.profile_photo.url if user.profile_photo else None,
        }
        logger.debug(f"Response data: {response_data}")

        return Response(response_data, status=status.HTTP_200_OK)


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

