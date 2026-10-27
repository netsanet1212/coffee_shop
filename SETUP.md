## Project Structure

```
/home/work/Documents/coffee_shop/
├── coffee_shop/              # Django project package
│   ├── settings.py           # Django settings
│   ├── urls.py               # URL routing
│   ├── wsgi.py               # WSGI entry point
│   └── asgi.py               # ASGI entry point
├── coffee_shop_app/          # Django app (coffee shop functionality)
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   ├── forms.py
│   └── migrations/
├── static/                   # Static assets (CSS, JS, images)
├── templates/                # HTML templates
├── media/                    # User uploaded media files
├── manage.py                 # Django management CLI
├── requirments.txt           # Python dependencies (note: intentional typo)
├── docker-compose.yml        # Docker service orchestration
├── Dockerfile                # Container build definition
├── .env                      # Environment variables (DB, secrets, etc.)
├── .dockerignore             # Files excluded from Docker build
├── .gitignore                # Git exclusions
├── db.sqlite3                # SQLite database (local dev)
└── SETUP.md                  # This file
```

## Docker Deployment

### Option 1: Using Docker Compose (Recommended)

```bash
cd /home/work/Documents/coffee_shop

# Start all services (web + MySQL database)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild after changes
docker-compose up -d --build
```

**Services:**
- `web`: Django app with Gunicorn (port 8000)
- `db`: MySQL 8.0 database (port 3306)

### Option 2: Manual Docker Build

```bash
cd /home/work/Documents/coffee_shop

# Build the image
docker build -t coffee_shop .

# Run the container (requires MySQL running separately)
docker run -p 8000:8000 \
  --env-file .env \
  --name coffee_shop_web \
  coffee_shop
```

### Access the Application
- **Web UI**: http://localhost:8000
- **Android Emulator**: http://10.0.2.2:8000