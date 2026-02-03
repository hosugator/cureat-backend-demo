from pydantic import BaseModel, Field
from typing import Optional, List


class ChatRequest(BaseModel):
    prompt: str = Field(..., example="강남역 맛집")
    language: str = Field("ko", example="en")  # 추가: 기본값은 ko


# --- 음식점 상세 정보 스케마 (데모용) ---
class RestaurantDetail(BaseModel):
    name: str
    address: Optional[str] = None
    image_url: Optional[str] = None
    mapx: Optional[str] = None
    mapy: Optional[str] = None

    # AI 및 분석 정보
    summary: Optional[str] = Field(None, description="LLM 요약 정보")
    is_ad_filtered: bool = Field(False, description="광고 필터링 여부")
    filtered_ad_count: int = Field(0, description="광고 필터링된 개수")

    # 기존 복잡한 필드들은 시각적 간결함을 위해 필수로 유지할 것만 선택
    summary_pros: Optional[List[str]] = None
    summary_cons: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    nearby_attractions: Optional[List[str]] = None


# --- API 요청/응답 스케마 ---
# class ChatRequest(BaseModel):
#     """라이브 데모에서는 user_id를 생략하고 프롬프트만 받습니다."""

#     prompt: str = Field(..., example="강남역 맛집")


class RecommendationResponse(BaseModel):
    answer: str
    restaurants: List[RestaurantDetail]
