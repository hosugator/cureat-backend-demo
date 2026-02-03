import os
import re
import logging
import requests
import google.generativeai as genai
from typing import List, Dict, Any
from dotenv import load_dotenv
from . import schemas
from openai import OpenAI
import json

# 로그 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s"
)
logger = logging.getLogger("CureatService")

if os.path.exists(".env.test"):
    load_dotenv(".env.test")
    logger.info("Loaded environment variables from .env.test")
else:
    # 파일이 없으면 시스템 환경 변수(ECS)를 그대로 사용
    logger.info("Using system environment variables (ECS/Production)")


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
        api_key = os.getenv("OPENAI_API_KEY")

        if api_key:
            self.client = OpenAI(api_key=api_key)
            self.model = "gpt-4o-mini"
            logger.info("OpenAI 클라이언트가 성공적으로 초기화되었습니다.")
        else:
            self.client = None
            logger.error("!!! OPENAI_API_KEY를 찾을 수 없습니다 !!!")

    def analyze_restaurant(
        self, name: str, context: str, language: str = "ko"
    ) -> Dict[str, Any]:
        # 클라이언트 체크 로그 추가
        if not self.client:
            logger.error("OpenAI 클라이언트 미설정으로 기본값을 반환합니다.")
            return {
                "summary": f"{name}은 인기 맛집입니다.",
                "pros": ["맛"],
                "cons": ["대기"],
            }

        if not context or len(context.strip()) < 10:
            logger.warning(f"[{name}] 분석할 리뷰 텍스트가 너무 짧습니다.")
            return {
                "summary": f"{name}은 리뷰 정보가 부족한 인기 맛집입니다.",
                "pros": ["접근성"],
                "cons": ["리뷰 부족"],
            }

        rich_context = context[:2000].strip()

        target_lang = "English" if language == "en" else "Korean"  # 언어 설정

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a food critic. Summarize the following reviews in {target_lang}."
                        'Respond ONLY in JSON format: {"summary": "...", "pros": ["..."], "cons": ["..."]}',
                    },
                    {
                        "role": "user",
                        "content": f"Restaurant: {name}\nReviews: {rich_context}",
                    },
                ],
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            logger.info(f"[{name}] GPT 응답 수신 완료")
            return json.loads(content)

        except Exception as e:
            # 에러의 정체를 로그로 정확히 찍습니다.
            logger.error(f"[{name}] GPT 분석 중 실제 에러 발생: {str(e)}")
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

    def create_recommendations_v2(self, request: schemas.ChatRequest) -> Dict[str, Any]:
        prompt = request.prompt
        language = request.language
        logger.info(f"--- [V2] '{prompt}' ({language}) 프로세스 시작 ---")

        # [Step 0] 쿼리 최적화 (유저 입력을 한국어 검색어로 변환)
        search_query = prompt
        if language == "en":
            try:
                opt_resp = self.analyzer.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional Korean search optimizer. "
                            "Translate the user input into 1-2 essential Korean keywords for Naver Maps. "
                            "Reply ONLY with the keywords. No explanation. "
                            "Example Input: 'Good sushi in Gangnam' -> Output: '강남역 스시'",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=20,
                    temperature=0,  # 결과의 일관성을 위해 0으로 설정
                )
                search_query = opt_resp.choices[0].message.content.strip()
                # GPT가 따옴표 등을 포함할 수 있으므로 제거
                search_query = search_query.replace('"', "").replace("'", "")
                logger.info(f"[V2] 최적화된 키워드: {search_query}")
            except Exception as e:
                logger.error(f"키워드 최적화 실패: {e}")

        # [Step 1] 최적화된 키워드로 검색
        places = self.naver_client.search_places(search_query)
        if not places:
            return {"answer": "검색 결과가 없습니다.", "restaurants": []}

        final_list = []
        for item in places[:3]:
            # 1. 네이버 API에서 가져온 원본 한글 데이터 유지
            ko_name = self.naver_client._clean_html(item["title"])
            ko_addr = item.get("roadAddress") or item.get("address", "")

            # 2. 블로그 후기 수집 (반드시 '한글' 이름과 주소로 검색해야 함)
            blog_results = self.naver_client.fetch_blog_context(ko_name, ko_addr)

            # 3. LLM 분석 수행 (한글 데이터를 바탕으로 분석)
            analysis = self.analyzer.analyze_restaurant(
                ko_name, blog_results["context"], language=language
            )

            # 4. 사용자에게 보여줄 변수 설정 (기본은 한글)
            display_name = ko_name
            display_addr = ko_addr

            # 5. [핵심] 만약 영어 모드라면, 수집/분석이 끝난 후 최종 노출용 데이터만 번역
            if language == "en":
                try:
                    trans_resp = self.analyzer.client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "system",
                                "content": "Translate the restaurant name and address into English for tourists. "
                                'Reply ONLY in JSON: {"name": "...", "address": "..."}',
                            },
                            {
                                "role": "user",
                                "content": f"Name: {ko_name}\nAddress: {ko_addr}",
                            },
                        ],
                        response_format={"type": "json_object"},
                    )
                    trans_data = json.loads(trans_resp.choices[0].message.content)
                    display_name = trans_data.get("name", ko_name)
                    display_addr = trans_data.get("address", ko_addr)
                except Exception as e:
                    logger.error(f"Translation failed: {e}")

            final_list.append(
                {
                    "name": f"{ko_name} ({display_name})",
                    "address": display_addr,
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
            "answer": f"Search: '{prompt}'",
            "restaurants": final_list,
        }

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
