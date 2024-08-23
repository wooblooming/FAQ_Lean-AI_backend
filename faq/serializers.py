from rest_framework import serializers
from .models import User, Store, Edit  # Edit 모델로 변경
from django.contrib.auth.hashers import make_password

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['user_id', 'username', 'password', 'name', 'dob', 'phone', 'email', 'profile_photo', 'created_at']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User(
            username=validated_data['username'],
            password=make_password(validated_data['password']),  # 비밀번호를 해시하여 저장
            name=validated_data.get('name'),
            dob=validated_data.get('dob'),
            phone=validated_data.get('phone'),
            email=validated_data.get('email'),
            profile_photo=validated_data.get('profile_photo')
        )
        user.save()
        return user

class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ['store_id', 'user', 'store_name', 'store_address', 'banner', 'menu_price', 'opening_hours', 'qr_code', 'updated_at']

    def validate_banner(self, value):
        if not value:
            raise serializers.ValidationError("Banner image is required.")
        if not isinstance(value, str) and not value.name.endswith(('.png', '.jpg', '.jpeg')):
            raise serializers.ValidationError("Invalid image format. Only .png, .jpg, .jpeg files are allowed.")
        return value


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

class UsernameCheckSerializer(serializers.Serializer):
    username = serializers.CharField()

# EditSerializer 추가
class EditSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edit
        fields = ['id', 'user', 'title', 'content', 'file', 'created_at']
