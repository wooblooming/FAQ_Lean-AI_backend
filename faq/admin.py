from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'name', 'dob', 'phone')
    search_fields = ('username', 'email', 'name')
    ordering = ('username',)
    fields = ('username', 'password', 'name', 'dob', 'phone', 'email')
    
    def save_model(self, request, obj, form, change):
        """
        비밀번호를 해싱하지 않고, 입력된 그대로 저장합니다.
        """
        # 비밀번호를 그대로 저장
        obj.password = form.cleaned_data['password']
        obj.save()
