import os
import shutil
from django.core.files import File
import pandas as pd
from .models import Menu, Store
import logging
import json  # JSON 변환을 위한 import
from django.conf import settings

# 디버깅을 위한 로거 설정
logger = logging.getLogger('faq')

def process_excel_and_save_to_db(file_path, store_id):
    """
    엑셀 파일을 읽어와서 DB에 저장하는 함수.
    엑셀 파일에 이미지 경로가 포함되어 있다면 해당 이미지를 /media/menu_images/로 복사하여 DB에 저장.
    """
    try:
        # 엑셀 파일을 읽어오기 (첫 번째 시트를 기준으로, 첫 번째 행은 헤더로 처리)
        df = pd.read_excel(file_path, header=1)
        logger.debug(f"df.head(): {df.head()}")

        # NaN 값을 빈 문자열("")로 대체
        df = df.fillna("")  
        logger.debug(f"NaN 값을 빈 문자열로 대체한 데이터프레임: {df.head()}")

        # store 객체 가져오기
        store = Store.objects.get(store_id=store_id)

        # 기존의 menu_price 데이터를 불러오기 (비어있을 경우 빈 리스트로 처리)
        if store.menu_price:
            try:
                menu_list = json.loads(store.menu_price)
            except json.JSONDecodeError:
                logger.error("menu_price 필드가 유효한 JSON 형식이 아닙니다. 빈 리스트로 초기화합니다.")
                menu_list = []
        else:
            menu_list = []

        # 엑셀 데이터 행별로 처리하여 Menu 테이블에 저장
        for _, row in df.iterrows():
            logger.debug(f"Processing row: {row}")  # 각 행의 데이터 출력
            if row['메뉴명'] == "":
                continue  # '메뉴명'이 없는 경우 해당 행을 건너뜀

            menu = Menu(
                store=store,
                name=row['메뉴명'],
                price=row['가격'],
                category=row['카테고리'],
                menu_introduction=row['간단한 소개(50자 이내)'],
                spicy=row['맵기'],
                allergy=row['알레르기 유발물질'],
                origin=row['원산지']
            )

            # 이미지 경로가 있을 경우 처리
            image_path = row.get('사진', None)  # '사진' 열에서 이미지 경로를 가져옴
            if pd.notna(image_path) and isinstance(image_path, str) and os.path.exists(image_path):
                # 이미지 파일을 /media/menu_images/로 복사하여 Django ImageField에 저장
                new_image_path = os.path.join('menu_images', os.path.basename(image_path))
                destination_path = os.path.join(settings.MEDIA_ROOT, new_image_path)
                
                # 이미지 복사
                shutil.copy(image_path, destination_path)

                # 파일을 ImageField에 저장
                with open(destination_path, 'rb') as image_file:
                    menu.image.save(os.path.basename(image_path), File(image_file), save=False)

            # 메뉴 객체를 저장
            menu.save()
            logger.debug(f"Saved menu: {menu}")

            # 새로운 메뉴 정보를 리스트에 추가
            menu_list.append({
                'name': menu.name,
                'price': menu.price,
                'category': menu.category,
                'allergy': menu.allergy
            })

        # 업데이트된 메뉴 리스트를 JSON으로 변환하여 store의 menu_price에 저장
        store.menu_price = json.dumps(menu_list, ensure_ascii=False)
        store.save()
        logger.debug(f"메뉴 정보를 store.menu_price에 저장: {store.menu_price}")

        logger.debug(f"엑셀 데이터를 성공적으로 처리하고 저장했습니다.")

    except Exception as e:
        logger.error(f"엑셀 파일 처리 중 오류 발생: {e}")
