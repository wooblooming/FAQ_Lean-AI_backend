from rest_framework import serializers
from .models import User, Store, Edit  # Edit 모델로 변경
from rest_framework.exceptions import ValidationError
from django.contrib.auth.hashers import make_password
import re

def validate_file(value, allowed_extensions, max_file_size, error_message_prefix):
    extension = value.name.split('.')[-1].lower()
    
    # 파일 확장자 확인
    if extension not in allowed_extensions:
        raise serializers.ValidationError(f"{error_message_prefix} 유효하지 않은 파일 형식입니다. "
                                          f".{', .'.join(allowed_extensions)} 파일만 허용됩니다.")
    
    # 파일 크기 확인
    if value.size > max_file_size:
        raise serializers.ValidationError(f"{error_message_prefix} 파일 크기는 {max_file_size // (1024 * 1024)}MB 이하이어야 합니다.")
    
    return value

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['user_id', 'username', 'password', 'name', 'dob', 'phone', 'email', 'profile_photo', 'created_at']
        extra_kwargs = {'password': {'write_only': True}}

    def validate_username(self, value):
        if not re.match(r'^[a-z][a-z0-9]{3,11}$', value):
            raise ValidationError("아이디는 영문 소문자로 시작하며, 영문 소문자와 숫자만을 포함한 4~12자여야 합니다.")
        return value

    def validate_password(self, value):
        if len(value) < 8 or len(value) > 20:
            raise ValidationError("비밀번호는 8자에서 20자 사이여야 합니다.")
        
        has_upper = re.search(r'[A-Z]', value) is not None
        has_lower = re.search(r'[a-z]', value) is not None
        has_digit = re.search(r'\d', value) is not None
        has_special = re.search(r'[!@#$%^&*]', value) is not None

        if sum([has_upper, has_lower, has_digit, has_special]) < 2:
            raise ValidationError("비밀번호는 대문자, 소문자, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다.")
        
        return value
    
    def validate_email(self, value):
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w{2,4}$', value):
            raise ValidationError("유효한 이메일 주소를 입력해주세요.")
        return value
    
    def validate_profile_photo(self, value):
        return validate_file(value, ['png', 'jpg', 'jpeg'], 5 * 1024 * 1024, "프로필 사진")

    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ['store_id', 'user', 'store_name', 'store_address', 'banner', 'menu_price', 'opening_hours', 'qr_code', 'agent_id', 'updated_at']

    def validate_banner(self, value):
        return validate_file(value, ['png', 'jpg', 'jpeg'], 10 * 1024 * 1024, "배너 사진")
    
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

class UsernameCheckSerializer(serializers.Serializer):
    username = serializers.CharField()

from rest_framework import serializers

class EditSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edit
        fields = ['id', 'user', 'title', 'content', 'file', 'created_at']

    def validate(self, data):
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        file = data.get('file', None)

        if not title and not content and file is None:
            raise serializers.ValidationError("모두 빈칸일 수 없습니다.")
        
        return data

    def validate_file(self, value):
        if value is None:
            return value  # 파일이 업로드되지 않은 경우, 검증을 건너뜁니다.
        
        allowed_extensions = [
            'pdf', 'docx', 'doc', 'txt', 'xlsx', 'xls', 'csv', 'hwp', 'pptx', 'ppt',
            'jpg', 'jpeg', 'png', 'gif', 'zip'
        ]
        max_file_size = 10 * 1024 * 1024  # 10MB

        # 압축 파일은 20MB까지 허용
        if value.name.split('.')[-1].lower() in ['zip']:
            max_file_size = 20 * 1024 * 1024  # 20MB
        
        # 파일 확장자 검사
        file_extension = value.name.split('.')[-1].lower()
        if file_extension not in allowed_extensions:
            raise serializers.ValidationError(f"허용되지 않는 파일 확장자입니다: {file_extension}. 허용된 확장자는 {', '.join(allowed_extensions)}입니다.")

        # 파일 크기 검사
        if value.size > max_file_size:
            raise serializers.ValidationError(f"파일 크기가 너무 큽니다. 최대 허용 크기는 {max_file_size // (1024 * 1024)}MB입니다.")

        return value

