FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    ffmpeg \
    libffi-dev \
    libsodium-dev \
    unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV DENO_INSTALL=/usr/local
ENV DATABASE_PATH=/data/config.db
RUN curl -fsSL https://deno.land/install.sh | sh
RUN mkdir -p /data

WORKDIR /app

COPY requirements.txt .

ARG CACHE_BUST=20260516b
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade "yt-dlp[default]" "PyNaCl>=1.5.0" "discord.py[voice]"

COPY . .

CMD ["python", "bot.py"]
