
																																																																																		# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies needed for mysqlclient
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirments.txt .

RUN pip install --no-cache-dir --user -r requirments.txt

# ---------- Runtime stage ----------
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime-only system deps for mysqlclient
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /root/.local /root/.local

# Copy project code
COPY manage.py ./
COPY coffee_shop/ ./coffee_shop/
COPY coffee_shop_app/ ./coffee_shop_app/
COPY static/ ./static/
COPY templates/ ./templates/

# Ensure scripts run from /root/.local/bin
ENV PATH=/root/.local/bin:$PATH

# Expose Django dev/prod port
EXPOSE 8000

# Run migrations, collectstatic, then start gunicorn
CMD ["bash", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn coffee_shop.wsgi:application --bind 0.0.0.0:8000  --workers 2 --threads 4 --timeout 120"]