# complaint_urls.py
from rest_framework.routers import DefaultRouter
from ..views import ComplaintViewSet

router = DefaultRouter()
router.register(r'complaints', ComplaintViewSet, basename='complaint')

urlpatterns = router.urls

'''
GET /complaints/ - 민원 조회 (부서 기반)
POST /complaints/ - 민원 등록
POST /complaints/customer_view/ - 민원인 조회
PATCH /complaints/{id}/update_status/ - 민원 상태 변경
POST /complaints/{id}/transfer/ - 민원 부서 이관
POST /complaints/{id}/answer/ - 민원 답변 등록

'''