FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=0 \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

# The free Render tier has no persistent disk, so the SQLite demo DB is
# rebuilt on every start. That's fine: the data is fictional.
# `exec` hands PID 1 to gunicorn so it receives stop signals directly
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_demo --if-empty && exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60"]
