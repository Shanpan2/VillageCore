FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

WORKDIR /app

COPY requirements.txt .

# キャッシュ破棄用（変更するたびにpip installが再実行される）
ARG CACHE_BUST=20260515b
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]