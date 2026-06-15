"""Clean-parameter select entities for Narwal vacuum.

These hold pending values applied at the next room clean (CleanParam is only sent in the
start payload). water additionally writes live via clean/set_mop_humidity while cleaning.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import NarwalConfigEntry
from .const import WORK_MODE_MAP, MOP_STRENGTH_MAP, WATER_MAP
from .coordinator import NarwalCoordinator
from .entity import NarwalEntity


@dataclass(frozen=True, kw_only=True)
class NarwalSelectEntityDescription(SelectEntityDescription):
    """Describes a Narwal clean-param select."""

    attr: str  # CleanSettings field this select reads/writes
    mapping: dict[str, int]  # option label -> robot enum value
    live_setter: str | None = None  # NarwalClient coroutine applied live while cleaning


SELECT_DESCRIPTIONS: tuple[NarwalSelectEntityDescription, ...] = (
    NarwalSelectEntityDescription(
        key="work_mode",
        translation_key="work_mode",
        entity_category=EntityCategory.CONFIG,
        attr="work_mode",
        mapping=WORK_MODE_MAP,
        options=list(WORK_MODE_MAP),
    ),
    NarwalSelectEntityDescription(
        key="water",
        translation_key="water",
        entity_category=EntityCategory.CONFIG,
        attr="water",
        mapping=WATER_MAP,
        live_setter="set_mop_humidity",
        options=list(WATER_MAP),
    ),
    NarwalSelectEntityDescription(
        key="mop_strength",
        translation_key="mop_strength",
        entity_category=EntityCategory.CONFIG,
        attr="mop_strength",
        mapping=MOP_STRENGTH_MAP,
        options=list(MOP_STRENGTH_MAP),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Narwal clean-param select entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        NarwalSelect(coordinator, description) for description in SELECT_DESCRIPTIONS
    )


class NarwalSelect(NarwalEntity, RestoreEntity, SelectEntity):
    """A clean-parameter select backed by coordinator.clean_settings; restored across restarts."""

    entity_description: NarwalSelectEntityDescription

    def __init__(
        self,
        coordinator: NarwalCoordinator,
        description: NarwalSelectEntityDescription,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self.entity_description = description
        device_id = coordinator.config_entry.data["device_id"]
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._labels = {int(v): k for k, v in description.mapping.items()}

    async def async_added_to_hass(self) -> None:
        """Restore the last selection into clean_settings (persists across restarts)."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self.entity_description.mapping:
            setattr(
                self.coordinator.clean_settings,
                self.entity_description.attr,
                self.entity_description.mapping[last.state],
            )

    @property
    def available(self) -> bool:
        """Editable even while the robot sleeps — these are pending settings."""
        return True

    @property
    def current_option(self) -> str | None:
        """Return the stored option label."""
        value = getattr(self.coordinator.clean_settings, self.entity_description.attr)
        return self._labels.get(int(value))

    async def async_select_option(self, option: str) -> None:
        """Store the selection and, for live controls, apply it if cleaning."""
        value = self.entity_description.mapping[option]
        setattr(self.coordinator.clean_settings, self.entity_description.attr, value)
        self.async_write_ha_state()
        state = self.coordinator.data
        if self.entity_description.live_setter and state is not None and state.is_cleaning:
            await getattr(self.coordinator.client, self.entity_description.live_setter)(value)
