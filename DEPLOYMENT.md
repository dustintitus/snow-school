# Snow School - Production Deployment Guide

## Deployment to snowschool.app

### Prerequisites
- Python 3.9+
- PostgreSQL database (or SQLite for development)
- Domain: snowschool.app
- SSL Certificate (Let's Encrypt)

### Environment Setup

1. **Clone the repository**
```bash
git clone https://github.com/dustintitus/snow-school.git
cd snow-school
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set environment variables**
Create a `.env` file in the project root:
```bash
# .env file
FLASK_ENV=production
SECRET_KEY=your-very-secret-key-here-generate-with-openssl-rand-hex-32
DATABASE_URL=postgresql://user:password@localhost/snowschool
```

### Database Setup

1. **PostgreSQL Database**
```bash
sudo -u postgres psql
CREATE DATABASE snowschool;
CREATE USER snowschool_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE snowschool TO snowschool_user;
\q
```

2. **Initialize Database**
```bash
export FLASK_ENV=production
python3 -c "from app import app, db; app.app_context().push(); db.create_all()"
```

### Deployment with Gunicorn

1. **Start the application**
```bash
gunicorn --config gunicorn_config.py app:app
```

2. **Or using systemd service** (recommended)

Create `/etc/systemd/system/snowschool.service`:
```ini
[Unit]
Description=Snow School Application
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/snow-school
Environment="PATH=/path/to/snow-school/venv/bin"
Environment="FLASK_ENV=production"
ExecStart=/path/to/snow-school/venv/bin/gunicorn --config gunicorn_config.py app:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
```

Start the service:
```bash
sudo systemctl enable snowschool
sudo systemctl start snowschool
```

### Nginx Configuration

Create `/etc/nginx/sites-available/snowschool.app`:
```nginx
server {
    listen 80;
    server_name snowschool.app www.snowschool.app;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name snowschool.app www.snowschool.app;
    
    # SSL Configuration (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/snowschool.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/snowschool.app/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Gunicorn
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Static files
    location /static {
        alias /path/to/snow-school/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/snowschool.app /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### SSL Certificate (Let's Encrypt)

```bash
sudo certbot --nginx -d snowschool.app -d www.snowschool.app
```

### Firewall Configuration

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### Updating the Application

```bash
cd /path/to/snow-school
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart snowschool
```

### Monitoring

Check logs:
```bash
sudo journalctl -u snowschool -f
```

### Backup

Create a backup script:
```bash
#!/bin/bash
# backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U snowschool_user snowschool > /path/to/backups/snowschool_$DATE.sql
```

### Security Checklist

- [ ] Change default SECRET_KEY
- [ ] Use strong database passwords
- [ ] Enable HTTPS only
- [ ] Set up firewall rules
- [ ] Regular backups
- [ ] Keep dependencies updated
- [ ] Monitor logs
- [ ] Set up rate limiting (optional)

### Default Credentials

**Admin Login:**
- Username: `admin`
- Password: `admin123`

**IMPORTANT:** Change these credentials immediately after deployment!

### Support

For issues or questions, contact the development team.

