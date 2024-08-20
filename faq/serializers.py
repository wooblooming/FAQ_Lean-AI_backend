from rest_framework import serializers
from .models import User, Store

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['user_id', 'username', 'password', 'name', 'dob', 'phone', 'email', 'profile_photo', 'created_at']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        # 비밀번호를 해싱하지 않고 그대로 저장하는 예시 (실제로는 해싱해야 안전함)
        user = User(
            username=validated_data['username'],
            password=validated_data['password'],  # 비밀번호를 그대로 저장
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

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    
class UsernameCheckSerializer(serializers.Serializer):
    username = serializers.CharField()
