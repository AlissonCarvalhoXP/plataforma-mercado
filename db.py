# db.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

# usa o Postgres se DATABASE_URL existir; senao, o SQLite local
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/mercado.db")
engine = create_engine(DATABASE_URL)