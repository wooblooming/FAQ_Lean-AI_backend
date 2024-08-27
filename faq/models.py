from django.db import models
from django.conf import settings

# User 모델을 관리하는 매니저 클래스 및 커스텀 User 모델
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager

# 기존 UserManager, User, Store 모델은 그대로 유지
class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('사용자 이름은 필수입니다.')
        user = self.model(username=username, **extra_fields)
        user.set_password(password)  # 비밀번호 해싱
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        return self.create_user(username, password, **extra_fields)

class User(AbstractBaseUser):
    user_id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=20, blank=True, null=True)
    dob = models.DateField(blank=True, null=True)  # 생년월일
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(max_length=30, blank=True, null=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)  # ImageField로 변경
    created_at = models.DateTimeField(auto_now_add=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'username'  # 사용자 인증에 사용되는 필드
    REQUIRED_FIELDS = ['email']  # 슈퍼유저 생성 시 필수 필드

    def __str__(self):
        return self.username

class Store(models.Model):
    store_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stores')
    store_name = models.CharField(max_length=20, unique=True)
    store_address = models.CharField(max_length=100, blank=True, null=True)
    banner = models.ImageField(upload_to='banners/', blank=True, null=True)
    menu_price = models.TextField(blank=True, null=True)
    opening_hours = models.TextField(blank=True, null=True)
    qr_code = models.CharField(max_length=100, blank=True, null=True)
    agent_id = models.CharField(max_length=100, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.store_name

class Edit(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='edits')  # 요청을 보낸 사용자
    title = models.CharField(max_length=255, null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    file = models.FileField(upload_to='uploads/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
