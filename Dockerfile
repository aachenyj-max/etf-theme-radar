FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY etf_theme_radar ./etf_theme_radar
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "etf_theme_radar.api:app", "--host", "0.0.0.0", "--port", "8000"]

