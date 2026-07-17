import asyncio
from onyx.db.engine.sql_engine import SqlEngine, get_session_with_current_tenant
from onyx.server.features.tool.api import list_tools

async def main():
    SqlEngine.init_engine(pool_size=5, max_overflow=10)
    
    with get_session_with_current_tenant() as session:
        tools = list_tools(db_session=session, _=None)
        print('Tools from API:')
        for t in tools:
            print(t.name, t.in_code_tool_id)

if __name__ == '__main__':
    asyncio.run(main())
