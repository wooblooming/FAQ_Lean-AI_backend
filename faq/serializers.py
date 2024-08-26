from rest_framework import serializers
from .models import User, Store, Edit  # Edit 모델로 변경
from django.contrib.auth.hashers import make_password

from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['user_id', 'username', 'password', 'name', 'dob', 'phone', 'email', 'profile_photo', 'created_at']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User(
            username=validated_data['username'],
            name=validated_data.get('name'),
            dob=validated_data.get('dob'),
            phone=validated_data.get('phone'),
            email=validated_data.get('email'),
            profile_photo=validated_data.get('profile_photo')
        )
        user.set_password(validated_data['password'])  # 비밀번호를 안전하게 해시하여 저장
        user.save()
        return user

    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.dob = validated_data.get('dob', instance.dob)
        instance.phone = validated_data.get('phone', instance.phone)
        instance.email = validated_data.get('email', instance.email)
        
        # profile_photo 업데이트
        if 'profile_photo' in validated_data:
            instance.profile_photo = validated_data['profile_photo']
        
        if 'password' in validated_data:
            instance.set_password(validated_data['password'])
        
        instance.save()
        return instance

    def validate_profile_photo(self, value):
        if not value:
            raise serializers.ValidationError("프로필 사진이 필요합니다.")
        if not isinstance(value, str) and not value.name.endswith(('.png', '.jpg', '.jpeg')):
            raise serializers.ValidationError("유효하지 않은 이미지 형식입니다. .png, .jpg, .jpeg 파일만 허용됩니다.")
        return value


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
