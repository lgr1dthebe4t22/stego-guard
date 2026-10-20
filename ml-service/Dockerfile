# ML-сервис Stego-Guard: Python + DWT-пайплайн
FROM python:3.13-slim

# libgl1 — системная зависимость opencv-python
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# зависимости отдельным слоем — кэш не ломается при изменении кода
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir -r requirements.txt

# код сервиса (proto_gen уже сгенерирован и лежит в app/)
COPY app ./app

EXPOSE 50051
CMD ["python", "-m", "app.server"]