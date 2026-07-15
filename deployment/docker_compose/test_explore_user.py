import sys
sys.path.append("/app")
from sqlalchemy.orm import Session
from sqlalchemy import select
from onyx.db.engine.sql_engine import get_sqlalchemy_engine, SqlEngine
from onyx.db.persona import get_explore_personas_paginated
from onyx.db.models import Persona, User

def test():
    SqlEngine.init_engine(pool_size=10, max_overflow=5)
    engine = get_sqlalchemy_engine()
    with Session(engine) as session:
        user = session.scalars(select(User).limit(1)).first()
        print("Testing with user:", user.email)
        
        personas, total = get_explore_personas_paginated(
            user=user,
            db_session=session,
            query=None,
            category=None,
            sort_by="rating",
            page_num=0,
            page_size=20
        )
        print("Total returned:", total)
        for p in personas:
            print("Persona:", p.name)

test()
