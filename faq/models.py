from django.db import models
from django.contrib.auth.models import User
import uuid

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    birth_date = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    store_name = models.CharField(max_length=100, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)

    # 이메일 인증 관련 필드 추가
    is_email_verified = models.BooleanField(default=False)  # 이메일 인증 여부
    email_verification_token = models.CharField(max_length=255, unique=True, null=True, blank=True)  # 인증 토큰

    def __str__(self):
        return self.user.username

    def save(self, *args, **kwargs):
        if not self.email_verification_token:
            self.email_verification_token = str(uuid.uuid4())  # 랜덤한 UUID 생성
        super().save(*args, **kwargs)

class UploadedFile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='uploads/')
    description = models.TextField(blank=True, null=True)  # description 필드 추가
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.file.name}"