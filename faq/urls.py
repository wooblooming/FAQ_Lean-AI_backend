from django.urls import path
from . import views  # faq 앱의 views를 임포트
from django.views.generic import TemplateView

urlpatterns = [
    path('', TemplateView.as_view(template_name='landingMenu.html')),
    path('siginform/', views.signup, name='siginform'),  # signForm.html 대응 (회원가입)
    path('login/', views.login, name='login'),  # login.html 대응 (로그인)
    path('logout/', views.logout, name='logout'),  # 로그아웃 기능
    path('mypage/', views.mypage, name='mypage'),  # myPage.html 대응 (마이페이지)
    path('edit_profile/', views.edit_profile, name='edit_profile'),  # editData.html 대응 (프로필 수정)
    path('upload_file/', views.upload_file, name='upload_file'),  # 파일 업로드 (프론트엔드에서 처리될 수도 있음)
]
