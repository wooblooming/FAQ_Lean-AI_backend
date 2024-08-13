from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        # 프로필이 이미 존재하는 경우에는 저장만 합니다.
        try:
            instance.profile.save()
        except Profile.DoesNotExist:
            # 만약 프로필이 없는 경우 (예외적인 경우), 새로 생성합니다.
            Profile.objects.create(user=instance)
