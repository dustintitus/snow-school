# Snow School - Vercel Deployment Guide

## Deploy to snowschool.app on Vercel

### Quick Start

1. **Install Vercel CLI**
```bash
npm i -g vercel
```

2. **Login to Vercel**
```bash
vercel login
```

3. **Deploy**
```bash
vercel
```

4. **Set Production Domain**
```bash
vercel --prod
vercel domains add snowschool.app
```

### Environment Variables

Set these in your Vercel dashboard (Project Settings → Environment Variables):

#### Required:
```bash
FLASK_ENV=production
SECRET_KEY=generate-with-openssl-rand-hex-32
DATABASE_URL=your-postgres-connection-string
```

#### Database Options

**Option 1: Vercel Postgres (Recommended)**
1. Go to your Vercel project dashboard
2. Click "Storage" → "Create Database"
3. Select "Postgres"
4. The `DATABASE_URL` will be automatically set

**Option 2: External Database**
- **Neon**: https://neon.tech (Free tier available)
- **Supabase**: https://supabase.com (Free tier available)
- **PlanetScale**: https://planetscale.com (MySQL)
- **Railway**: https://railway.app

Connection string format: `postgresql://user:password@host:port/database`

### Database Setup

After deploying with a database, you need to initialize it:

**Option 1: Using Vercel CLI**
```bash
vercel env pull .env.local
python3 -c "from app import app, db; app.app_context().push(); db.create_all()"
```

**Option 2: Using Python Script**
Create a file `init_db.py`:
```python
from app import app, db, init_db

with app.app_context():
    init_db()
    print("Database initialized!")
```

Run it on Vercel's serverless environment:
```bash
vercel exec -- python3 -c "from app import app, db; app.app_context().push(); exec(open('init_db.py').read())"
```

### Manual Deployment Steps

1. **Push to GitHub** (if not already)
```bash
git push origin main
```

2. **Connect to Vercel**
- Go to https://vercel.com
- Click "Add New Project"
- Import your GitHub repository
- Vercel will auto-detect Python settings

3. **Configure Build Settings**
```
Build Command: (leave empty)
Install Command: pip install -r requirements.txt
Output Directory: (leave empty)
Root Directory: (leave empty)
```

4. **Add Environment Variables**
Go to Project Settings → Environment Variables and add:
- `FLASK_ENV` = `production`
- `SECRET_KEY` = Generate a secret key
- `DATABASE_URL` = Your database connection string

5. **Deploy**
Click "Deploy"

### Database Initialization

Since Vercel is serverless, you need to initialize the database separately:

**Using a one-time script:**
```bash
# Clone repo
git clone https://github.com/dustintitus/snow-school.git
cd snow-school

# Create init script
cat > init_vercel_db.py << 'EOF'
import os
os.environ['DATABASE_URL'] = 'your-connection-string'

from app import app, db, init_db

with app.app_context():
    init_db()
    print("✓ Database initialized")
EOF

# Run
python3 init_vercel_db.py
```

### Production Domain Setup

1. **In Vercel Dashboard:**
   - Go to your project
   - Settings → Domains
   - Add domain: `snowschool.app`
   - Add `www.snowschool.app` (optional)

2. **Configure DNS:**
   - Add CNAME record: `snowschool.app` → `cname.vercel-dns.com`
   - Or use Vercel's nameservers

### SSL Certificate

Vercel automatically provides SSL certificates for all domains. No additional configuration needed!

### Default Admin Credentials

- **Username**: `admin`
- **Password**: `admin123`

**⚠️ IMPORTANT**: Change these immediately after deployment!

### Troubleshooting

**Issue**: Database connection errors
**Solution**: Make sure `DATABASE_URL` is set correctly and database allows connections from Vercel IPs

**Issue**: Tables don't exist
**Solution**: Run the database initialization script

**Issue**: Static files not loading
**Solution**: Check that `vercel.json` routes `/static/*` correctly

**Issue**: Cold start too slow
**Solution**: Upgrade to Vercel Pro for better performance

### Monitoring

- Check logs: `vercel logs`
- Monitor errors in Vercel dashboard
- Set up alerts in Project Settings

### Updating the Application

1. Make changes locally
2. Commit and push to GitHub
3. Vercel automatically deploys

OR manually:
```bash
vercel --prod
```

### Cost

- **Hobby Plan**: Free for hobby projects
- **Pro Plan**: $20/month for production apps
- **Database**: Pay as you go (Vercel Postgres starts at $12/month)

### Security Checklist

- [ ] Change default SECRET_KEY
- [ ] Change admin credentials
- [ ] Use strong database passwords
- [ ] Enable Vercel Analytics (optional)
- [ ] Set up monitoring
- [ ] Review API rate limits
- [ ] Enable DDoS protection (Vercel Pro)
- [ ] Regular backups of database

### Support Resources

- Vercel Docs: https://vercel.com/docs
- Vercel Python Guide: https://vercel.com/docs/concepts/functions/serverless-functions/runtimes/python
- Community: https://github.com/vercel/vercel/discussions

