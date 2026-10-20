FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd --create-home --uid 1000 app && mkdir -p data backups reports && chown -R app:app /srv
USER app
EXPOSE 8000
CMD ["python", "-m", "app.cli", "serve"]
