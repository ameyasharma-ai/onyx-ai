from sqlalchemy import select, update
from onyx.db.engine.sql_engine import get_session
from onyx.db.models import Persona, User

db_session = next(get_session())
try:
    # 1. Get user ameyasharma401@gmail.com
    user = db_session.execute(select(User).where(User.email == "ameyasharma401@gmail.com")).scalar_one_or_none()
    if not user:
        print("User not found!")
    else:
        print(f"Found user: {user.id}")
        # 2. Update personas
        personas = db_session.execute(select(Persona).where(Persona.builtin_persona == False)).scalars().all()
        for p in personas:
            p.user_id = user.id
            if p.name == "Girlfriend" or p.name == "Oprah" or p.name == "Taylor Swift":
                p.voice_id = "af_bella" # Female voice
            else:
                p.voice_id = "am_echo" # Male voice for Elon Musk, Jeff Bezos, John McAfee
            print(f"Updated persona {p.name} with user_id {p.user_id} and voice {p.voice_id}")
        db_session.commit()
        print("Done updating personas.")
finally:
    db_session.close()
