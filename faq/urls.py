from django.urls import path
from . import views

urlpatterns = [
    path('', views.main, name='main'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login, name='login'),
    path('mypage/', views.mypage, name='mypage'),
    path('logout/', views.logout, name='logout'),
    path('upload/', views.upload_file, name='upload_file'),
]
