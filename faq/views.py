from django.http import HttpResponse
from django.shortcuts import render, redirect
from .forms import UserRegistrationForm

def index(request):
    return HttpResponse("린에이아이에 오신것을 환영합니다.")

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')  # 회원가입이 성공하면 로그인 페이지로 리다이렉트
    else:
        form = UserRegistrationForm()
    
    return render(request, 'register.html', {'form': form})