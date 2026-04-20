import asyncio
from src.workflow.agent import root_agent

async def main():
    try:
        async for event in root_agent.run(node_input={'user_id': 1}):
            print("Event:", event)
    except TypeError as e:
        print("TypeError:", repr(e))
    except Exception as e:
        print("Exception:", repr(e))

if __name__ == '__main__':
    asyncio.run(main())
