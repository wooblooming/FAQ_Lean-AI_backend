# public_urls.py
from rest_framework.routers import DefaultRouter
from django.urls import path
from ..views import (
    PublicViewSet,
    DepartmentViewSet

)

router = DefaultRouter()
router.register(r'publics', PublicViewSet, basename='public')
router.register(r'departments', DepartmentViewSet, basename='department')

urlpatterns = router.urls

'''
PublicViewSet
GET /publics/ → 모든 공공기관 조회 (list)
POST /publics/ → 공공기관 생성 (create)
GET /publics/{pk}/ → 특정 공공기관 조회 (retrieve)
PUT /publics/{pk}/ → 특정 공공기관 수정 (update)
DELETE /publics/{pk}/ → 특정 공공기관 삭제 (destroy)

DepartmentViewSet
GET /departments/ → 모든 부서 조회 (list)
POST /departments/ → 부서 생성 (create)
GET /departments/{pk}/ → 특정 부서 조회 (retrieve)
PUT /departments/{pk}/ → 특정 부서 수정 (update)
DELETE /departments/{pk}/ → 특정 부서 삭제 (destroy)
'''