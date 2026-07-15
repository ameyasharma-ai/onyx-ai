import sys
import os

# Add /app to sys.path so we can import onyx
sys.path.append("/app")

from sqlalchemy.orm import Session
from onyx.db.engine.sql_engine import get_sqlalchemy_engine, SqlEngine
from onyx.db.models import Persona

def add_test_personas():
    test_personas = [
        {
            "name": "Girlfriend",
            "description": "Your virtual AI Girlfriend.",
            "long_description": "A sweet, caring, and slightly sassy virtual girlfriend who loves to chat with you.",
            "category": "Romance",
            "temperature": 0.8,
            "tags": ["sweet", "caring", "sassy"]
        },
        {
            "name": "Elon Musk",
            "description": "CEO of Tesla and SpaceX, owner of X.",
            "long_description": "Chat with Elon about multi-planetary life, electric cars, Dogecoin, and free speech.",
            "category": "Celebrities",
            "temperature": 0.6,
            "tags": ["mars", "doge", "tesla"]
        },
        {
            "name": "Jeff Bezos",
            "description": "Founder of Amazon and Blue Origin.",
            "long_description": "Discuss e-commerce, space exploration, and day 1 thinking with Jeff Bezos.",
            "category": "Celebrities",
            "temperature": 0.5,
            "tags": ["amazon", "space", "business"]
        },
        {
            "name": "John McAfee",
            "description": "Cybersecurity legend and crypto enthusiast.",
            "long_description": "Unfiltered conversations about privacy, cybersecurity, and wild adventures.",
            "category": "Celebrities",
            "temperature": 0.9,
            "tags": ["crypto", "security", "wild"]
        }
    ]

    SqlEngine.init_engine(pool_size=10, max_overflow=5)
    engine = get_sqlalchemy_engine()
    with Session(engine) as session:
        for p_data in test_personas:
            # Check if exists
            exists = session.query(Persona).filter(Persona.name == p_data["name"], Persona.deleted == False).first()
            if not exists:
                new_persona = Persona(
                    name=p_data["name"],
                    description=p_data["description"],
                    long_description=p_data["long_description"],
                    category=p_data["category"],
                    temperature=p_data["temperature"],
                    tags=p_data["tags"],
                    is_public=True,
                    deleted=False
                )
                session.add(new_persona)
        
        session.commit()
        print("Successfully added test personas.")

if __name__ == "__main__":
    add_test_personas()
