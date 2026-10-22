"""
quest_board.py – Read-only Discord quest discovery.

Fetches the public DiscordQuest dataset, normalizes active quests, groups
regional variants of the same campaign, and exposes region-aware filtering.
No Tkinter here; the GUI renders whatever QuestBoard reports.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import config
from .errors import QuestBoardError
from .net import fetch_json

SUPPORTED_TASKS = frozenset({"PLAY_ON_DESKTOP"})
REGION_ALL = "ALL"
REGION_GLOBAL = "GLOBAL"


@dataclass(frozen=True)
class RegionAvailability:
    """Where a quest can be completed according to the public dataset."""

    is_global: bool
    regions: frozenset[str] = frozenset()
    known_regions: frozenset[str] = frozenset()
    exclude_based: bool = False

    def available_in(self, code: str) -> bool:
        """Return True when *code* is covered by this availability rule."""
        key = str(code or "").strip().upper()
        if key == REGION_ALL:
            return True
        if key == REGION_GLOBAL:
            return self.is_global
        return self.is_global or key in self.regions

    def label(self) -> str:
        """Short human-readable region summary for the list and detail panes."""
        if self.is_global:
            return REGION_GLOBAL
        if not self.regions:
            return "UNAVAILABLE"

        missing = self.known_regions - self.regions
        huge_majority = len(self.regions) >= max(4, len(self.known_regions) - 2)
        if missing and len(missing) <= 6 and (self.exclude_based or huge_majority):
            return "GLOBAL EXCEPT " + ", ".join(sorted(missing))

        if len(self.regions) <= 6:
            return ", ".join(sorted(self.regions))
        return f"{len(self.regions)} REGIONS"


@dataclass(frozen=True)
class QuestInfo:
    """One campaign after regional variants have been grouped together."""

    quest_ids: tuple[str, ...]
    name: str
    app_name: str
    app_id: str
    reward: str
    tasks: frozenset[str]
    starts_at: datetime | None
    expires_at: datetime | None
    availability: RegionAvailability
    age_gate: bool = False

    @property
    def supported(self) -> bool:
        """True when Orbifier can progress this quest with a fake process."""
        return bool(self.tasks & SUPPORTED_TASKS)

    @property
    def variant_count(self) -> int:
        return len(self.quest_ids)

    def expires_label(self) -> str:
        """Local end date/time, or NO END for evergreen/unknown entries."""
        if self.expires_at is None:
            return "NO END"
        return self.expires_at.astimezone().strftime("%Y-%m-%d %H:%M")


@dataclass(frozen=True)
class QuestBoard:
    """A snapshot of the active quests and the region codes they reference."""

    quests: tuple[QuestInfo, ...]
    regions: tuple[str, ...] = ()
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    skipped: int = 0

    def filter(self, region: str = REGION_ALL, desktop_only: bool = True) -> list[QuestInfo]:
        """Return quests matching the region and support filters."""
        key = str(region or REGION_ALL).strip().upper()
        result = [q for q in self.quests if not desktop_only or q.supported]
        if key != REGION_ALL:
            result = [q for q in result if q.availability.available_in(key)]
        return sorted(result, key=lambda q: (not q.supported, q.name.casefold(), q.app_id))


def load_quest_board(fetcher=fetch_json, now: datetime | None = None) -> QuestBoard:
    """Fetch both public datasets and build a board snapshot."""
    quests_payload = fetcher(
        config.DISCORD_QUEST_API_URL,
        timeout=config.QUEST_API_TIMEOUT,
    )
    regions_payload = fetcher(
        config.DISCORD_QUEST_REGIONS_URL,
        timeout=config.QUEST_API_TIMEOUT,
    )
    return build_quest_board(quests_payload, regions_payload, now=now)


def build_quest_board(
    quests_payload: object,
    regions_payload: object,
    now: datetime | None = None,
) -> QuestBoard:
    """Normalize the two API payloads into a grouped, active-only board."""
    if isinstance(quests_payload, Mapping):
        quests_payload = quests_payload.get("quests")
    if not isinstance(quests_payload, list):
        raise QuestBoardError("Unexpected quest data format")
    if not isinstance(regions_payload, Mapping):
        raise QuestBoardError("Unexpected region data format")

    moment = _as_utc(now)
    region_map = _region_entries(regions_payload)
    known = _known_regions(region_map)

    parsed: list[QuestInfo] = []
    skipped = 0
    for entry in quests_payload:
        quest = _parse_quest(entry, region_map, known)
        if quest is None:
            skipped += 1
            continue
        if not _is_active(quest, moment):
            continue
        parsed.append(quest)

    if not parsed:
        raise QuestBoardError("No active quests found in the quest data")

    grouped = _group_quests(parsed, known)
    grouped = tuple(sorted(grouped, key=lambda q: (not q.supported, q.name.casefold(), q.app_id)))
    return QuestBoard(grouped, tuple(sorted(known)), moment, skipped)


# ── Parsing helpers ──────────────────────────────────────────────────────────

def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _task_keys(cfg: Mapping) -> frozenset[str]:
    for section in ("task_config_v2", "task_config"):
        part = cfg.get(section)
        if not isinstance(part, Mapping):
            continue
        tasks = part.get("tasks")
        if isinstance(tasks, Mapping):
            keys = {str(key).strip().upper() for key in tasks if str(key).strip()}
            if keys:
                return frozenset(keys)
        elif isinstance(tasks, list):
            keys = set()
            for item in tasks:
                if isinstance(item, str) and item.strip():
                    keys.add(item.strip().upper())
                elif isinstance(item, Mapping) and item.get("type"):
                    keys.add(str(item["type"]).strip().upper())
            if keys:
                return frozenset(keys)
    return frozenset()


def _reward_name(cfg: Mapping) -> str:
    rewards_config = cfg.get("rewards_config")
    if not isinstance(rewards_config, Mapping):
        return ""
    rewards = rewards_config.get("rewards")
    if not isinstance(rewards, list) or not rewards:
        return ""
    first = rewards[0]
    if not isinstance(first, Mapping):
        return ""
    messages = first.get("messages")
    if isinstance(messages, Mapping):
        name = _clean(messages.get("name"))
        if name:
            return name
    return _clean(first.get("name"))


def _region_entries(payload: Mapping) -> dict[str, Mapping]:
    entries = payload.get("quests")
    if not isinstance(entries, list):
        return {}
    result: dict[str, Mapping] = {}
    for entry in entries:
        if isinstance(entry, Mapping) and entry.get("id") is not None:
            result[str(entry["id"])] = entry
    return result


def _known_regions(region_map: Mapping[str, Mapping]) -> frozenset[str]:
    codes: set[str] = set()
    for entry in region_map.values():
        regions = entry.get("regions")
        if isinstance(regions, Mapping):
            for key in ("include", "exclude"):
                values = regions.get(key)
                if isinstance(values, list):
                    codes.update(
                        str(value).strip().upper()
                        for value in values
                        if str(value).strip()
                    )
        elif isinstance(regions, list):
            codes.update(
                str(value).strip().upper()
                for value in regions
                if str(value).strip()
            )
    return frozenset(codes)


def _region_rule(
    entry: Mapping | None,
    known: frozenset[str],
) -> tuple[bool, frozenset[str], bool]:
    """Return (is_global, available regions, exclude-based rule)."""
    if not isinstance(entry, Mapping) or entry.get("is_global"):
        return True, known, False

    regions = entry.get("regions")
    include: set[str] = set()
    exclude: set[str] = set()
    if isinstance(regions, Mapping):
        include = {
            str(value).strip().upper()
            for value in (regions.get("include") or [])
            if str(value).strip()
        }
        exclude = {
            str(value).strip().upper()
            for value in (regions.get("exclude") or [])
            if str(value).strip()
        }
    elif isinstance(regions, list):
        include = {
            str(value).strip().upper()
            for value in regions
            if str(value).strip()
        }
    else:
        return True, known, False

    if not include and not exclude:
        return True, known, False

    if include:
        available = include - exclude
        exclude_based = False
    else:
        available = set(known) - exclude
        exclude_based = True

    if known:
        available &= set(known)
    return False, frozenset(available), exclude_based


def _parse_quest(
    entry: object,
    region_map: Mapping[str, Mapping],
    known: frozenset[str],
) -> QuestInfo | None:
    if not isinstance(entry, Mapping):
        return None
    quest_id = _clean(entry.get("id"))
    cfg = entry.get("config")
    if not quest_id or not isinstance(cfg, Mapping):
        return None

    application = cfg.get("application")
    if not isinstance(application, Mapping):
        return None
    app_id = _clean(application.get("id"))
    if not app_id:
        return None

    messages = cfg.get("messages")
    if not isinstance(messages, Mapping):
        messages = {}
    name = _clean(messages.get("quest_name")) or _clean(messages.get("name"))
    if not name:
        return None

    app_name = _clean(application.get("name")) or "Unknown game"
    is_global, available, exclude_based = _region_rule(region_map.get(quest_id), known)
    rule = region_map.get(quest_id)
    age_gate = bool(rule.get("show_age_gate")) if isinstance(rule, Mapping) else False

    return QuestInfo(
        quest_ids=(quest_id,),
        name=name,
        app_name=app_name,
        app_id=app_id,
        reward=_reward_name(cfg),
        tasks=_task_keys(cfg),
        starts_at=_parse_dt(cfg.get("starts_at")),
        expires_at=_parse_dt(cfg.get("expires_at")),
        availability=RegionAvailability(is_global, available, known, exclude_based),
        age_gate=age_gate,
    )


def _is_active(quest: QuestInfo, now: datetime) -> bool:
    if quest.starts_at is not None and quest.starts_at > now:
        return False
    if quest.expires_at is not None and quest.expires_at <= now:
        return False
    return True


def _group_key(quest: QuestInfo) -> tuple:
    return (
        quest.name.casefold(),
        quest.app_id,
        quest.reward.casefold(),
        quest.expires_at,
        quest.tasks,
    )


def _group_quests(quests: list[QuestInfo], known: frozenset[str]) -> tuple[QuestInfo, ...]:
    groups: dict[tuple, list[QuestInfo]] = {}
    for quest in quests:
        groups.setdefault(_group_key(quest), []).append(quest)

    grouped: list[QuestInfo] = []
    for items in groups.values():
        global_flag = any(item.availability.is_global for item in items)
        available: set[str] = set(known) if global_flag else set()
        if not global_flag:
            for item in items:
                available.update(item.availability.regions)
            if known and available >= set(known):
                global_flag = True
                available = set(known)

        starts = [item.starts_at for item in items if item.starts_at is not None]
        grouped.append(QuestInfo(
            quest_ids=tuple(sorted({qid for item in items for qid in item.quest_ids})),
            name=items[0].name,
            app_name=items[0].app_name,
            app_id=items[0].app_id,
            reward=items[0].reward,
            tasks=frozenset().union(*(item.tasks for item in items)),
            starts_at=min(starts) if starts else None,
            expires_at=items[0].expires_at,
            availability=RegionAvailability(
                is_global=global_flag,
                regions=frozenset(available),
                known_regions=known,
                exclude_based=all(item.availability.exclude_based for item in items),
            ),
            age_gate=any(item.age_gate for item in items),
        ))
    return tuple(grouped)
