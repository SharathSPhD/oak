FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir streamlit httpx

COPY app.py .
COPY pages/ pages/

EXPOSE 8501
HEALTHCHECK CMD python -c "import httpx; httpx.get('http://localhost:8501/_stcore/health', timeout=5)" || exit 1
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
