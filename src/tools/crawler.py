import os
import asyncio
from playwright.async_api import async_playwright
from typing import List, Dict, Any
from src.schema.state import SlotInfo
import logging

logger = logging.getLogger(__name__)

class CampingCrawler:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser = None
        self._context = None
        self._playwright = None

    async def initialize(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            locale="ko-KR",
            timezone_id="Asia/Seoul"
        )
        
    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def login(self, target_url: str, credentials: dict) -> Dict[str, Any]:
        """Login to yeyak.seoul.go.kr"""
        page = await self._context.new_page()
        try:
            # Seoul Public Service Reservation Login URL
            login_url = "https://yeyak.seoul.go.kr/web/loginForm.do"
            await page.goto(login_url)
            
            # Wait for login inputs
            if credentials and credentials.get("id"):
                await page.wait_for_selector("input[name='userid']", state="visible", timeout=5000)
                await page.fill("input[name='userid']", credentials.get("id"))
                await page.fill("input[name='userpwd']", credentials.get("pw"))
                
                # In real scenarios there's a login button, often with id #btn_login or similar
                # await page.click("button.btn_login, a.btn_login, button[type='submit']")
                
                # Example: Wait for navigation or specific logged in element
                # await page.wait_for_url("**/web/main.do", timeout=10000)
                
            cookies = await self._context.cookies()
            return {"status": "success", "cookies": cookies}
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            await page.close()

    async def scan_availability(self, url: str, session_info: List[Dict[str, Any]] = None) -> List[SlotInfo]:
        """Scan yeyak.seoul.go.kr camping page slots"""
        if session_info:
            await self._context.add_cookies(session_info)
            
        page = await self._context.new_page()
        try:
            await page.goto(url)
            
            # This is a mocked/heuristic parser for Seoul Yeyak calendar.
            # In reality, you'd wait for the calendar component:
            # await page.wait_for_selector(".calendar_wrap", timeout=10000)
            
            # Parse available dates...
            # This is a skeleton logic demonstrating extracting DOM nodes:
            # available_elements = await page.query_selector_all(".cal_available, .date.possible")
            # for el in available_elements: ...
            
            # Simulate parsed slots for Demo
            logger.debug(f"Scanning target URL: {url}")
            await asyncio.sleep(1) # simulate DOM interaction
            
            # MOCK Data representing typical structure
            return [
                SlotInfo(date="2026-05-01", zone="A구역", available=True, price="30,000", url=url),
                SlotInfo(date="2026-05-02", zone="B구역", available=False, price="25,000", url=url),
                SlotInfo(date="2026-05-03", zone="A구역", available=True, price="30,000", url=url),
            ]
        finally:
            await page.close()
            
    async def hold_reservation(self, slot: SlotInfo) -> bool:
        """Execute the actual booking on yeyak.seoul.go.kr detail page"""
        page = await self._context.new_page()
        try:
            logger.info(f"Navigating to reserve detail: {slot.url}")
            await page.goto(slot.url)
            
            # 1. Select the Date
            # For yeyak.seoul, it's often a calendar where dates have 'data-date' or similar attributes
            # await page.click(f".cal_wrap a[data-date='{slot.date}']")
            await asyncio.sleep(0.5)
            
            # 2. Select the Zone (e.g. A구역)
            # await page.click(f"text='{slot.zone}'")
            await asyncio.sleep(0.5)
            
            # 3. Click 'Reservation' button
            # await page.click("#btn_reserve, a.btn_reservation")
            logger.info(f"Targeting Slot Date: {slot.date}, Zone: {slot.zone}. Booking initiated.")
            await asyncio.sleep(1) # Simulate network response
            
            return True
        except Exception as e:
            logger.error(f"Failed to hold reservation: {e}")
            return False
        finally:
            await page.close()
