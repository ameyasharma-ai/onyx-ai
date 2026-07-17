import asyncio
from onyx.db.engine.sql_engine import init_engine, get_session
from onyx.tools.tool_implementations.web_search.web_search_tool import WebSearchTool
from onyx.db.web_search import fetch_active_web_search_provider
from onyx.server.features.tool.api import list_tools

async def main():
    init_engine()
    with get_session() as session:
        provider = fetch_active_web_search_provider(session)
        print("Provider via get_session:", provider)
        
        # Test the endpoint exactly as it's run
        tools = list_tools(db_session=session, _=None)
        print("Tools from API:", [t.name for t in tools if 'web' in t.name or 'Web' in t.name])
        
        print("is_available:", WebSearchTool.is_available(session))

if __name__ == '__main__':
    asyncio.run(main())
