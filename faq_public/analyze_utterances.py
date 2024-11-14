import pandas as pd
from collections import Counter
import re
import os
import matplotlib.pyplot as plt
from matplotlib import font_manager
from konlpy.tag import Okt

# Okt 형태소 분석기 초기화
okt = Okt()

# NanumGothic 폰트를 설정하는 함수
def set_font():
    font_path = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
    if os.path.exists(font_path):
        font_name = font_manager.FontProperties(fname=font_path).get_name()
        plt.rcParams['font.family'] = font_name

# 어근 추출을 통한 텍스트 정규화 함수
def normalize_text(text):
    tokens = okt.morphs(text, stem=True)  # 형태소 분석 및 어근 추출
    return ' '.join(tokens)

# 가장 많이 언급된 user_utterances를 반환하는 함수
def get_most_common_utterances(file_path):
    try:
        # CSV 파일 불러오기
        merged_df = pd.read_csv(file_path, encoding='utf-8')
        if 'user_utterances' in merged_df.columns:
            # user_utterances 컬럼의 결측치 제거 및 정규화
            user_utterances = merged_df['user_utterances'].dropna().apply(normalize_text)
            
            # 특정 단어 필터링 및 특수 문자 제거
            filtered_utterances = [utterance for utterance in user_utterances if utterance not in ['안녕', 'HOME']]
            filtered_utterances = [re.sub(r'[^가-힣a-zA-Z\s]', '', utterance) for utterance in filtered_utterances]
            
            # 가장 많이 언급된 문장 집계
            utterance_counts = Counter(filtered_utterances)
            most_common_utterances = utterance_counts.most_common(5)
            return [{"utterance": utterance, "count": count} for utterance, count in most_common_utterances]
        else:
            raise ValueError("'user_utterances' 열을 찾을 수 없습니다.")
    except FileNotFoundError:
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")
    except Exception as e:
        raise e

# 가장 많이 언급된 user_utterances의 그래프를 저장하는 함수
def save_most_common_utterances_graph(data, output_image_path):
    set_font()  # 폰트 설정
    labels, counts = zip(*[(item['utterance'], item['count']) for item in data])
    
    # 긴 문장 줄바꿈 처리
    labels = [label if len(label) <= 10 else '\n'.join([label[i:i+10] for i in range(0, len(label), 10)]) for label in labels]
    
    # 그래프 생성 및 저장
    plt.figure(figsize=(8, 6))
    plt.bar(labels, counts)
    plt.xlabel('질문', color='blue')
    plt.ylabel('질문 횟수', color='green')
    plt.title('가장 많이 질문한 내용')
    plt.savefig(output_image_path, format='png')
    plt.close()
