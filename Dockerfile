# 1. 파이썬 버전 상향 (현재 환경이 3.13이므로 최소 3.11 이상 권장)
FROM python:3.11-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 시스템 의존성 설치 (필요 시)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. 의존성 설치 (캐시 활용을 위해 COPY 순서 유지)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 소스 코드 복사
COPY . .

# 6. PYTHONPATH 설정 (중요: app 패키지를 인식시키기 위함)
ENV PYTHONPATH=/app

# 7. 포트 설정
EXPOSE 80

# 8. 실행 명령 (app.main:app 경로가 프로젝트 루트 기준인지 확인 필요)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]