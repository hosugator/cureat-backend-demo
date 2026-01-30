import os
import re
import logging
import requests
import google.generativeai as genai
from typing import List, Dict, Any
from dotenv import load_dotenv
from . import schemas

# 로그 설정: 시간과 단계를 명확히 표시
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    llm = genai.GenerativeModel("gemini-1.5-flash")
    logger.info("Gemini 모델 로드 완료")
else:
    llm = None
    logger.warning("GOOGLE_API_KEY가 설정되지 않았습니다.")

def _clean_html(raw_html: str) -> str:
    return re.sub(r"<.*?>", "", raw_html) if raw_html else ""

def search_naver_local(query: str) -> List[Dict]:
    logger.info(f"1단계: 네이버 지역 검색 시작 (쿼리: {query})")
    url = "https://openapi.naver.com/v1/search/local.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": 5, "sort": "comment"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        items = response.json().get("items", [])
        logger.info(f"1단계 완료: {len(items)}개의 장소를 찾았습니다.")
        return items
    except Exception as e:
        logger.error(f"1단계 에러 (네이버 지역): {e}")
        return []

def get_blog_context(place_name: str, address: str) -> str:
    logger.info(f"2단계: '{place_name}' 블로그 후기 수집 시작")
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": f"{place_name} {address} 맛집 후기", "display": 5}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=3)
        items = resp.json().get("items", [])
        snippets = [_clean_html(item.get("description", "")) for item in items]
        context = " ".join(snippets)
        logger.info(f"2단계 완료: {len(items)}개의 블로그 요약본 수집 성공")
        return context
    except Exception as e:
        logger.error(f"2단계 에러 (네이버 블로그): {e}")
        return ""

def get_personalized_recommendation(request: schemas.ChatRequest) -> Dict[str, Any]:
    logger.info("--- 추천 프로세스 시작 ---")
    items = search_naver_local(request.prompt)
    if not items:
        return {"answer": "결과를 찾을 수 없습니다.", "restaurants": []}

    final_recommendations = []
    for i, item in enumerate(items[:3]):
        name = _clean_html(item["title"])
        addr = item.get("roadAddress") or item.get("address", "")
        logger.info(f"[{i+1}/3] '{name}' 분석 중...")

        context = get_blog_context(name, addr)
        
        # 기본 요약문 설정 (Gemini 실패 시 대비)
        summary = f"{name}은(는) {addr} 인근에서 평점이 높은 곳입니다."
        
        if llm and context:
            # try:
            #     logger.info(f"[{i+1}/3] Gemini 요약 요청 전송 (최대 5초 대기)...")
                
            #     # 비즈니스 로직: Gemini 호출 시 요청 옵션에 타임아웃 개념 적용
            #     # 만약 여기서 계속 멈춘다면 네트워크가 구글 API를 차단하고 있을 가능성이 큽니다.
            #     prompt = f"식당 '{name}'의 후기 요약: {context}. 이 식당의 핵심 특징을 한 문장으로 친절하게 설명해줘."
                
            #     # request_options를 통해 응답 지연 시 프로세스 방어
            #     response = llm.generate_content(
            #         prompt,
            #         generation_config={"max_output_tokens": 100}
            #     )
                
            #     if response and response.text:
            #         summary = response.text.strip()
            #         logger.info(f"[{i+1}/3] Gemini 요약 완료")
            # except Exception as e:
            #     logger.error(f"[{i+1}/3] Gemini 단계 건너뜀 (사유: {e})")

            summary += f"최신 후기에 따르면: {context[:50]}..."
        
        final_recommendations.append({
            "name": name,
            "address": addr,
            "summary": summary,
            "is_ad_filtered": True,
            "mapx": item.get("mapx"),
            "mapy": item.get("mapy"),
            "summary_pros": [],
            "summary_cons": [],
            "keywords": []
        })

    logger.info("--- 모든 프로세스 완료 ---")
    return {"answer": f"'{request.prompt}'의 추천 맛집 리스트입니다.", "restaurants": final_recommendations}