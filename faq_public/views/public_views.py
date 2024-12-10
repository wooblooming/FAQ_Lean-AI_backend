# public_views.py
# 공공기관 및 부서 관리
from ..authentication import PublicUserJWTAuthentication
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
import logging
from ..models import Public, Public_Department
from ..serializers import (
    PublicUserSerializer, 
    PublicSerializer, 
    PublicRegisterSerializer,
    PublicDepartmentSerializer
)

# 디버깅을 위한 로거 설정
logger = logging.getLogger('faq')


# 공공기관
class PublicViewSet(ViewSet):

    """
    공공기관 관련 CRUD를 처리하는 ViewSet
    """
    def list(self, request):
        """
        모든 공공기관 출력 API
        """
        public_list = Public.objects.all()
        serializer = PublicSerializer(public_list, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """
        선택한 공공기관 정보 출력 API
        """
        try:
            public = Public.objects.get(public_id=pk)
            serializer = PublicSerializer(public)
            return Response(serializer.data)
        except Public.DoesNotExist:
            return Response({"error": "해당 공공기관을 찾을 수 없습니다."}, status=404)

    def create(self, request):
        """
        공공기관 생성 API
        """
        logo_file = request.FILES.get('logo', None)
        serializer = PublicRegisterSerializer(data=request.data)

        if serializer.is_valid():
            public_instance = serializer.save()

            if logo_file:
                public_instance.logo = logo_file
                public_instance.save()

            return Response(
                {
                    "status": "success",
                    "message": "공공기관 정보가 성공적으로 등록되었습니다.",
                    "data": PublicSerializer(public_instance).data,
                },
                status=201,
            )
        return Response({"status": "error", "errors": serializer.errors}, status=400)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def detail_by_slug(self, request):
        """
        특정 공공기관(slug 기반) 출력 API
        """
        slug = request.data.get('slug')
        if not slug:
            return Response({"error": "slug가 필요합니다."}, status=400)

        try:
            public = Public.objects.get(slug=slug)
            serializer = PublicSerializer(public)
            return Response(serializer.data)
        except Public.DoesNotExist:
            return Response({"error": "해당 slug의 공공기관을 찾을 수 없습니다."}, status=404)
        

    @action(detail=False, methods=['post'], authentication_classes=[PublicUserJWTAuthentication], permission_classes=[IsAuthenticated])
    def user_info(self, request):
        """
        공공기관 및 사용자 정보 출력 API
        """
        public_user = request.user
        if not public_user:
            return Response({"error": "가입된 사용자가 아닙니다."}, status=404)

        public = public_user.public
        if not public:
            return Response({"error": "공공기관 정보가 없습니다."}, status=404)

        department = public_user.department
        department_data = {
            "department_id": department.department_id if department else "",
            "department_name": department.department_name if department else ""
        }

        user_data = PublicUserSerializer(public_user).data
        public_data = PublicSerializer(public).data

        return Response({
            "user": user_data,
            "public": public_data,
            "department": department_data,
        })


# 부서
class DepartmentViewSet(ViewSet):
    authentication_classes = [PublicUserJWTAuthentication]
    
    # 공공기관 부서 목록 조회 (POST 요청)
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def list_departments(self, request):
        try:
            slug = request.data.get('slug')
            public_id = request.data.get('publicID')

            if not slug and not public_id:
                return Response({'error': 'slug 또는 publicID 중 하나를 제공해야 합니다.'}, status=400)

            if public_id:
                departments = list(
                    Public_Department.objects.filter(public_id=public_id)
                    .values_list('department_name', flat=True)
                    .distinct()
                )
            elif slug:
                public = Public.objects.filter(slug=slug).first()
                if not public:
                    return Response({'error': '해당 slug에 일치하는 Public이 없습니다.'}, status=404)

                departments = list(
                    Public_Department.objects.filter(public=public)
                    .values_list('department_name', flat=True)
                    .distinct()
                )

            if '기타' not in departments:
                departments.append('기타')

            if departments:
                return Response({'departments': departments}, status=200)
            else:
                return Response({'message': '해당 public_id 또는 slug에 대한 부서가 없습니다.'}, status=404)

        except Exception as e:
            return Response({'error': str(e)}, status=500)

    # 부서 생성 (POST 요청)
    def create(self, request):
        department_name = request.data.get('department_name')
        public_id = request.data.get('public_id')

        if not department_name or not public_id:
            return Response(
                {"error": "부서 이름과 공공기관 ID는 필수입니다."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            public = Public.objects.get(public_id=public_id)
        except Public.DoesNotExist:
            return Response(
                {"error": "유효하지 않은 공공기관 ID입니다."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        department = Public_Department.objects.create(department_name=department_name, public=public)
        serializer = PublicDepartmentSerializer(department)
        return Response(serializer.data, status=status.HTTP_201_CREATED)



    # 사용자 부서 이동 (PUT 요청)
    def update(self, request, pk=None):
        user = request.user
        department_name = request.data.get("department_name")
        public_id = request.data.get("public_id")

        if not department_name or not public_id:
            return Response(
                {"error": "부서와 공공기관 ID는 필수 항목입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            department = Public_Department.objects.get(department_name=department_name, public_id=public_id)

            if user.department == department:
                return Response(
                    {"error": "현재 선택된 부서와 동일합니다."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user.department = department
            user.save()
            return Response({"message": "부서가 성공적으로 변경되었습니다."}, status=status.HTTP_200_OK)

        except Public_Department.DoesNotExist:
            return Response(
                {"error": "해당 부서는 존재하지 않습니다."},
                status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            return Response(
                {"error": f"예상치 못한 오류가 발생했습니다: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


