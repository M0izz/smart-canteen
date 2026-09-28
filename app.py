import os

os.environ["DATABASE_PATH"] = "/tmp/smart-canteen.db"

from backend.app import create_app

app = create_app()