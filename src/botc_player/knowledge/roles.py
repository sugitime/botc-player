"""Baseline role knowledge for Trouble Brewing and alignment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Alignment(str, Enum):
    GOOD = "good"
    EVIL = "evil"
    UNKNOWN = "unknown"


class RoleType(str, Enum):
    TOWNSFOLK = "townsfolk"
    OUTSIDER = "outsider"
    MINION = "minion"
    DEMON = "demon"
    TRAVELLER = "traveller"
    FABLED = "fabled"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Role:
    name: str
    role_type: RoleType
    alignment: Alignment
    summary: str
    night_order: Optional[str] = None
    bluff_tips: str = ""


TROUBLE_BREWING: dict[str, Role] = {
    "Washerwoman": Role(
        "Washerwoman",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "Learns that one of two players is a particular Townsfolk.",
        bluff_tips="Share both names + role; watch for Spy/Poisoner noise.",
    ),
    "Librarian": Role(
        "Librarian",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "Learns that one of two players is a particular Outsider (or zero Outsiders).",
    ),
    "Investigator": Role(
        "Investigator",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "Learns that one of two players is a particular Minion.",
    ),
    "Chef": Role(
        "Chef",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "Learns how many pairs of evil players are neighboring.",
    ),
    "Empath": Role(
        "Empath",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "Each night, learns how many of their two living neighbors are evil.",
        night_order="each night",
    ),
    "Fortune Teller": Role(
        "Fortune Teller",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "Each night, chooses two players and learns if either is the Demon (one false positive exists).",
        night_order="each night",
    ),
    "Undertaker": Role(
        "Undertaker",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "Each night*, learns the role of the player executed today.",
        night_order="each night*",
    ),
    "Monk": Role(
        "Monk",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "Each night*, protects a player from the Demon.",
        night_order="each night*",
    ),
    "Ravenkeeper": Role(
        "Ravenkeeper",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "If killed by Demon, learns one player's role.",
    ),
    "Virgin": Role(
        "Virgin",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "First time nominated by Townsfolk, nominator dies.",
    ),
    "Slayer": Role(
        "Slayer",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "Once per game, publicly attempt to shoot the Demon.",
    ),
    "Soldier": Role(
        "Soldier",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "Safe from the Demon kill.",
    ),
    "Mayor": Role(
        "Mayor",
        RoleType.TOWNSFOLK,
        Alignment.GOOD,
        "If only 3 alive and no execution, Good wins. Sometimes redirected executions.",
    ),
    "Butler": Role(
        "Butler",
        RoleType.OUTSIDER,
        Alignment.GOOD,
        "Each night, chooses a master; can only vote if master votes.",
        night_order="each night",
    ),
    "Drunk": Role(
        "Drunk",
        RoleType.OUTSIDER,
        Alignment.GOOD,
        "Thinks they are a Townsfolk but is not; info is wrong from their perspective.",
    ),
    "Recluse": Role(
        "Recluse",
        RoleType.OUTSIDER,
        Alignment.GOOD,
        "Might register as evil / as Minion or Demon to abilities.",
    ),
    "Saint": Role(
        "Saint",
        RoleType.OUTSIDER,
        Alignment.GOOD,
        "If executed, Good team loses.",
    ),
    "Poisoner": Role(
        "Poisoner",
        RoleType.MINION,
        Alignment.EVIL,
        "Each night, poisons a player (ability malfunctions).",
        night_order="each night",
        bluff_tips="Bluff info roles; explain wrong info as poison/drunk world.",
    ),
    "Spy": Role(
        "Spy",
        RoleType.MINION,
        Alignment.EVIL,
        "Each night, sees the Grimoire. Might register as good / Townsfolk/Outsider.",
        night_order="each night",
        bluff_tips="Powerful info bluff; careful not to know too much too early.",
    ),
    "Scarlet Woman": Role(
        "Scarlet Woman",
        RoleType.MINION,
        Alignment.EVIL,
        "If 5+ alive and Demon dies, becomes the Demon.",
        bluff_tips="Often mid-tier claim; protect Demon hard.",
    ),
    "Baron": Role(
        "Baron",
        RoleType.MINION,
        Alignment.EVIL,
        "Adds extra Outsiders in setup.",
        bluff_tips="Outsider-heavy setups; bluff Outsider or weak Townsfolk.",
    ),
    "Imp": Role(
        "Imp",
        RoleType.DEMON,
        Alignment.EVIL,
        "Each night*, kills a player. If Imp kills themselves, a Minion becomes Imp.",
        night_order="each night*",
        bluff_tips="Need a consistent Townsfolk bluff and kill pattern story.",
    ),
}


def get_role(name: str) -> Optional[Role]:
    if name in TROUBLE_BREWING:
        return TROUBLE_BREWING[name]
    # case-insensitive fallback
    lower = {k.lower(): v for k, v in TROUBLE_BREWING.items()}
    return lower.get(name.lower())


def alignment_for_role(name: str) -> Alignment:
    role = get_role(name)
    return role.alignment if role else Alignment.UNKNOWN


def is_evil_type(role_type: RoleType) -> bool:
    return role_type in (RoleType.MINION, RoleType.DEMON)
