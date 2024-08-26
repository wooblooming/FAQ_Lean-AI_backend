from rest_framework import serializers
from .models import User, Store, Edit  # Edit 모델로 변경
from rest_framework.exceptions import ValidationError
from django.contrib.auth.hashers import make_password
from rest_framework import serializers
import re

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['user_id', 'username', 'password', 'name', 'dob', 'phone', 'email', 'profile_photo', 'created_at']
        extra_kwargs = {'password': {'write_only': True}}

    def validate_username(self, value):
        """
        아이디 유효성 검사: 영문 소문자와 숫자만 사용, 영문 소문자로 시작, 4~12자
        """
        if not re.match(r'^[a-z][a-z0-9]{3,11}$', value):
            raise ValidationError("아이디는 영문 소문자로 시작하며, 영문 소문자와 숫자만을 포함한 4~12자여야 합니다.")
        return value

    def validate_password(self, value):
        """
        비밀번호 유효성 검사: 대문자, 소문자, 숫자, 특수문자 중 2가지 이상을 조합하여 8자~20자
        """
        if len(value) < 8 or len(value) > 20:
            raise ValidationError("비밀번호는 8자에서 20자 사이여야 합니다.")
        
        # 대문자, 소문자, 숫자, 특수문자 조건을 각각 확인
        has_upper = re.search(r'[A-Z]', value) is not None
        has_lower = re.search(r'[a-z]', value) is not None
        has_digit = re.search(r'\d', value) is not None
        has_special = re.search(r'[!@#$%^&*]', value) is not None

        # 조건 중 2가지 이상을 만족해야 함
        if sum([has_upper, has_lower, has_digit, has_special]) < 2:
            raise ValidationError("비밀번호는 대문자, 소문자, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다.")
        
        return value
    
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
            raise serializers.ValidationError("Banner 사진이 필요합니다.")
        if not isinstance(value, str) and not value.name.endswith(('.png', '.jpg', '.jpeg')):
            raise serializers.ValidationError("유효하지 않은 이미지 형식입니다. .png, .jpg, .jpeg 파일만 허용됩니다.")
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
