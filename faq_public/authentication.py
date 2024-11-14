# authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Public_User

class PublicUserJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            # 토큰에서 user_id를 사용하여 Public_User 객체를 조회
            user_id = validated_token.get("user_id")
            return Public_User.objects.get(user_id=user_id)
        except Public_User.DoesNotExist:
            return None
