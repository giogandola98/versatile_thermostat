# pylint: disable=wildcard-import, unused-wildcard-import, protected-access, unused-argument, line-too-long, unused-variable

""" Reproduction of issue #2135: a heat order received while auto-stopped turns the underlying on """
from datetime import datetime, timedelta
import logging

from custom_components.versatile_thermostat.thermostat_climate import ThermostatOverClimate

from .commons import *  # pylint: disable=wildcard-import, unused-wildcard-import

logging.getLogger().setLevel(logging.DEBUG)


async def _create_auto_stopped_vtherm(hass: HomeAssistant, hvac_mode) -> tuple[ThermostatOverClimate, datetime]:
    """Create an over_climate AC VTherm with auto-start/stop and bring it to the auto-stopped state"""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="TheOverClimateMockName",
        unique_id="overClimateUniqueId",
        data={
            CONF_NAME: "overClimate",
            CONF_TEMP_SENSOR: "sensor.mock_temp_sensor",
            CONF_THERMOSTAT_TYPE: CONF_THERMOSTAT_CLIMATE,
            CONF_EXTERNAL_TEMP_SENSOR: "sensor.mock_ext_temp_sensor",
            CONF_CYCLE_MIN: 5,
            CONF_TEMP_MIN: 15,
            CONF_TEMP_MAX: 30,
            CONF_USE_WINDOW_FEATURE: False,
            CONF_USE_MOTION_FEATURE: False,
            CONF_USE_POWER_FEATURE: False,
            CONF_USE_PRESENCE_FEATURE: False,
            CONF_USE_AUTO_START_STOP_FEATURE: True,
            CONF_UNDERLYING_LIST: ["climate.mock_climate"],
            CONF_MINIMAL_ACTIVATION_DELAY: 30,
            CONF_MINIMAL_DEACTIVATION_DELAY: 0,
            CONF_SAFETY_DELAY_MIN: 5,
            CONF_SAFETY_MIN_ON_PERCENT: 0.3,
            CONF_AC_MODE: True,
            CONF_AUTO_START_STOP_LEVEL: AUTO_START_STOP_LEVEL_FAST,
        },
    )

    await create_and_register_mock_climate(hass, "mock_climate", "mock_climate", {}, hvac_modes=[VThermHvacMode_OFF, VThermHvacMode_COOL, VThermHvacMode_HEAT])
    vtherm: ThermostatOverClimate = await create_thermostat(hass, config_entry, "climate.overclimate")
    assert vtherm is not None

    tz = get_tz(hass)  # pylint: disable=invalid-name
    now: datetime = datetime.now(tz=tz)
    vtherm._set_now(now)

    await send_temperature_change_event(vtherm, 20, now, True)
    await vtherm.async_set_hvac_mode(hvac_mode)
    await vtherm.async_set_temperature(temperature=20)
    await hass.async_block_till_done()
    assert vtherm.hvac_mode == hvac_mode
    assert hass.states.get("climate.mock_climate").state == hvac_mode

    # the room goes away from the demand until auto-start/stop stops the VTherm
    room = 20.0
    for _ in range(10):
        now = now + timedelta(minutes=5)
        room = room + 1.5 if hvac_mode == VThermHvacMode_HEAT else room - 1.5
        vtherm._set_now(now)
        await send_temperature_change_event(vtherm, room, now, True)
        await hass.async_block_till_done()
        if vtherm.hvac_mode == VThermHvacMode_OFF:
            break

    assert vtherm.hvac_mode == VThermHvacMode_OFF
    assert vtherm.auto_start_stop_manager.is_auto_stop_detected
    assert hass.states.get("climate.mock_climate").state == VThermHvacMode_OFF
    return vtherm, now


async def test_issue_2135_heat_order_while_auto_stopped_in_heat(hass: HomeAssistant, skip_hass_states_is_state):
    """Auto-stopped in heat, a scheduler sends set_temperature(hvac_mode=heat): the underlying must stay off"""
    vtherm, now = await _create_auto_stopped_vtherm(hass, VThermHvacMode_HEAT)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.overclimate", "hvac_mode": "heat", "temperature": 20},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert vtherm.auto_start_stop_manager.is_auto_stop_detected
    assert vtherm.hvac_mode == VThermHvacMode_OFF
    assert hass.states.get("climate.mock_climate").state == VThermHvacMode_OFF

    vtherm.remove_thermostat()


async def test_issue_2135_heat_order_while_auto_stopped_in_cool(hass: HomeAssistant, skip_hass_states_is_state):
    """Auto-stopped in cool, a scheduler sends set_temperature(hvac_mode=heat) with a room above the target: the underlying must stay off"""
    vtherm, now = await _create_auto_stopped_vtherm(hass, VThermHvacMode_COOL)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.overclimate", "hvac_mode": "heat", "temperature": 15},
        blocking=True,
    )
    await hass.async_block_till_done()

    # whatever auto-start/stop decides, the VTherm and the underlying must agree
    assert hass.states.get("climate.mock_climate").state == vtherm.hvac_mode

    vtherm.remove_thermostat()


async def test_issue_2135_heat_order_while_auto_stopped_set_hvac_mode_only(hass: HomeAssistant, skip_hass_states_is_state):
    """Auto-stopped in heat, set_hvac_mode(heat) alone: the underlying must stay off"""
    vtherm, now = await _create_auto_stopped_vtherm(hass, VThermHvacMode_HEAT)

    await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": "climate.overclimate", "hvac_mode": "heat"}, blocking=True)
    await hass.async_block_till_done()

    assert vtherm.hvac_mode == VThermHvacMode_OFF
    assert hass.states.get("climate.mock_climate").state == VThermHvacMode_OFF

    vtherm.remove_thermostat()
