from django.db import models

class User(models.Model):
    username = models.CharField(max_length=15, unique=True)  # 아이디
    password = models.CharField(max_length=15)  # 비밀번호
    name = models.CharField(max_length=15)  # 이름
    date_of_birth = models.DateField()  # 생년월일
    phone_number = models.CharField(max_length=11)  # 휴대폰번호
    email = models.EmailField(unique=True)  # 이메일
    business_name = models.CharField(max_length=20)  # 업소명
    address = models.CharField(max_length=100)  # 주소

    def __str__(self):
        return self.username
