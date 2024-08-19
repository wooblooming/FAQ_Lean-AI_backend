from django.db import models

class User(models.Model):
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128)
    name = models.CharField(max_length=100, null=True, blank=True)  # 사용자 이름, NULL 허용
    dob = models.DateField(null=True, blank=True)  # 생년월일, NULL 허용
    phone = models.CharField(max_length=15, null=True, blank=True)  # 전화번호, NULL 허용
    email = models.EmailField(unique=True, null=True, blank=True)  # 이메일, NULL 허용, 고유해야 함
    business_name = models.CharField(max_length=255, null=True, blank=True)  # 사업자명, NULL 허용
    address = models.TextField(null=True, blank=True)  # 주소, NULL 허용

    def __str__(self):
        return self.username  # 객체를 문자열로 표현할 때 사용자 이름을 반환

# 이 모델은 사용자 정보를 저장하는 테이블과 연결되며,
# 'username'과 'password'를 제외한 모든 필드는 NULL 값을 허용합니다.
