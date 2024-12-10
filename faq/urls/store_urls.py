# store_urls.py
from rest_framework.routers import DefaultRouter
from ..views.store_views import StoreViewSet, FeedViewSet

router = DefaultRouter()
router.register(r'stores', StoreViewSet, basename='stores')
router.register(r'feeds', FeedViewSet, basename='feeds')

urlpatterns = router.urls


'''
StoreViewSet
GET /api/stores/<store_id>/ → retrieve: 특정 매장 정보 조회
PUT /api/stores/update/<store_id>/ → update: 매장 정보 업데이트
POST /api/stores/detail_by_slug/ → detail_by_slug: slug 기반 매장 정보 조회 (@action

FeedViewSet
POST /api/feeds/list_images/ → list_images: 피드 이미지 목록 조회 (@action)
POST /api/feeds/upload_image/ → upload_image: 피드 이미지 업로드 (@action)
DELETE /api/feeds/delete_image/ → delete_image: 피드 이미지 삭제 (@action)
PUT /api/feeds/rename_image/ → rename_image: 피드 이미지 이름 변경 (@action)


'''