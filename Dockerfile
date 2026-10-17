FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PORT=7860
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fonts-noto-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-ai.txt /app/
RUN pip install --no-cache-dir -r requirements-ai.txt
COPY . /app
EXPOSE 7860
CMD ["python", "server.py"]
