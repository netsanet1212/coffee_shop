# Coffee Shop — Setup & Build Guide (MySQL + Docker)

Quick reference for the two phases implemented.

---
## 1. Database (MySQL)

### Config
- `coffee_shop/settings.py` uses `django.db.backends.mysql` (env-based).
- `requirments.txt` has `mysqlclient`.

### Setup DB
```bash
mysql -u root -p <<EOF
CREATE DATABASE coffee_shop_prod;
CREATE USER 'coffee_shop_user'@'localhost' IDENTIFIED BY 'coffee_shop_pass';
GRANT ALL PRIVILEGES ON coffee_shop_prod.* TO 'coffee_shop_user'@'localhost';
EOF
```

### Migrate
```bash
python manage.py migrate
python manage.py createsuperuser
```

---
## 2. Docker

### Files
- `Dockerfile` (multi-stage, mysqlclient, gunicorn)
- `docker-compose.yml` (web + mysql:8)
- `.env` (DB, DEBUG, SECRET_KEY)

### Build & Run
```bash
docker compose up --build -d
```

### Test
```bash
curl http://localhost:8000
```

---
## Environment
- `.env` controls DB/host/DEBUG/ALLOWED_HOSTS.
- `ALLOWED_HOSTS` includes `localhost,127.0.0.1,0.0.0.0,10.0.2.2`.
