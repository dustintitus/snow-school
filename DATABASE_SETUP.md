# Database Setup for Snow School on Vercel

## Recommended: Neon (Free PostgreSQL)

### Quick Setup:

1. **Create Account**:
   - Go to: https://neon.tech
   - Sign up (free tier available)

2. **Create Project**:
   - Click "Create Project"
   - Name it: `snowschool-production`
   - Select a region close to your users

3. **Get Connection String**:
   - After creating project, click "Connection Details"
   - Copy the connection string
   - It looks like: `postgresql://user:password@ep-example-123456.us-east-2.aws.neon.tech/snowschool`

4. **Add to Vercel**:
   - Go to your Vercel project
   - Settings → Environment Variables
   - Add: `DATABASE_URL` = (paste your connection string)

### Alternative Options:

**Supabase** (Free):
- https://supabase.com
- Connection string format: Same as PostgreSQL

**Vercel Postgres** (if available in your plan):
- Built into Vercel dashboard
- Storage → Create Database → Postgres
- Auto-creates DATABASE_URL

## Complete Environment Variables for Vercel:

```
FLASK_ENV=production
SECRET_KEY=your-random-secret-key-here-generate-with-openssl-rand-hex-32
DATABASE_URL=postgresql://user:pass@host:5432/database
```

## After Setting DATABASE_URL:

1. Deploy will work with database connection
2. Tables will be created automatically on first request
3. You can still initialize sample data manually if needed

## Initialize Database Tables:

The app will create tables automatically when first accessed. If you want to add sample data, run this locally:

```python
from app import app, init_db
with app.app_context():
    init_db()
```

