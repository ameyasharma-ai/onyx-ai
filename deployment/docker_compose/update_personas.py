import sys
sys.path.append("/app")
from sqlalchemy.orm import Session
from onyx.db.engine.sql_engine import get_sqlalchemy_engine, SqlEngine
from onyx.db.models import Persona

def update():
    SqlEngine.init_engine(pool_size=10, max_overflow=5)
    engine = get_sqlalchemy_engine()
    with Session(engine) as session:
        personas = session.query(Persona).all()
        for p in personas:
            p.is_listed = True
        session.commit()
        print("Updated personas.")
update()
