from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    name = forms.CharField(max_length=30, required=True, label='이름')
    birth_date = forms.DateField(
        required=True,
        label='생년월일',
        widget=forms.TextInput(attrs={'type': 'date'})
    )
    phone_number = forms.CharField(max_length=15, required=True, label='휴대폰번호')
    store_name = forms.CharField(max_length=100, required=True, label='업소명')
    address = forms.CharField(max_length=255, required=True, label='주소')

    class Meta:
        model = User
        fields = ('username', 'password1', 'password2', 'name', 'email', 'birth_date', 'phone_number', 'store_name', 'address')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['name']  # name 필드를 first_name에 저장
        if commit:
            user.save()
            user.profile.birth_date = self.cleaned_data['birth_date']
            user.profile.phone_number = self.cleaned_data['phone_number']
            user.profile.store_name = self.cleaned_data['store_name']
            user.profile.address = self.cleaned_data['address']
            user.profile.save()
        return user
    
class LoginForm(AuthenticationForm):
    username = forms.CharField(max_length=254, required=True)
    password = forms.CharField(widget=forms.PasswordInput, required=True)
