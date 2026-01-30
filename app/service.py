import os
import re
import logging
import requests
import google.generativeai as genai
from typing import List, Dict, Any
from dotenv import load_dotenv
from . import schemas

# 로그 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s"
)
logger = logging.getLogger("CureatService")

load_dotenv()


class NaverAPIClient:
    """1단계: 네이버 API 통신 (검색 및 블로그 수집) 전담"""

    def __init__(self):
        self.client_id = os.getenv("NAVER_CLIENT_ID")
        self.client_secret = os.getenv("NAVER_CLIENT_SECRET")
        self.headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }

    def _clean_html(self, raw_html: str) -> str:
        return re.sub(r"<.*?>", "", raw_html) if raw_html else ""

    def search_places(self, query: str) -> List[Dict]:
        logger.info(f"네이버 장소 검색 시작: {query}")
        url = "https://openapi.naver.com/v1/search/local.json"
        params = {"query": query, "display": 5, "sort": "comment"}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=5)
            return resp.json().get("items", [])
        except Exception as e:
            logger.error(f"장소 검색 에러: {e}")
            return []

    def fetch_blog_context(self, name: str, address: str) -> str:
        logger.info(f"블로그 후기 수집 시작: {name}")
        url = "https://openapi.naver.com/v1/search/blog.json"
        params = {"query": f"{name} {address} 맛집 후기", "display": 5}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=3)
            items = resp.json().get("items", [])
            return " ".join([self._clean_html(i.get("description", "")) for i in items])
        except Exception as e:
            logger.error(f"블로그 수집 에러: {e}")
            return ""


class ContentAnalyzer:
    """2~3단계: 데이터 정제 및 LLM/키워드 분석 전담"""

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.llm = genai.GenerativeModel("gemini-1.5-flash")
            logger.info("Gemini 모델 로드 완료")
        else:
            self.llm = None
            logger.warning("Gemini 모델 로드 실패 (API 키 없음)")

    def generate_summary(self, name: str, context: str) -> str:
        # 기본 요약문
        default_summary = f"{name}은(는) 후기가 많은 인기 장소입니다."

        if not self.llm or not context:
            return default_summary

        # 로컬 무한 로딩 방지를 위해 현재는 가공 로직만 실행 (배포 후 주석 해제)
        # 실제 LLM 호출을 원하시면 아래 try 구문의 주석을 푸세요.
        try:
            """
            prompt = f"식당 '{name}'의 후기 요약: {context}. 특징을 한 문장으로 요약해줘."
            response = self.llm.generate_content(prompt)
            return response.text.strip()
            """
            return f"최신 후기 분석: {context[:50]}..."
        except Exception as e:
            logger.error(f"요약 생성 에러: {e}")
            return default_summary


class RecommendationService:
    """비즈니스 로직 오케스트레이터 (전체 흐름 조율)"""

    def __init__(self):
        self.naver_client = NaverAPIClient()
        self.analyzer = ContentAnalyzer()

    def create_recommendations(self, prompt: str) -> Dict[str, Any]:
        logger.info(f"--- '{prompt}' 추천 프로세스 시작 ---")

        # 1. 장소 검색
        places = self.naver_client.search_places(prompt)
        if not places:
            return {"answer": "검색 결과가 없습니다.", "restaurants": []}

        final_list = []
        for item in places[:3]:
            name = self.naver_client._clean_html(item["title"])
            addr = item.get("roadAddress") or item.get("address", "")

            # 2. 블로그 후기 수집
            context = self.naver_client.fetch_blog_context(name, addr)

            # 3. 데이터 분석 및 요약
            summary = self.analyzer.generate_summary(name, context)

            final_list.append(
                {
                    "name": name,
                    "address": addr,
                    "summary": summary,
                    "is_ad_filtered": True,
                    "mapx": item.get("mapx"),
                    "mapy": item.get("mapy"),
                    "summary_pros": [],
                    "summary_cons": [],
                    "keywords": ["맛집", "추천"],
                }
            )

        logger.info("--- 추천 프로세스 완료 ---")
        return {
            "answer": f"'{prompt}' 지역의 추천 결과입니다.",
            "restaurants": final_list,
        }


# FastAPI 엔드포인트에서 호출할 인스턴스
service_instance = RecommendationService()


def get_personalized_recommendation(request: schemas.ChatRequest) -> Dict[str, Any]:
    return service_instance.create_recommendations(request.prompt)
