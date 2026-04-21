"""텍스트 아트 펫.

사용자 직군 + 개발 성향 + 현재 무드 기반 ASCII / 이모지 혼합 프레임 제공.
`Pet.frame(mood="focused")` 같은 식으로 렌더링.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal

Species = Literal["fox", "turtle", "owl", "dragon", "egg"]
Mood = Literal["happy", "neutral", "tired", "stressed", "focused"]


FRAMES: Dict[Species, Dict[Mood, List[str]]] = {
    "egg": {
        "neutral": [
            "   ___   ",
            "  /   \\  ",
            " | · · | ",
            "  \\___/  ",
        ],
        "happy": [
            "   ___   ",
            "  /   \\  ",
            " | ^ ^ | ",
            "  \\_-_/  ",
        ],
        "tired": [
            "   ___   ",
            "  /   \\  ",
            " | - - | ",
            "  \\___/  ",
        ],
        "stressed": [
            "   ___   ",
            "  /!!!\\  ",
            " | x x | ",
            "  \\___/  ",
        ],
        "focused": [
            "   ___   ",
            "  /   \\  ",
            " | o o | ",
            "  \\___/  ",
        ],
    },
    "fox": {
        "neutral": [
            "   /\\___/\\ ",
            "  ( 🦊  ) ",
            "   > ᴥ <  ",
            "  /     \\ ",
        ],
        "happy": [
            "   /\\___/\\ ",
            "  ( ^ᴥ^ ) ",
            "   >   <  ",
            "  / *^* \\ ",
        ],
        "tired": [
            "   /\\___/\\ ",
            "  ( -ᴥ- ) ",
            "   >zzz<  ",
            "  /     \\ ",
        ],
        "stressed": [
            "   /\\___/\\ ",
            "  ( >ᴥ< )!",
            "   > !! <  ",
            "  / /|\\ \\ ",
        ],
        "focused": [
            "   /\\___/\\ ",
            "  ( •ᴥ• ) ",
            "   > =_= < ",
            "  / === \\ ",
        ],
    },
    "turtle": {
        "neutral": [
            "     _____    ",
            "   /       \\  ",
            "  |  🐢 ᴥ ᴥ |  ",
            "   \\_______/  ",
        ],
        "happy": [
            "     _____    ",
            "   /  ^ ^  \\  ",
            "  |   ᴥᴥᴥ   | ",
            "   \\_______/  ",
        ],
        "tired": [
            "     _____    ",
            "   /  - -  \\  ",
            "  |   zzz   | ",
            "   \\_______/  ",
        ],
        "stressed": [
            "     _____    ",
            "   /  x x  \\  ",
            "  |   !!!   | ",
            "   \\_______/  ",
        ],
        "focused": [
            "     _____    ",
            "   /  o o  \\  ",
            "  |   ==    | ",
            "   \\_______/  ",
        ],
    },
    "owl": {
        "neutral": [
            "   ,___,   ",
            "   (o,o)   ",
            "   /)_)\\   ",
            "  -\"-\"-\"-  ",
        ],
        "happy": [
            "   ,___,   ",
            "   (^,^)   ",
            "   /)_)\\   ",
            "  -\" * \"-  ",
        ],
        "tired": [
            "   ,___,   ",
            "   (-,-)   ",
            "   /)_)\\   ",
            "  -zzz-zz  ",
        ],
        "stressed": [
            "   ,___,   ",
            "   (@,@)!  ",
            "   /)_)\\   ",
            "  -!-!-!- ",
        ],
        "focused": [
            "   ,___,   ",
            "   (o_o)   ",
            "   /)=)\\   ",
            "  -\"===\"-  ",
        ],
    },
    "dragon": {
        "neutral": [
            "      /\\___/\\         ",
            "     ( o   o )        ",
            "    /  =ω=    \\__    ",
            "   /_/\\_/\\_/\\_//  \\__",
        ],
        "happy": [
            "      /\\___/\\         ",
            "     ( ^   ^ )        ",
            "    /  =ω=    \\__    ",
            "  (💎)/\\_/\\_//  \\__  ",
        ],
        "tired": [
            "      /\\___/\\         ",
            "     ( -   - )        ",
            "    /  zzz    \\__    ",
            "   /_/\\_/\\_/\\_//  \\__",
        ],
        "stressed": [
            "      /\\___/\\ 🔥     ",
            "     ( >   < )!       ",
            "    /  !!!    \\__    ",
            "   /_/\\_/\\_/\\_//  \\__",
        ],
        "focused": [
            "      /\\___/\\         ",
            "     ( ◎   ◎ )        ",
            "    /  ===    \\__    ",
            "   /_/\\_/\\_/\\_//  \\__",
        ],
    },
}


DEFAULT_TALK = {
    "neutral": "오늘은 평범한 하루! 같이 해봐요.",
    "happy": "기분 최고! 이대로 쭉 가봅시다 🎉",
    "tired": "잠깐 눈 좀 붙여요… 스트레칭도 해요.",
    "stressed": "탭이 너무 많아요! 정리 어때요? 💬",
    "focused": "집중 모드 진입! 방해 금지 🔕",
}


@dataclass
class Pet:
    species: Species = "egg"
    nickname: str | None = None

    def frame(self, mood: Mood = "neutral") -> List[str]:
        return FRAMES.get(self.species, FRAMES["egg"]).get(
            mood, FRAMES[self.species]["neutral"]
        )

    def say(self, mood: Mood = "neutral", message: str | None = None) -> str:
        text = message or DEFAULT_TALK.get(mood, "")
        name = self.nickname or self.species
        return f"[{name}] 💬 {text}"


def pick_species_for(job_role: str | None, dev_tendency: str | None) -> Species:
    role = (job_role or "").lower()
    tend = (dev_tendency or "").lower()
    if role in {"frontend", "pm", "planner"} and tend in {"active", "explorer", ""}:
        return "fox"
    if role in {"backend", "data"} and tend in {"calm", "pragmatic", ""}:
        return "turtle"
    if role in {"backend", "data", "infra"} and tend in {"owl", "thoughtful", "calm"}:
        return "owl"
    if role in {"ai", "ml", "infra"} and tend in {"explorer", "researcher", ""}:
        return "dragon"
    return "fox"
