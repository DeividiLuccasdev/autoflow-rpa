FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir "pip>=26.2,<27" && pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home autoflow && chown -R autoflow:autoflow /app
USER autoflow
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
