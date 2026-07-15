import sys
sys.path.append("/app")
from sqlalchemy.orm import Session
from sqlalchemy import select
from onyx.db.engine.sql_engine import get_sqlalchemy_engine, SqlEngine
from onyx.db.models import User

def test():
    SqlEngine.init_engine(pool_size=10, max_overflow=5)
    engine = get_sqlalchemy_engine()
    with Session(engine) as session:
        users = session.scalars(select(User)).unique().all()
        for u in users:
            print("User:", u.email, u.role)

test()
