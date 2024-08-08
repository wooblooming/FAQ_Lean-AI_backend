from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from .forms import SignUpForm, LoginForm
from .models import Profile, UploadedFile

def main(request):
    return render(request, 'faq/main.html')

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            if not Profile.objects.filter(user=user).exists():
                Profile.objects.create(user=user)  # 회원가입 시 프로필 생성
            return redirect('login')
    else:
        form = SignUpForm()
    return render(request, 'faq/signup.html', {'form': form})

def login(request):
    if request.method == 'POST':
        form = LoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            # 로그인 시 프로필이 없으면 생성
            if not hasattr(user, 'profile'):
                Profile.objects.create(user=user)
            return redirect('mypage')
    else:
        form = LoginForm()
    return render(request, 'faq/login.html', {'form': form})

@login_required
def mypage(request):
    profile = Profile.objects.get(user=request.user)
    return render(request, 'faq/mypage.html', {'profile': profile})

@login_required
def upload_file(request):
    if request.method == 'POST' and request.FILES['file']:
        myfile = request.FILES['file']
        fs = FileSystemStorage()
        filename = fs.save(myfile.name, myfile)
        uploaded_file_url = fs.url(filename)
        # 업로드된 파일 정보를 저장
        UploadedFile.objects.create(user=request.user, file=myfile)
        return render(request, 'faq/upload_file.html', {'uploaded_file_url': uploaded_file_url})
    return render(request, 'faq/upload_file.html')

def logout(request):
    auth_logout(request)
    return redirect('main')
