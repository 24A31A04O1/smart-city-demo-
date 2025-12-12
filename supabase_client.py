
from supabase import create_client

# 🔹 Hard‑code your Supabase project details here
SUPABASE_URL = "https://rcrbazstbgqfmhzubmrg.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjcmJhenN0YmdxZm1oenVibXJnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1Nzc2NTMxMiwiZXhwIjoyMDczMzQxMzEyfQ.Y42dwejCsS66t0d-cMXaxL5Gxm9YuWx1JebUQelC5FQ"   # ⚠ Keep this private

# Create Supabase client with service role key
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
