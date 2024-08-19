from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'password', 'name', 'dob', 'phone', 'email', 'business_name', 'address']
        extra_kwargs = {'password': {'write_only': True}}  # 비밀번호는 쓰기 전용으로 설정

    def create(self, validated_data):
        # 비밀번호를 해싱하지 않고 그대로 저장
        user = User(
            username=validated_data['username'],
            password=validated_data['password'],  # 비밀번호를 그대로 저장
            name=validated_data.get('name'),
            dob=validated_data.get('dob'),
            phone=validated_data.get('phone'),
            email=validated_data.get('email'),
            business_name=validated_data.get('business_name'),
            address=validated_data.get('address'),
        )
        user.save()
        return user

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    
class UsernameCheckSerializer(serializers.Serializer):
    username = serializers.CharField()