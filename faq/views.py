from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile
from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
import json
import uuid
import os

from .forms import SignUpForm, LoginForm, EditProfileForm
from .models import Profile, UploadedFile

# 사용자 인증 관련 뷰
def signup(request):
    """회원가입 뷰: 회원가입 후 사용자를 로그인합니다."""
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'errors': form.errors})
    
    return JsonResponse({'success': False, 'error': '잘못된 요청입니다.'})

def login(request):
    """로그인 뷰: 사용자가 이메일 인증을 완료했는지 확인하고 로그인합니다."""
    if request.method == 'POST':
        form = LoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.profile.is_email_verified:
                auth_login(request, user)
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': '이메일 인증을 완료해주세요.'})
        return JsonResponse({'success': False, 'errors': form.errors})
    
    return JsonResponse({'success': False, 'error': '잘못된 요청입니다.'})

def logout(request):
    """로그아웃 뷰: 사용자를 로그아웃시킵니다."""
    auth_logout(request)
    return JsonResponse({'success': True})

@login_required
def mypage(request):
    """마이페이지 뷰: 현재 로그인한 사용자의 프로필을 반환합니다."""
    profile = request.user.profile
    return JsonResponse({
        'username': profile.user.username,
        'email': profile.user.email,
        # 필요한 다른 프로필 정보를 여기에 추가
    })

@login_required
def edit_profile(request):
    """프로필 수정 뷰: 사용자가 자신의 프로필을 수정할 수 있습니다."""
    if request.method == 'POST':
        form = EditProfileForm(request.POST, instance=request.user.profile)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'errors': form.errors})
    
    return JsonResponse({'success': False, 'error': '잘못된 요청입니다.'})

# 파일 업로드 관련 뷰
@login_required
def upload_file(request):
    """파일 업로드 뷰: 사용자가 파일을 업로드하고, 설명을 추가할 수 있습니다."""
    if request.method == 'POST':
        description = request.POST.get('description')
        upload_dir = 'uploads'
        fs = FileSystemStorage()
        uploaded_file_urls = []

        try:
            if request.FILES.getlist('file'):
                for myfile in request.FILES.getlist('file'):
                    user_name = request.user.username
                    current_time = timezone.now().strftime('%Y%m%d_%H%M%S')
                    file_extension = os.path.splitext(myfile.name)[1]
                    new_filename = f"{user_name}_{current_time}{file_extension}"

                    file_path = os.path.join(upload_dir, new_filename)
                    filename = fs.save(file_path, myfile)
                    uploaded_file_url = fs.url(filename)
                    uploaded_file_urls.append(uploaded_file_url)

                    UploadedFile.objects.create(user=request.user, file=filename, description=description)

            if description:
                text_filename = f"{request.user.username}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.txt"
                text_file_path = os.path.join(upload_dir, text_filename)
                fs.save(text_file_path, ContentFile(description))

                UploadedFile.objects.create(user=request.user, file=text_file_path, description=description)
                uploaded_file_urls.append(fs.url(text_file_path))

            return JsonResponse({'success': True, 'uploaded_file_urls': uploaded_file_urls})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': '잘못된 요청입니다.'})
