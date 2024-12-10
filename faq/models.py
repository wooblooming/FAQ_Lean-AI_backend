from django.db import models
from django.utils.text import slugify
from django.conf import settings
import os
import json

# User 모델을 관리하는 매니저 클래스 및 커스텀 User 모델
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager

# 경로 생성 함수를 정의
def user_directory_path(instance, filename):
    # 파일이 저장될 경로를 정의합니다. 예: 'uploads/store_<store_id>/<filename>'
    return os.path.join(f'uploads/store_{instance.user.stores.first().store_id}', filename)

def profile_photo_upload_path(instance, filename):
    store_id = instance.stores.first().store_id if instance.stores.exists() else 'default'
    return os.path.join(f'profile_photos/store_{store_id}', filename)

def banner_upload_path(instance, filename):
    return os.path.join(f'banners/store_{instance.store_id}', filename)

def menu_image_upload_path(instance, filename):
    return os.path.join(f'menu_images/store_{instance.store.store_id}', filename)


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
    profile_photo = models.ImageField(upload_to=profile_photo_upload_path, blank=True, null=True)  # ImageField로 변경
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    marketing = models.CharField(max_length=1, choices=[('Y', 'Yes'), ('N', 'No')], default='N')
    
    push_token = models.CharField(max_length=255, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'username'  # 사용자 인증에 사용되는 필드
    REQUIRED_FIELDS = ['email']  # 슈퍼유저 생성 시 필수 필드

    # 탈퇴 시 비활성화
    def deactivate(self):
        self.is_active = False
        self.save()

    def __str__(self):
        return self.username
    

class Store(models.Model):
    STORE_CATEGORIES = [
        ('FOOD', '음식점'),
        ('RETAIL', '판매점'),
        ('UNMANNED', '무인매장'),
        ('PUBLIC', '공공기관'),
        ('OTHER', '기타'),
    ]

    store_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stores')
    store_name = models.CharField(max_length=20, unique=True)
    store_address = models.TextField(blank=True, null=True)
    store_tel = models.TextField(blank=True, null=True)
    banner = models.ImageField(upload_to=banner_upload_path, blank=True, null=True)
    menu_price = models.TextField(blank=True, null=True)
    opening_hours = models.TextField(blank=True, null=True)
    qr_code = models.CharField(max_length=100, blank=True, null=True)
    agent_id = models.CharField(max_length=100, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    slug = models.SlugField(max_length=255, unique=True)
    store_category = models.CharField(max_length=50, choices=STORE_CATEGORIES, default='FOOD')
    store_introduction = models.TextField(blank=True, null=True)
    store_information = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        # Slug가 비어있으면 store_name을 기반으로 slug 생성
        if not self.slug:
            # 공백은 하이픈으로, 특수 문자는 모두 제거
            base_slug = slugify(self.store_name, allow_unicode=True)  # allow_unicode=True로 한글 슬러그 지원
            slug = base_slug
            counter = 1

            # 중복된 슬러그가 있으면 '-1', '-2'를 붙여 고유하게 만듦
            while Store.objects.filter(slug=slug).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1

            self.slug = slug

        if isinstance(self.menu_price, list):
            self.menu_price = json.dumps(self.menu_price)  # JSON 문자열로 변환
        super(Store, self).save(*args, **kwargs)

    def __str__(self):
        return self.store_name

class Edit(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='edits')  # 요청을 보낸 사용자
    title = models.CharField(max_length=255, null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    file = models.FileField(upload_to=user_directory_path, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    def __str__(self):
        return self.title
    
class Menu(models.Model):
    SPICY_CATEGORIES = [
        ('0', '매운맛이 없는 음식'),
        ('1', '초보 (진라면 순한맛 맵기)'),
        ('2', '하수 (진라면 매운맛 맵기)'),
        ('3', '중수 (신라면 맵기)'),
        ('4', '고수 (불닭볶음면 맵기)'),
        ('5', '신 (핵불닭볶음면 맵기)'),
    ]

    store = models.ForeignKey(Store, related_name='menus', on_delete=models.CASCADE)
    menu_number = models.AutoField(primary_key=True)  # 기본 키로 전역적으로 유일한 값을 할당
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=100)
    image = models.ImageField(upload_to=menu_image_upload_path, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)
    spicy = models.CharField(max_length=50, choices=SPICY_CATEGORIES, default='0')
    allergy = models.TextField(null=True, blank=True)
    menu_introduction = models.TextField(blank=True, null=True)
    origin = models.TextField(blank=True, null=True)
