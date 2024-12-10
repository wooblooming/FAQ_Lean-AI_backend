import pandas as pd
import glob
import os
import sqlite3
import json
from datetime import datetime
import logging

logger = logging.getLogger('faq')

# CSV 파일 병합 함수
def merge_csv_files(folder_path, db_path='db.sqlite3'):
    # 폴더 내 모든 CSV 파일 경로 가져오기
    csv_files = glob.glob(os.path.join(folder_path, '*.csv'))

    if not csv_files:
        #logger.debug("CSV 파일을 찾을 수 없습니다. 경로를 확인해주세요.")
        return None

    df_list = []
    for file in csv_files:
        try:
            # 필요한 열(2, 6번째 열)만 선택하여 읽기
            df = pd.read_csv(file, encoding='utf-8', usecols=[1, 5])  # 2열(agent_id), 6열(user_utterances)
            df_list.append(df)
        except FileNotFoundError:
            logger.error(f"파일을 찾을 수 없습니다: {file}")
        except pd.errors.EmptyDataError:
            logger.warning(f"빈 파일입니다: {file}")
        except ValueError as ve:
            logger.error(f"열 인덱스가 잘못되었습니다. 파일을 확인해주세요: {file}, 오류 메시지: {ve}")
        except Exception as e:
            logger.error(f"파일을 읽는 중 오류 발생: {file}, 오류 메시지: {e}")

    if df_list:
        # CSV 데이터 병합
        merged_df = pd.concat(df_list, ignore_index=True)

        # 병합된 데이터의 첫 번째 agent_id 가져오기
        first_agent_id = merged_df['agent_id'].iloc[0]

        # SQLite 데이터베이스 연결 및 특정 agent_id의 webhook_questionlog 테이블 데이터 가져오기
        with sqlite3.connect(db_path) as conn:
            query = "SELECT questions FROM webhook_questionlog WHERE agent_id = ?"
            webhook_data = pd.read_sql(query, conn, params=(first_agent_id,))

        # questions 필드에서 JSON 데이터를 파싱하고, question 값만 추출
        def extract_questions(questions_json):
            try:
                questions_list = json.loads(questions_json)
                # questions_list가 리스트일 경우, 각 항목에서 question 키 추출
                if isinstance(questions_list, list):
                    return [item.get("question", "") for item in questions_list if isinstance(item, dict)]
                return []
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"JSON 형식이 올바르지 않거나 데이터가 누락되었습니다: {questions_json}")
                return []

        # question 값 추출 후 새로운 행으로 추가
        if not webhook_data.empty:
            questions = extract_questions(webhook_data['questions'].iloc[0])
            for question in questions:
                new_row = {'agent_id': first_agent_id, 'user_utterances': question}
                merged_df = pd.concat([merged_df, pd.DataFrame([new_row])], ignore_index=True)

        # 병합된 데이터프레임을 지정된 폴더에 CSV로 저장
        output_path = os.path.join(folder_path, f"public_merged_output_{datetime.now().strftime('%Y-%m-%d')}.csv")
        merged_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        #logger.debug("병합된 파일이 성공적으로 저장되었습니다.")
        return output_path
    else:
        #logger.debug("병합할 데이터가 없습니다. 모든 파일이 비어있거나 오류가 발생했습니다.")
        return None
