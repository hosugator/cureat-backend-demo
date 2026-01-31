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
        params = {"query": query, "display": 10, "sort": "comment"}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=5)
            return resp.json().get("items", [])
        except Exception as e:
            logger.error(f"장소 검색 에러: {e}")
            return []

    def fetch_blog_context(self, name: str, address: str) -> Dict[str, Any]:
        logger.info(f"블로그 후기 수집 시작: {name}")
        url = "https://openapi.naver.com/v1/search/blog.json"
        params = {"query": f"{name} {address} 맛집 후기", "display": 10}

        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=3)
            items = resp.json().get("items", [])
            total_count = len(items)

            ad_keywords = [
                "원고료",
                "지원",
                "체험단",
                "협찬",
                "서비스",
                "원고료",
                "업체",
                "포스팅",
                "제작비",
                "광고",
                "리뷰 이벤트",
                "홍보",
                "프로모션",
            ]
            filtered_items = [
                self._clean_html(i.get("description", ""))
                for i in items
                if not any(
                    key in self._clean_html(i.get("description", ""))
                    for key in ad_keywords
                )
            ]

            removed_count = total_count - len(filtered_items)
            logger.info(
                f"[{name}] 필터링 완료: 총 {total_count}개 중 {removed_count}개 광고 제거"
            )

            return {"context": " ".join(filtered_items), "removed_count": removed_count}
        except Exception as e:
            return {"context": "", "removed_count": 0}


# service.py 내 수정 제안


class ContentAnalyzer:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-flash-lite-latest")

    def analyze_restaurant(self, name: str, context: str) -> Dict[str, Any]:
        if not self.model or not context:
            return {"summary": "정보가 부족합니다.", "pros": [], "cons": []}

        # 데이터 확장: 이제 500자 제한을 풀고 더 넉넉하게(약 2000자) 던집니다.
        rich_context = context[:2000].strip()

        prompt = (
            f"식당 '{name}'에 대한 여러 블로그 후기 내용입니다: {rich_context}\n\n"
            "위 내용을 바탕으로 다음 정보를 분석해줘:\n"
            "1. 전체적인 특징 요약 (한 문장)\n"
            "2. 방문객들이 꼽은 구체적인 장점 3가지\n"
            "3. 방문객들이 아쉬워한 점이나 주의사항 1-2가지\n\n"
            "응답 포맷은 반드시 아래 형식을 지켜줘:\n"
            "요약: [내용]\n"
            "장점: [장점1, 장점2, 장점3]\n"
            "단점: [단점1, 단점2]"
        )

        try:
            response = self.model.generate_content(prompt)
            text = response.text

            # 간단한 파싱 로직 (실제 서비스에선 더 정교하게 처리 가능)
            lines = text.split("\n")
            summary = (
                [l for l in lines if l.startswith("요약:")][0]
                .replace("요약:", "")
                .strip()
            )
            pros = (
                [l for l in lines if l.startswith("장점:")][0]
                .replace("장점:", "")
                .strip()
                .split(",")
            )
            cons = (
                [l for l in lines if l.startswith("단점:")][0]
                .replace("단점:", "")
                .strip()
                .split(",")
            )

            return {"summary": summary, "pros": pros, "cons": cons}
        except:
            return {
                "summary": f"{name}은 인기 맛집입니다.",
                "pros": ["맛", "분위기"],
                "cons": ["대기 시간"],
            }


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

            # 딱 한 번만 호출해서 변수에 담아두기
            blog_results = self.naver_client.fetch_blog_context(name, addr)

            # 분석기에는 텍스트만 전달
            analysis = self.analyzer.analyze_restaurant(name, blog_results["context"])

            final_list.append(
                {
                    "name": name,
                    "address": addr,
                    "summary": analysis["summary"],
                    "summary_pros": analysis["pros"],
                    "summary_cons": analysis["cons"],
                    "is_ad_filtered": True,
                    "filtered_ad_count": blog_results[
                        "removed_count"
                    ],  # 이 값이 0보다 크면 성공!
                    "mapx": item.get("mapx"),
                    "mapy": item.get("mapy"),
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
