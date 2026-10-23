import os
from dotenv import load_dotenv

load_dotenv()

ML_CLIENT_ID = os.getenv("ML_CLIENT_ID", "")
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET", "")
ML_REDIRECT_URI = os.getenv("ML_REDIRECT_URI", "http://localhost:8000/auth/callback")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "dev-secret")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ml_dashboard.db")

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_API_BASE = "https://api.mercadolibre.com"
