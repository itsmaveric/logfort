from app import app
import logging

# Set up more verbose logging for debugging
logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
