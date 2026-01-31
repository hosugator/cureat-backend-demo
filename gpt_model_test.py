from openai import OpenAI
import os
from dotenv import load_dotenv  # 추가

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
models = client.models.list()

for model in models:
    print(f"모델 ID: {model.id}")