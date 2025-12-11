FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir gunicorn

# Copy application
COPY . .

EXPOSE 8080

# Honor $PORT if provided (Replit/heroku-style), fallback 8080
CMD ["/bin/sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT:-8080} app:app"]
