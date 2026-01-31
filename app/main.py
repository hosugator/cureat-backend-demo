from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from . import service, schemas

app = FastAPI(
    title="Cureat Live Demo API - ECS 연동 테스트",
    description="광고 필터링 및 LLM 요약 기반 맛집 추천 엔진",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hosugator.com",  # 호수가토 실제 도메인
        "https://www.hosugator.com",  # 호수가토 실제 도메인
        "http://localhost:3000",  # 로컬 개발 테스트용
    ],
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드(GET, POST 등) 허용
    allow_headers=["*"],  # 모든 헤더 허용
)


@app.get("/", tags=["Health"])
def read_root():
    """ECS 로드밸런서의 상태 확인(Health Check)을 위한 엔드포인트입니다."""
    return {"status": "healthy", "message": "Cureat Demo Server is running"}


@app.post(
    "/recommendations", response_model=schemas.RecommendationResponse, tags=["Demo"]
)
def get_recommendations(request: schemas.ChatRequest):
    """
    사용자의 자연어 요청을 받아 맛집을 추천합니다.
    DB 없이 실시간 크롤링 및 분석 로직으로만 작동합니다.
    """
    try:
        # service.py에서 정의한 간소화된 함수 호출
        recommendation_data = service.get_personalized_recommendation(request)
        return recommendation_data
    except Exception as e:
        # 데모 환경에서 발생할 수 있는 에러 처리
        raise HTTPException(status_code=500, detail=f"추천 생성 중 오류 발생: {str(e)}")


# (필요 시) 코스 생성 API 등 추가 기능도 같은 방식으로 service 연결 가능
