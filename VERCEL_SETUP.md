# Vercel Environment Variables Checklist

## Required Environment Variables in Vercel:

1. **DATABASE_URL**
   ```
   postgresql://neondb_owner:npg_8WHrSQcFh2sy@ep-silent-bread-a46ym48t-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require
   ```

2. **FLASK_ENV**
   ```
   production
   ```

3. **SECRET_KEY**
   ```
   your-secret-key-here-make-it-long-and-random
   ```

## How to Set in Vercel:

1. Go to your Vercel project dashboard
2. Click "Settings" tab
3. Click "Environment Variables" in the sidebar
4. Add each variable:
   - Name: DATABASE_URL
   - Value: [paste your Neon connection string]
   - Environment: Production, Preview, Development (check all)
5. Click "Save"
6. Repeat for FLASK_ENV and SECRET_KEY

## After Setting Variables:

1. Go to "Deployments" tab
2. Click "Redeploy" on the latest deployment
3. Wait for deployment to complete
4. Test login with: admin / password123

## If Still Not Working:

1. Check "Functions" tab for error logs
2. Check browser console for JavaScript errors
3. Verify the deployment is using the latest code
4. Make sure all environment variables are set for all environments (Production, Preview, Development)
