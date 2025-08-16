import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'prasannabollineni'
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg','mov', 'jpeg', 'gif', 'mp4', 'webm', 'ogg'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size


    # MongoDB Configuration
    # For local MongoDB:
    

    MONGO_URI = os.environ.get('MONGO_URI') or "mongodb+srv://prasannabollineni2:pwd@cluster0.ngdtd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    MONGO_DB_NAME = "digital_signage_db" # Name of your database within MongoDB

    # If using MongoDB Atlas, your MONGO_URI would look something like this:
    # MONGO_URI = os.environ.get('MONGO_URI') or "mongodb+srv://<username>:<password>@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority"
    # Make sure to replace <username> and <password> with your Atlas database user credentials.

    # It's best practice to load this from environment variables.
