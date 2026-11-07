"""Regression tests with a minimal HA API double. Run unittest discover -s tests.

These verify imports and sensor lifecycle wiring, not a running HA Recorder.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "salad_chopping"


class SensorEntity:
    @property
    def name(self):
        return self._attr_name


class CoordinatorEntity:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self.removers = []

    async def async_added_to_hass(self):
        pass

    def async_on_remove(self, callback):
        self.removers.append(callback)

    def _handle_coordinator_update(self):
        pass


def module(name, **attrs):
    result = ModuleType(name)
    result.__dict__.update(attrs)
    return result


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


class StatisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.imported = Mock()
        cls.external = Mock()
        modules = {
            "salad_test": module("salad_test", __path__=[str(ROOT)], SaladConfigEntry=object, SaladCoordinator=object),
            "homeassistant": module("homeassistant"),
            "homeassistant.components": module("homeassistant.components"),
            "homeassistant.components.recorder": module("homeassistant.components.recorder"),
            "homeassistant.components.recorder.models": module("models", StatisticData=dict, StatisticMeanType=SimpleNamespace(ARITHMETIC=1)),
            "homeassistant.components.recorder.statistics": module("statistics", async_import_statistics=cls.imported, async_add_external_statistics=cls.external),
            "homeassistant.components.sensor": module("sensor", SensorDeviceClass=SimpleNamespace(MONETARY="monetary"), SensorStateClass=SimpleNamespace(TOTAL="total", MEASUREMENT="measurement"), SensorEntity=SensorEntity),
            "homeassistant.const": module("const", EVENT_RECORDER_HOURLY_STATISTICS_GENERATED="hourly_statistics"),
            "homeassistant.core": module("core", HomeAssistant=object, callback=lambda fn: fn),
            "homeassistant.helpers": module("helpers", entity_registry=Mock()),
            "homeassistant.helpers.device_registry": module("device_registry", DeviceEntryType=SimpleNamespace(SERVICE="service"), DeviceInfo=dict),
            "homeassistant.helpers.entity_platform": module("entity_platform", AddEntitiesCallback=object),
            "homeassistant.helpers.update_coordinator": module("update_coordinator", CoordinatorEntity=CoordinatorEntity),
        }
        cls.patcher = patch.dict(sys.modules, modules)
        cls.patcher.start()
        cls.stats = load("salad_test.statistics", "statistics.py")
        cls.sensor = load("salad_test.sensor", "sensor.py")

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def setUp(self):
        self.imported.reset_mock()
        self.external.reset_mock()
        self.start = datetime(2026, 11, 1, tzinfo=UTC)
        self.hass = SimpleNamespace(bus=SimpleNamespace(async_listen=Mock(return_value=Mock())))

    def buckets(self, count, step):
        return {self.start + i * step: Decimal(i + 1) for i in range(count)}

    def publish(self, buckets, period="hour", previous=None):
        self.stats.publish_entity_statistics(self.hass, "sensor.renamed_earnings_2", "Salad earnings", period, buckets, previous)

    def test_hourly_import_uses_actual_entity_id_and_skips_partial_hour(self):
        self.publish(self.buckets(24, timedelta(hours=1)))
        _, metadata, points = self.imported.call_args.args
        self.assertEqual(metadata["statistic_id"], "sensor.renamed_earnings_2")
        self.assertEqual(metadata["source"], "recorder")
        self.assertEqual(metadata["unit_of_measurement"], "USD")
        self.assertFalse(metadata["has_sum"])
        self.assertEqual(len(points), 23)
        self.assertEqual(points[-1], {"start": self.start + timedelta(hours=22), "mean": 23.0, "min": 23.0, "max": 23.0})

    def test_daily_totals_survive_hourly_storage_and_daily_aggregation(self):
        self.publish(self.buckets(30, timedelta(days=1)), "day")
        points = self.imported.call_args.args[2]
        self.assertEqual(len(points), 29 * 24)
        for day in range(29):
            rows = points[day * 24:(day + 1) * 24]
            self.assertEqual(sum(p["mean"] for p in rows) / 24, day + 1)
            self.assertEqual(min(p["min"] for p in rows), day + 1)
            self.assertEqual(max(p["max"] for p in rows), day + 1)
        self.assertLess(points[-1]["start"], self.start + timedelta(days=29))

    def test_unchanged_buckets_not_reimported_and_corrections_are(self):
        buckets = self.buckets(24, timedelta(hours=1))
        self.publish(buckets, previous=buckets)
        self.imported.assert_not_called()
        changed = dict(buckets)
        changed[self.start] = Decimal("0.1234")
        self.publish(changed, previous=buckets)
        self.assertEqual(len(self.imported.call_args.args[2]), 1)
        self.assertEqual(self.imported.call_args.args[2][0]["mean"], 0.1234)

    def test_unchanged_partial_bucket_imported_when_it_completes(self):
        previous = self.buckets(24, timedelta(hours=1))
        current = dict(previous)
        del current[self.start]
        current[self.start + timedelta(hours=24)] = Decimal(25)
        self.publish(current, previous=previous)
        self.assertEqual(self.imported.call_args.args[2][0]["start"], self.start + timedelta(hours=23))
        self.assertEqual(len(self.imported.call_args.args[2]), 1)

    def test_sensor_lifecycle_backfills_and_restores_recorder_overwrites(self):
        buckets = self.buckets(30, timedelta(days=1))
        coordinator = SimpleNamespace(hass=self.hass, data=SimpleNamespace(history={"earnings_30d": buckets}))
        sensor = self.sensor.SaladCompletedPeriodSensor(coordinator, "account", "day", "earnings_30d")
        sensor.entity_id = "sensor.my_daily_earnings"
        asyncio.run(sensor.async_added_to_hass())
        self.assertEqual(sensor.name, "Salad earnings daily")
        self.assertEqual(sensor._attr_unique_id, "account_earnings_last_completed_day")
        self.assertEqual(sensor._attr_state_class, "measurement")
        self.assertIsNone(sensor._attr_device_class)
        self.assertEqual(sensor.native_value, Decimal(29))
        self.assertEqual(self.imported.call_args.args[1]["statistic_id"], sensor.entity_id)
        self.assertEqual(len(sensor.removers), 1)
        self.imported.reset_mock()
        sensor._handle_coordinator_update()
        self.imported.assert_not_called()
        event_callback = self.hass.bus.async_listen.call_args.args[1]
        event_callback(None)
        self.assertEqual(len(self.imported.call_args.args[2]), 29 * 24)
        sensor.entity_id = "sensor.user_renamed_daily"
        sensor._handle_coordinator_update()
        self.assertEqual(self.imported.call_args.args[1]["statistic_id"], sensor.entity_id)
        coordinator.data.history = None
        self.imported.reset_mock()
        event_callback(None)
        self.imported.assert_not_called()
        self.assertIsNone(sensor.native_value)

    def test_external_statistics_still_published_for_existing_dashboards(self):
        history = {"earnings_24h": self.buckets(24, timedelta(hours=1)), "earnings_30d": self.buckets(30, timedelta(days=1))}
        self.stats.publish_statistics(self.hass, "ACCOUNT", history, None)
        self.assertEqual(self.external.call_count, 2)
        self.assertEqual(self.external.call_args_list[0].args[1]["statistic_id"], "salad_chopping:earnings_hourly_account")
        self.assertEqual(self.external.call_args_list[1].args[1]["statistic_id"], "salad_chopping:earnings_daily_account")


if __name__ == "__main__":
    unittest.main()
