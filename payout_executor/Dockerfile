FROM python:3.12-slim
WORKDIR /app
COPY payout_executor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY payout_executor/app.py ./app.py
ENV PORT=8000
CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
