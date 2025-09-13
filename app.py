import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Set up logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# configure the database, relative to the app instance folder
database_url = os.environ.get("DATABASE_URL", "sqlite:///tracking.db")

# Simplified database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max file size
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000

# Create upload directory if it doesn't exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# initialize the app with the extension
db.init_app(app)

with app.app_context():
    try:
        # Import models
        import models
        
        # Create all tables
        db.create_all()
        logging.info("Database tables created successfully")
    except Exception as e:
        logging.error(f"Failed to initialize database: {str(e)}")
        # Don't raise the exception here, let the app start but log the error
        pass

# Register routes after app context
from routes import *
