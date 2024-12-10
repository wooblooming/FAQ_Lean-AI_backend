from rest_framework import serializers
from .models import Public_User, Public, Public_Edit, Public_Complaint, Public_Department
from rest_framework.exceptions import ValidationError
from django.contrib.auth.hashers import make_password
import re

# 파일 검증 유틸리티 함수
def validate_file(value, allowed_extensions, max_file_size, error_message_prefix):
    extension = value.name.split('.')[-1].lower()
    if extension not in allowed_extensions:
        return f"{error_message_prefix} 유효하지 않은 파일 형식입니다. " \
               f".{', .'.join(allowed_extensions)} 파일만 허용됩니다."
    if value.size > max_file_size:
        return f"{error_message_prefix} 파일 크기는 {max_file_size // (1000 * 1024 * 1024)}MB 이하이어야 합니다."
    return None


# 유저 관련 시리얼라이저
class PublicUserSerializer(serializers.ModelSerializer):
    department = serializers.CharField(write_only=True)  # department_name을 받아 처리
    class Meta:
        model = Public_User
        fields = ['user_id', 'username', 'password', 'name', 'dob', 'phone', 'email', 'profile_photo', 
                  'created_at', 'marketing', 'public', 'department']
        extra_kwargs = {
            'password': {'write_only': True},
            'email': {'required': False},
            'department': {'required': False},
            'public': {'required': True},
        }

    def validate_username(self, value):
        if not re.match(r'^[a-z][a-z0-9]{3,11}$', value):
            raise serializers.ValidationError("아이디는 영문 소문자로 시작하며, 영문 소문자와 숫자만을 포함한 4~12자여야 합니다.")
        return value

    def validate_password(self, value):
        if len(value) < 8 or len(value) > 20:
            raise serializers.ValidationError("비밀번호는 8자에서 20자 사이여야 합니다.")
        has_upper = re.search(r'[A-Z]', value) is not None
        has_lower = re.search(r'[a-z]', value) is not None
        has_digit = re.search(r'\d', value) is not None
        has_special = re.search(r'[!@#$%^&*]', value) is not None
        if sum([has_upper, has_lower, has_digit, has_special]) < 2:
            raise serializers.ValidationError("비밀번호는 대문자, 소문자, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다.")
        return value
    
    def validate_profile_photo(self, value):
        error_message = validate_file(value, ['png', 'jpg', 'jpeg'], 1000 * 1024 * 1024, "프로필 사진")
        if error_message:
            raise serializers.ValidationError(error_message)
        return value

    def create(self, validated_data):
        department_name = validated_data.pop('department', None)
        public_institution = validated_data.get('public')

        if not public_institution:
            raise serializers.ValidationError("유효한 공공기관을 제공해야 합니다.")

        if department_name and public_institution:
            # 부서가 없으면 생성
            department, _ = Public_Department.objects.get_or_create(
                department_name=department_name,
                public=public_institution
            )
            validated_data['department'] = department

        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)


# 공공기관 관련 시리얼라이저
class PublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Public
        fields = ['public_id', 'public_name', 'public_address', 'public_tel', 'logo', 'opening_hours', 'qr_code', 'agent_id', 'updated_at', 'slug']

    def validate_logo(self, value):
        if value in [None, '']:
            return value
        error_message = validate_file(value, ['png', 'jpg', 'jpeg'], 1000 * 1024 * 1024, "배너 사진")
        if error_message:
            raise serializers.ValidationError({"logo": error_message})
        return value

# 회원가입 시 공공기관 등록시 사용하는 시리얼라이저
class PublicRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Public
        fields = ['public_id', 'public_name', 'public_address', 'public_tel', 'opening_hours', 'logo']


# 로그인 요청에 사용하는 시리얼라이저
class PublicLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


# 사용자명 중복 확인 시리얼라이저
class PublicUsernameCheckSerializer(serializers.Serializer):
    username = serializers.CharField()
    
    def validate_username(self, value):
        if not re.match(r'^[a-z][a-z0-9]{3,11}$', value):
            raise serializers.ValidationError("아이디는 영문 소문자로 시작하며, 영문 소문자와 숫자만을 포함한 4~12자여야 합니다.")
        return value


# 비밀번호 변경 시 사용되는 시리얼라이저
class PublicPasswordCheckSerializer(serializers.Serializer):
    new_password = serializers.CharField()

    def validate_new_password(self, value):
        if len(value) < 8 or len(value) > 20:
            raise serializers.ValidationError("비밀번호는 8자에서 20자 사이여야 합니다.")
        has_upper = re.search(r'[A-Z]', value) is not None
        has_lower = re.search(r'[a-z]', value) is not None
        has_digit = re.search(r'\d', value) is not None
        has_special = re.search(r'[!@#$%^&*]', value) is not None
        if sum([has_upper, has_lower, has_digit, has_special]) < 2:
            raise serializers.ValidationError("비밀번호는 대문자, 소문자, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다.")
        return value


# 수정 사항과 관련된 시리얼라이저
class PublicEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = Public_Edit
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
            return value
        allowed_extensions = ['pdf', 'docx', 'doc', 'txt', 'xlsx', 'xls', 'csv', 'hwp', 'pptx', 'ppt', 'jpg', 'jpeg', 'png', 'gif', 'zip']
        max_file_size = 1000 * 1024 * 1024
        if value.name.split('.')[-1].lower() in ['zip']:
            max_file_size = 1000 * 1024 * 1024
        file_extension = value.name.split('.')[-1].lower()
        if file_extension not in allowed_extensions:
            raise serializers.ValidationError(f"허용되지 않는 파일 확장자입니다: {file_extension}. 허용된 확장자는 {', '.join(allowed_extensions)}입니다.")
        if value.size > max_file_size:
            raise serializers.ValidationError(f"파일 크기가 너무 큽니다. 최대 허용 크기는 {max_file_size // (1024 * 1024)}MB입니다.")
        return value
    
class PublicComplaintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Public_Complaint
        fields = ['complaint_id', 'complaint_number', 'public', 'name', 'birth_date', 'phone', 'email', 'title', 'content', 'status', 'answer', 'created_at', 'department']
        read_only_fields = ['complaint_number', 'created_at']

    def validate(self, data):
        # 제목과 내용 필드 검증
        if not data.get('title'):
            raise serializers.ValidationError({"title": "제목을 입력해야 합니다."})
        if not data.get('content'):
            raise serializers.ValidationError({"content": "내용을 입력해야 합니다."})
        
        # department 필드 검증
        if not data.get('department'):
            raise serializers.ValidationError({"department": "부서를 선택해야 합니다."})
        
        return data



class PublicDepartmentSerializer(serializers.ModelSerializer):
    # 부서 업데이트 시 사용할 필드
    department = serializers.CharField(max_length=255, required=False)
    public_id = serializers.IntegerField(required=False)

    class Meta:
        model = Public_Department
        fields = ['department_id', 'department_name', 'public', 'department', 'public_id']

    def save(self, user=None):
        if 'department_instance' in self.validated_data:
            print("Updating department for user:", user)
            print("New department instance:", self.validated_data['department_instance'])
            
            user.department = self.validated_data['department_instance']
            user.save()
            return user
        else:
            print("Creating new department...")
            return super().save()
