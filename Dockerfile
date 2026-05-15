FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y ffmpeg libffi-dev libsodium-dev && apt-get clean

WORKDIR /app

COPY requirements.txt .

ARG CACHE_BUST=20260515c
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "PyNaCl>=1.5.0" "discord.py[voice]"

COPY . .

CMD ["python", "bot.py"]