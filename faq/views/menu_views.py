# menu_views.py
# 메뉴 등록, 수정, 삭제 관리
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from django.db import transaction
from urllib.parse import unquote
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
import logging, json
from ..models import Store, Menu
from ..serializers import MenuSerializer

logger = logging.getLogger('faq')


class MenuViewSet(ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """
        메뉴 목록 조회
        """
        slug = request.query_params.get('slug')
        store_id = request.query_params.get('store_id')

        try:
            if slug:
                store = Store.objects.get(slug=slug)
            elif store_id:
                store = Store.objects.get(store_id=store_id)
            else:
                return Response({'error': 'slug 또는 store_id가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

            menus = Menu.objects.filter(store=store)
            serializer = MenuSerializer(menus, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Store.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        
        
    def retrieve(self, request, pk=None):
        """
        단일 매장 정보 조회
        """
        try:
            store = Store.objects.get(store_id=pk, user=request.user)
            menus = Menu.objects.filter(store=store)
            serializer = MenuSerializer(menus, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except Store.DoesNotExist:
            return Response({'error': '해당 매장 정보를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        


    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def list_menus_by_slug(self, request):
        """
        특정 매장(slug 기반)의 메뉴 출력 API
        """
        slug = request.query_params.get('slug') 
        if not slug:
            return Response({"error": "slug가 필요합니다."}, status=400)

        try:
            if slug:
                store = Store.objects.get(slug=slug)
            else:
                return Response({'error': 'slug가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

            menus = Menu.objects.filter(store=store)
            serializer = MenuSerializer(menus, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Store.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        

    def create(self, request):
        """
        메뉴 생성
        """
        menus = self.extract_menus_from_request(request, 'create')
        if not menus:
            return Response({'error': '메뉴 데이터가 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)

        created_menus = []
        with transaction.atomic():
            for menu_data in menus:
                store_slug = unquote(menu_data.get('slug'))
                try:
                    store = Store.objects.get(slug=store_slug, user=request.user)
                except Store.DoesNotExist:
                    return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)

                last_menu = Menu.objects.filter(store=store).order_by('-menu_number').first()
                menu_data['menu_number'] = (last_menu.menu_number + 1) if last_menu else 1
                menu_data['store'] = store.store_id

                serializer = MenuSerializer(data=menu_data)
                if serializer.is_valid():
                    created_menu = serializer.save()
                    created_menus.append(serializer.data)
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            update_menu_price_field(store)

        return Response({'created_menus': created_menus}, status=status.HTTP_201_CREATED)
    

    def update(self, request, pk=None):
        """
        메뉴 수정
        """
        try:
            # 요청 데이터 가져오기
            menu_number = request.data.get('menu_number')  # `menu_number` 확인
            name = request.data.get('name')
            price = request.data.get('price')
            category = request.data.get('category')
            image = request.FILES.get('image')

            # 메뉴 객체 가져오기
            menu = Menu.objects.get(menu_number=menu_number, store__user=request.user)

            # 필드 업데이트
            if name:
                menu.name = name
            if price:
                menu.price = price
            if category:
                menu.category = category
            if image:
                menu.image = image

            # 변경 사항 저장
            menu.save()

            # 응답 데이터 구성
            serializer = MenuSerializer(menu)
            return Response({'updated_menu': serializer.data}, status=status.HTTP_200_OK)

        except Menu.DoesNotExist:
            return Response({'error': '메뉴를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception(f"Unexpected error during menu update: {e}")
            return Response({'error': '알 수 없는 오류가 발생했습니다.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    

    def destroy(self, request, pk=None):
        """
        메뉴 삭제
        """
        try:
            menu = Menu.objects.get(pk=pk, store__user=request.user)
            menu.delete()
            return Response({'message': '메뉴가 삭제되었습니다.'}, status=status.HTTP_204_NO_CONTENT)
        except Menu.DoesNotExist:
            return Response({'error': '메뉴를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)  
            
         
        

    @action(detail=False, methods=['get'])
    def view_category(self, request):
        """
        메뉴 카테고리 조회
        """
        slug = request.query_params.get('slug')

        try:
            store = Store.objects.get(slug=slug)
            categories = Menu.objects.filter(store=store).values_list('category', flat=True).distinct()
            category_options = [{'value': category, 'label': category} for category in categories if category]
            return Response(category_options, status=status.HTTP_200_OK)
        except Store.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        

    @action(detail=False, methods=['delete'])
    def delete_category(self, request):
        """
        카테고리 삭제
        """
        category = request.data.get('category')
        slug = request.data.get('slug')

        if not category or not slug:
            return Response({'error': '카테고리와 스토어 슬러그가 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            store = Store.objects.get(slug=slug, user=request.user)
            Menu.objects.filter(store=store, category=category).delete()
            update_menu_price_field(store)

            return Response({'message': f'카테고리 "{category}" 삭제 성공.'}, status=status.HTTP_204_NO_CONTENT)

        except Store.DoesNotExist:
            return Response({'error': '스토어를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        

    def extract_menus_from_request(self, request, action):
        """
        요청 데이터에서 메뉴를 추출
        """
        menus = []
        if 'slug' in request.data:
            menu_data = {
                'slug': request.data.get('slug'),
                'name': request.data.get('name'),
                'price': request.data.get('price'),
                'category': request.data.get('category'),
                'image': request.FILES.get('image'),
            }
            if action == 'update':
                menu_data['menu_number'] = request.data.get('menu_number')
            menus.append(menu_data)
        else:
            index = 0
            while f'menus[{index}][slug]' in request.data:
                menu_data = {
                    'slug': request.data.get(f'menus[{index}][slug]'),
                    'name': request.data.get(f'menus[{index}][name]'),
                    'price': request.data.get(f'menus[{index}][price]'),
                    'category': request.data.get(f'menus[{index}][category]'),
                    'image': request.FILES.get(f'menus[{index}][image]'),
                }
                if action == 'update':
                    menu_data['menu_number'] = request.data.get(f'menus[{index}][menu_number]')
                menus.append(menu_data)
                index += 1
        return menus


def update_menu_price_field(store):
    """
    Store의 menu_price 필드를 업데이트
    """
    menus = Menu.objects.filter(store=store)
    menu_price_data = [
        {
            'name': menu.name,
            'price': float(menu.price),
            'category': menu.category,
            'image': str(menu.image.url) if menu.image else None,
            'allergy': menu.allergy or ""
        }
        for menu in menus
    ]
    store.menu_price = json.dumps(menu_price_data, ensure_ascii=False)
    store.save()
