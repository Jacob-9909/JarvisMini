import asyncio
from src.workflow.agent import root_agent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService

# Let's modify root_agent temporarily for this test
original_init = root_agent.graph.nodes[0] # assuming START is connected to init_node

async def main():
    runner = Runner(node=root_agent, session_service=InMemorySessionService(), auto_create_session=True)
    try:
        async for event in runner.run_async(user_id="1", session_id="test", state_delta={"user_id": 1}):
            print("Event:", getattr(event, 'event_type', type(event)))
    except Exception as e:
        print("Exception:", repr(e))

if __name__ == '__main__':
    asyncio.run(main())
