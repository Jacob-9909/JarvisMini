import asyncio
import argparse
import logging
from src.workflow.agent import root_agent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    parser = argparse.ArgumentParser(description="BookChecker Agent")
    parser.add_argument("--mock", action="store_true", help="Run with mock data locally")
    args = parser.parse_args()

    logger.info("=========================================")
    logger.info("BookChecker Agent (ADK 2.0)")
    logger.info("To run the interactive UI workflow:")
    logger.info("  uv run adk web agents")
    logger.info("Then select 'bookchecker_workflow'")
    logger.info("=========================================")
    
    # You could also run the agent programmatically here
    # e.g. await root_agent.arun(...)
    
if __name__ == "__main__":
    asyncio.run(main())
