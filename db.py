# db.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

# usa o Postgres se DATABASE_URL existir; senao, o SQLite local
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/mercado.db")
# pool_pre_ping evita "PendingRollbackError: Can't reconnect until invalid
# transaction is rolled back" em scripts de longa duracao (ex.: coleta_cotahist.py,
# que fica minutos parseando um arquivo antes de voltar a consultar o banco) -
# o Postgres remoto (Neon) derruba conexoes ociosas; pre_ping testa a conexao
# antes de usar e reconecta sozinho se precisar, sem custo perceptivel no caso
# comum (conexao viva).
engine = create_engine(DATABASE_URL, pool_pre_ping=True)