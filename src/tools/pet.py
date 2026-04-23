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


def _apply_pose(species: Species, frame: List[str], motion_step: int) -> List[str]:
    """species 별 간단한 자세 변형(팔/표정)을 적용한다."""
    step = motion_step % 6
    if step in (0, 3):
        return frame

    posed = list(frame)

    if species == "fox":
        # 귀/손동작 강조
        if step in (1, 4):
            posed[1] = posed[1].replace("( ", "( /", 1).replace(" )", " \\)", 1)
        elif step in (2, 5):
            posed[3] = posed[3].replace("/", "╭", 1).replace("\\", "╮", 1)
    elif species == "turtle":
        if step in (1, 4):
            posed[1] = posed[1].replace("^ ^", "^_^", 1).replace("o o", "o_o", 1)
        elif step in (2, 5):
            posed[2] = posed[2].replace("|", "(", 1).replace("|", ")", 1)
    elif species == "owl":
        if step in (1, 4):
            posed[2] = posed[2].replace("/", "╱", 1).replace("\\", "╲", 1)
        elif step in (2, 5):
            posed[1] = posed[1].replace("(o,o)", "(^,^)", 1).replace("(o_o)", "(^_^)", 1)
    elif species == "dragon":
        if step in (1, 4):
            posed[0] = posed[0].replace("/\\___/\\", "/\\_▲_/\\", 1)
        elif step in (2, 5):
            posed[2] = posed[2].replace("===", "=v=", 1)
    elif species == "egg":
        if step in (1, 4):
            posed[2] = posed[2].replace("· ·", "^ ^", 1).replace("- -", "· ·", 1)
        elif step in (2, 5):
            posed[1] = posed[1].replace("/", "(", 1).replace("\\", ")", 1)

    return posed


@dataclass
class Pet:
    species: Species = "egg"
    nickname: str | None = None

    def frame(self, mood: Mood = "neutral", motion_step: int | None = None) -> List[str]:
        frame = FRAMES.get(self.species, FRAMES["egg"]).get(
            mood, FRAMES[self.species]["neutral"]
        )
        if motion_step is None:
            return frame
        frame = _apply_pose(self.species, frame, motion_step)
        # 위젯에서 주기적으로 호출될 때 좌우로 1칸씩 흔들어 살아있는 느낌을 준다.
        shifts = (-1, 0, 1, 0)
        shift = shifts[motion_step % len(shifts)]
        if shift == 0:
            return frame
        if shift > 0:
            return [(" " * shift) + line for line in frame]
        cut = abs(shift)
        return [line[cut:] if len(line) > cut else line for line in frame]

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
