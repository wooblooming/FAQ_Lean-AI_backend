import os
import shutil
import pandas as pd
import json
from django.core.files import File
from django.conf import settings
from .models import Menu, Store
import logging
from .utils import send_slack_notification

logger = logging.getLogger('faq')

def validate_excel_data(df):
    """
    엑셀 데이터의 유효성을 검증하는 함수.
    각 행의 필수 값과 데이터 타입을 확인.
    """
    errors = []

    # 필수 필드 정의
    required_columns = ['카테고리', '메뉴명', '가격', '간단한 소개(50자 이내)', '맵기', '알레르기 유발물질' ,'원산지', '사진']

    # 필수 필드 존재 여부 확인
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        errors.append(f"엑셀 파일에 다음 항목이 누락되었습니다: {', '.join(missing_columns)}")
        return errors  # 필드가 없으면 추가 검증을 중단하고 에러 반환

    # 각 행에 대해 데이터 검증
    for index, row in df.iterrows():
        # '메뉴명' 필수 확인
        if pd.isnull(row.get('메뉴명')):
            errors.append(f"{index + 2}번째 줄: '메뉴명'이 비어 있습니다.")
        
        # '가격'이 숫자인지 확인
        if not pd.isnull(row.get('가격')) and not isinstance(row['가격'], (int, float)):
            errors.append(f"{index + 2}번째 줄: '가격' 값이 숫자가 아닙니다. (값: {row['가격']})")
    
    return errors


def preprocess_excel_data(df):
    """
    엑셀 데이터를 전처리하는 함수.
    예를 들어, 비어 있는 값에 기본값을 추가하거나 형식을 수정.
    """
    default_category = "기본 카테고리"
    last_category = default_category

    for index, row in df.iterrows():
        # 카테고리 값이 비어 있으면 이전 값 사용, 없으면 기본값
        if pd.isnull(row.get('카테고리')):
            df.at[index, '카테고리'] = last_category
        else:
            last_category = row['카테고리']

        # '가격'이 비어 있는 경우 기본값 0 설정
        if pd.isnull(row.get('가격')):
            df.at[index, '가격'] = 0

    return df


def process_excel_and_save_to_db(file_path, store_id, user, file_name, created_at):
    """
    엑셀 파일을 처리하고 DB에 저장하며 성공 시 파일을 이동합니다.
    """
    try:
        logger.info(f"Processing Excel file: {file_path}")

        # 엑셀 파일 읽기
        df = pd.read_excel(file_path, header=1)
        logger.info(f"Excel data loaded. Head: \n{df.head()}")

        # 데이터 검증
        validation_errors = validate_excel_data(df)
        if validation_errors:
            error_message = "\n".join(validation_errors)
            logger.error(f"Validation errors: \n{error_message}")
            raise ValueError(error_message)

        # 데이터 전처리
        df = preprocess_excel_data(df)

        # Store 객체 가져오기
        store = Store.objects.get(store_id=store_id)

        # 메뉴 저장 로직
        menu_list = json.loads(store.menu_price) if store.menu_price else []
        for _, row in df.iterrows():
            menu = Menu(
                store=store,
                name=row['메뉴명'],
                price=row['가격'],
                category=row['카테고리'],
                menu_introduction=row.get('간단한 소개(50자 이내)', ''),
                spicy=row.get('맵기', 0),
                allergy=row.get('알레르기 유발물질', ''),
                origin=row.get('원산지', '')
            )

            # 이미지 처리
            image_path = row.get('사진', None)
            if pd.notna(image_path) and isinstance(image_path, str) and os.path.exists(image_path):
                new_image_path = os.path.join('menu_images', os.path.basename(image_path))
                destination_path = os.path.join(settings.MEDIA_ROOT, new_image_path)
                shutil.copy(image_path, destination_path)

                with open(destination_path, 'rb') as image_file:
                    menu.image.save(os.path.basename(image_path), File(image_file), save=False)

            menu.save()
            menu_list.append({
                'name': menu.name,
                'price': menu.price,
                'category': menu.category
            })

        # Store의 menu_price 업데이트
        store.menu_price = json.dumps(menu_list, ensure_ascii=False)
        store.save()

        # 파일 이동
        destination_dir = os.path.join(settings.MEDIA_ROOT, f"uploads/store_{store_id}")
        os.makedirs(destination_dir, exist_ok=True)
        destination_path = os.path.join(destination_dir, file_name)
        shutil.move(file_path, destination_path)

        logger.info(f"File moved to: {destination_path}")
        logger.info(f"Successfully processed and saved Excel data for store_id: {store_id}")

        # 성공 알림 메시지
        message = (
            f"🔔 *데이터 등록 성공 알림!*\n"
            f"- *사용자*: {user}\n"
            f"- *파일 이름*: {file_name}\n"
            f"- *등록 시간*: {created_at}\n"
        )
        send_slack_notification(message)

        return {"status": "success", "message": "파일이 성공적으로 처리되었습니다."}

    except Exception as e:
        error_message = f"Error processing Excel file: {str(e)}"
        logger.error(error_message)
        slack_message = (
            f"⚠️ *데이터 등록 실패 알림!*\n"
            f"- *사용자*: {user}\n"
            f"- *파일 이름*: {file_name}\n"
            f"- *등록 시간*: {created_at}\n"
            f"- *파일 경로*: {file_path}\n"
            f"- *오류 내용*: {str(e)}"
        )
        send_slack_notification(slack_message)

        return {"status": "error", "message": str(e)}



