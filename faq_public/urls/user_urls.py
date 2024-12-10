# profile_urls.py
from django.urls import path
from ..views import (
    UserProfileView, UserProfilePhotoUpdateView,

)

urlpatterns = [
    path('user-profile/', UserProfileView.as_view(), name='user_profile'),
    path('update-profile-photo/', UserProfilePhotoUpdateView.as_view(), name='update_profile_photo'),

]