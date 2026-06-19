"""Comprehensive unit tests for dol-cloud-client and elasticmail modules."""

import importlib
import importlib.util
import json
import os
import sys
import tempfile
import datetime
from unittest.mock import patch, MagicMock, mock_open, call

import pandas as pd
import pytest
import sqlalchemy


# ---------------------------------------------------------------------------
# Import helpers – dol-cloud-client.py has a hyphenated filename
# ---------------------------------------------------------------------------

def _import_dol_module():
    spec = importlib.util.spec_from_file_location(
        "dol_cloud_client",
        os.path.join(os.path.dirname(__file__), "dol-cloud-client.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    # We need to stub heavy imports that run at module level
    sys.modules["dol_cloud_client"] = mod
    spec.loader.exec_module(mod)
    return mod


dol_mod = _import_dol_module()
DeviceManagement = dol_mod.DeviceManagement
Database = dol_mod.Database
GenerateDiagram = dol_mod.GenerateDiagram
Table = dol_mod.Table
main = dol_mod.main

from elasticmail import ElasticMailClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_login_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"accessToken":"tok123","expiresIn":"3600"}'
    resp.json.return_value = {"accessToken": "tok123", "expiresIn": "3600"}
    return resp


def _make_dm(monkeypatch=None, config=None):
    """Create a DeviceManagement with mocked login."""
    cfg = config or {"user": "u@test.com", "pwd": "secret", "url": "https://api.test/"}
    with patch("requests.post", return_value=_mock_login_response()), \
         patch("os.path.exists", return_value=False):
        dm = DeviceManagement(cfg)
    return dm


def _sqlite_url(tmp_path):
    db_path = str(tmp_path / "test.db")
    return "sqlite:///" + db_path.replace("\\", "/")


# ===========================================================================
# 1. Table Enum
# ===========================================================================

class TestTableEnum:
    def test_enum_values(self):
        assert Table.DATA.value == "sensorData"
        assert Table.STATUS.value == "sensorStatus"
        assert Table.INACTIVE.value == "inactiveSensor"


# ===========================================================================
# 2. DeviceManagement — Auth & Init
# ===========================================================================

class TestDeviceManagementAuth:
    def test_login_when_no_cache(self):
        cfg = {"user": "u@test.com", "pwd": "pw", "url": "https://api/"}
        with patch("os.path.exists", return_value=False), \
             patch("requests.post", return_value=_mock_login_response()) as mock_post:
            dm = DeviceManagement(cfg)
        mock_post.assert_called_once()
        assert dm.token == "tok123"

    def test_load_valid_cached_token_skips_login(self):
        future_ts = int(datetime.datetime.now().timestamp()) + 9999
        cache = {"token": "cached_tok", "expireTime": future_ts}
        cfg = {"user": "u@test.com", "pwd": "pw", "url": "https://api/"}
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(cache))), \
             patch("requests.post") as mock_post:
            dm = DeviceManagement(cfg)
        mock_post.assert_not_called()
        assert dm.token == "cached_tok"

    def test_expired_cache_triggers_login(self):
        past_ts = int(datetime.datetime.now().timestamp()) - 100
        cache = {"token": "old", "expireTime": past_ts}
        cfg = {"user": "u@test.com", "pwd": "pw", "url": "https://api/"}
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(cache))), \
             patch("requests.post", return_value=_mock_login_response()) as mock_post:
            dm = DeviceManagement(cfg)
        mock_post.assert_called_once()
        assert dm.token == "tok123"

    def test_corrupt_cache_triggers_login(self):
        cfg = {"user": "u@test.com", "pwd": "pw", "url": "https://api/"}
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="NOT JSON")), \
             patch("requests.post", return_value=_mock_login_response()) as mock_post:
            dm = DeviceManagement(cfg)
        mock_post.assert_called_once()

    def test_token_saved_to_cache_after_login(self):
        cfg = {"user": "u@test.com", "pwd": "pw", "url": "https://api/"}
        m = mock_open()
        with patch("os.path.exists", return_value=False), \
             patch("requests.post", return_value=_mock_login_response()), \
             patch("builtins.open", m):
            dm = DeviceManagement(cfg)
        # _saveTokenToCache opens file for writing
        write_calls = [c for c in m.call_args_list if "'w'" in str(c) or "w" in str(c)]
        assert len(write_calls) >= 1

    def test_check_response_success_json(self):
        dm = _make_dm()
        resp = MagicMock(status_code=200, text='{"key":"val"}')
        resp.json.return_value = {"key": "val"}
        result = dm._checkResponse(resp)
        assert result["success"] is True
        assert result["data"] == {"key": "val"}

    def test_check_response_success_empty(self):
        dm = _make_dm()
        resp = MagicMock(status_code=204, text="  ")
        result = dm._checkResponse(resp)
        assert result["success"] is True
        assert result["data"] is None

    def test_check_response_failure(self):
        dm = _make_dm()
        resp = MagicMock(status_code=401, text="Unauthorized")
        result = dm._checkResponse(resp)
        assert result["success"] is False
        assert result["status_code"] == 401


# ===========================================================================
# 3. DeviceManagement — API Methods
# ===========================================================================

class TestDeviceManagementAPI:
    def _ok_response(self, data=None):
        resp = MagicMock(status_code=200, text=json.dumps(data or {}))
        resp.json.return_value = data or {}
        return resp

    def test_claim(self):
        dm = _make_dm()
        with patch("requests.post", return_value=self._ok_response()) as mp:
            dm.Claim("MAC1", "KEY1", "GW", "owner", "name")
        assert "devices/claim" in mp.call_args[0][0]

    def test_unclaim(self):
        dm = _make_dm()
        with patch("requests.delete", return_value=self._ok_response()) as md:
            dm.Unclaim("MAC1")
        assert "devices/claim/MAC1" in md.call_args[0][0]

    def test_add_lora_sensor_default_sample_rate(self):
        dm = _make_dm()
        with patch("requests.post", return_value=self._ok_response()) as mp:
            dm.AddLoraSensor("MAC1", "Sensor1", "DEVEUI", "TYPE")
        body = mp.call_args[1]["json"]
        assert body["sampleRate"] == 60

    def test_add_lora_sensor_custom_sample_rate(self):
        dm = _make_dm()
        with patch("requests.post", return_value=self._ok_response()) as mp:
            dm.AddLoraSensor("MAC1", "S", "EUI", "T", sample_rate=120)
        assert mp.call_args[1]["json"]["sampleRate"] == 120

    def test_remove_lora_sensor(self):
        dm = _make_dm()
        with patch("requests.delete", return_value=self._ok_response()) as md:
            dm.RemoveLoraSensor("MAC1", "EUI1")
        assert "MAC1/sensor/EUI1" in md.call_args[0][0]

    def test_update_lora_sensor(self):
        dm = _make_dm()
        with patch("requests.put", return_value=self._ok_response()) as mp:
            dm.UpdateLoraSensor("MAC1", "EUI1", 30)
        body = mp.call_args[1]["json"]
        assert body["devEui"] == "EUI1"
        assert body["sampleRate"] == 30

    def test_add_wired_sensor(self):
        dm = _make_dm()
        sensors = [{"port": 1, "wiredSensorType": "DOL139"}]
        with patch("requests.put", return_value=self._ok_response()) as mp:
            dm.AddWiredSensor("MAC1", sensors)
        assert mp.call_args[1]["json"]["sensors"] == sensors

    def test_list_devices(self):
        dm = _make_dm()
        resp_data = {"devices": [{"mac": "AA"}, {"mac": "BB"}]}
        resp = MagicMock(status_code=200, text=json.dumps(resp_data))
        resp.json.return_value = resp_data
        with patch("requests.get", return_value=resp):
            dm.ListDevices()
        assert dm.devices == resp_data

    def test_get_device(self):
        dm = _make_dm()
        device = {
            "mac": "MAC1", "key": "K", "deviceType": "GW", "owner": "O",
            "deviceName": "N", "createdAt": "2024-01-01", "updatedAt": "2024-01-02",
            "connectionState": "Connected", "firmwareVersion": "1.0",
            "isOnline": True, "lastActivityUtc": "2024-01-01T00:00:00",
            "cloudToDeviceMessages": 0, "sensors": [], "wiredSensors": [],
        }
        resp = MagicMock(status_code=200, text=json.dumps(device))
        resp.json.return_value = device
        with patch("requests.get", return_value=resp):
            dm.GetDevice("MAC1")
        # No assertion on return – just verifies no crash


# ===========================================================================
# 4. DeviceManagement — Queue
# ===========================================================================

class TestDeviceManagementQueue:
    def _queue_meta(self):
        return {
            "dataQueueConnection": "Endpoint=sb://...",
            "dataQueueName": "data-q",
            "dataQueueMessageCount": "5",
            "dataQueueDeadLetterCount": "1",
            "statusQueueConnection": "Endpoint=sb://...",
            "statusQueueName": "status-q",
            "statusQueueMessageCount": "3",
            "statusQueueDeadLetterCount": "0",
        }

    def test_get_queue_metadata_data(self):
        dm = _make_dm()
        resp = MagicMock(status_code=200, text=json.dumps(self._queue_meta()))
        resp.json.return_value = self._queue_meta()
        with patch("requests.get", return_value=resp):
            dm.GetQueueMetaData(Table.DATA.value)
        assert dm.queueName == "data-q"
        assert dm.queueSize == 5

    def test_get_queue_metadata_status(self):
        dm = _make_dm()
        resp = MagicMock(status_code=200, text=json.dumps(self._queue_meta()))
        resp.json.return_value = self._queue_meta()
        with patch("requests.get", return_value=resp):
            dm.GetQueueMetaData(Table.STATUS.value)
        assert dm.queueName == "status-q"
        assert dm.queueSize == 3

    def test_empty_queue_with_device_filter(self):
        dm = _make_dm()
        # Setup queue metadata
        dm.queueConn = "conn"
        dm.queueName = "q"
        dm.queueSize = 1
        dm.queueDeadletterSize = 0

        msg = MagicMock()
        msg.__str__ = lambda s: json.dumps({"deviceId": "DEV1", "value": 42})

        mock_receiver = MagicMock()
        mock_receiver.__enter__ = MagicMock(return_value=mock_receiver)
        mock_receiver.__exit__ = MagicMock(return_value=False)
        mock_receiver.__iter__ = MagicMock(return_value=iter([msg]))

        mock_sbc_instance = MagicMock()
        mock_sbc_instance.__enter__ = MagicMock(return_value=mock_sbc_instance)
        mock_sbc_instance.__exit__ = MagicMock(return_value=False)
        mock_sbc_instance.get_queue_receiver.return_value = mock_receiver

        mock_db = MagicMock()

        with patch.object(DeviceManagement, 'ServiceBusClient') as mock_sbc, \
             patch.object(dol_mod, 'alive_bar') as mock_bar, \
             patch.object(dm, 'GetQueueMetaData'):
            mock_sbc.from_connection_string.return_value = mock_sbc_instance
            bar_instance = MagicMock()
            mock_bar.return_value.__enter__ = MagicMock(return_value=bar_instance)
            mock_bar.return_value.__exit__ = MagicMock(return_value=False)

            dm.EmptyQueue("sensorData", "DEV1", None, mock_db, False, False)

        mock_db.Insert.assert_called_once()
        mock_receiver.complete_message.assert_called_once_with(msg)

    def test_empty_queue_readonly(self):
        dm = _make_dm()
        dm.queueConn = "conn"
        dm.queueName = "q"
        dm.queueSize = 1
        dm.queueDeadletterSize = 0

        msg = MagicMock()
        msg.__str__ = lambda s: json.dumps({"deviceId": "DEV1", "value": 42})

        mock_receiver = MagicMock()
        mock_receiver.__enter__ = MagicMock(return_value=mock_receiver)
        mock_receiver.__exit__ = MagicMock(return_value=False)
        mock_receiver.__iter__ = MagicMock(return_value=iter([msg]))

        mock_sbc_instance = MagicMock()
        mock_sbc_instance.__enter__ = MagicMock(return_value=mock_sbc_instance)
        mock_sbc_instance.__exit__ = MagicMock(return_value=False)
        mock_sbc_instance.get_queue_receiver.return_value = mock_receiver

        mock_db = MagicMock()

        with patch.object(DeviceManagement, 'ServiceBusClient') as mock_sbc, \
             patch.object(dol_mod, 'alive_bar') as mock_bar, \
             patch.object(dm, 'GetQueueMetaData'):
            mock_sbc.from_connection_string.return_value = mock_sbc_instance
            bar_instance = MagicMock()
            mock_bar.return_value.__enter__ = MagicMock(return_value=bar_instance)
            mock_bar.return_value.__exit__ = MagicMock(return_value=False)

            dm.EmptyQueue("sensorData", "DEV1", None, mock_db, False, True)

        mock_receiver.complete_message.assert_not_called()


# ===========================================================================
# 5. Database — Insert
# ===========================================================================

class TestDatabaseInsert:
    def test_sensor_data_table_creation(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        df = pd.DataFrame([{
            "id": "1", "deviceId": "D1", "sensorId": "S1",
            "sensorName": "Temp", "value": 22.5, "type": "temperature",
            "unit": "C", "timestamp": 1700000000,
        }])
        db.Insert(df, "sensorData")
        engine = sqlalchemy.create_engine(url)
        result = pd.read_sql("SELECT * FROM sensorData", engine)
        assert len(result) == 1
        assert result.iloc[0]["deviceId"] == "D1"

    def test_sensor_data_extra_columns_filtered(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        df = pd.DataFrame([{
            "id": "1", "deviceId": "D1", "sensorId": "S1",
            "sensorName": "Temp", "value": 22.5, "type": "t",
            "unit": "C", "timestamp": 1700000000,
            "extraCol": "should_not_appear",
        }])
        db.Insert(df, "sensorData")
        engine = sqlalchemy.create_engine(url)
        result = pd.read_sql("SELECT * FROM sensorData", engine)
        assert "extraCol" not in result.columns

    def test_sensor_data_missing_columns_filled(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        df = pd.DataFrame([{"id": "1", "deviceId": "D1"}])
        db.Insert(df, "sensorData")
        engine = sqlalchemy.create_engine(url)
        result = pd.read_sql("SELECT * FROM sensorData", engine)
        assert "sensorId" in result.columns
        assert "timestamp" in result.columns

    def test_sensor_data_append(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        row = {"id": "1", "deviceId": "D1", "sensorId": "S1",
               "sensorName": "T", "value": 1.0, "type": "t",
               "unit": "C", "timestamp": 1700000000}
        db.Insert(pd.DataFrame([row]), "sensorData")
        row["id"] = "2"
        db.Insert(pd.DataFrame([row]), "sensorData")
        engine = sqlalchemy.create_engine(url)
        result = pd.read_sql("SELECT * FROM sensorData", engine)
        assert len(result) == 2

    def test_non_sensor_data_table_creation(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        df = pd.DataFrame([{"deviceId": "D1", "status": "online", "timestamp": 170}])
        db.Insert(df, "sensorStatus")
        engine = sqlalchemy.create_engine(url)
        result = pd.read_sql("SELECT * FROM sensorStatus", engine)
        assert len(result) == 1

    def test_non_sensor_data_column_filtering(self, tmp_path):
        """When table already exists, extra columns in new data are filtered out."""
        url = _sqlite_url(tmp_path)
        db = Database(url)
        df1 = pd.DataFrame([{"deviceId": "D1", "status": "on", "timestamp": 1}])
        db.Insert(df1, "other")
        df2 = pd.DataFrame([{"deviceId": "D2", "status": "off", "timestamp": 2, "extra": "x"}])
        db.Insert(df2, "other")
        engine = sqlalchemy.create_engine(url)
        result = pd.read_sql("SELECT * FROM other", engine)
        assert "extra" not in result.columns
        assert len(result) == 2

    def test_inactive_sensors_list(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        sensors = [{"name": "S1", "devEui": "EUI1", "lastSeenAt": "2024-01-01"}]
        df = pd.DataFrame([{
            "deviceId": "D1", "timestamp": 170,
            "inactiveSensors": sensors,
        }])
        db.Insert(df, "sensorStatus")
        engine = sqlalchemy.create_engine(url)
        inactive = pd.read_sql("SELECT * FROM inactiveSensor", engine)
        assert len(inactive) == 1
        assert inactive.iloc[0]["devEui"] == "EUI1"

    def test_inactive_sensors_json_string(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        sensors = json.dumps([{"name": "S1", "devEui": "EUI1", "lastSeenAt": "2024"}])
        df = pd.DataFrame([{
            "deviceId": "D1", "timestamp": 170,
            "inactiveSensors": sensors,
        }])
        db.Insert(df, "sensorStatus")
        engine = sqlalchemy.create_engine(url)
        inactive = pd.read_sql("SELECT * FROM inactiveSensor", engine)
        assert len(inactive) == 1

    def test_inactive_sensors_empty_list(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        df = pd.DataFrame([{
            "deviceId": "D1", "timestamp": 170,
            "inactiveSensors": [],
        }])
        db.Insert(df, "sensorStatus")
        engine = sqlalchemy.create_engine(url)
        tables = sqlalchemy.inspect(engine).get_table_names()
        assert "inactiveSensor" not in tables

    def test_empty_dataframe_skip(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        df = pd.DataFrame()
        db.Insert(df, "sensorData")
        engine = sqlalchemy.create_engine(url)
        tables = sqlalchemy.inspect(engine).get_table_names()
        assert "sensorData" not in tables


# ===========================================================================
# 6. Database — Export & ExportToExcel
# ===========================================================================

class TestDatabaseExport:
    def _seed_db(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        for i in range(3):
            df = pd.DataFrame([{
                "id": str(i), "deviceId": "D1", "sensorId": "S1",
                "sensorName": "Temp", "value": float(i),
                "type": "t", "unit": "C", "timestamp": 1700000000 + i,
            }])
            db.Insert(df, "sensorData")
        return db, url

    def test_export_single_table(self, tmp_path):
        db, _ = self._seed_db(tmp_path)
        result = db.Export(None, "sensorData")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3

    def test_export_single_table_with_since(self, tmp_path):
        db, _ = self._seed_db(tmp_path)
        # 'since' adds a WHERE date > 'value' clause; pick a date that excludes nothing
        result = db.Export("2020-01-01", "sensorData")
        assert len(result) == 3

    def test_export_all_tables(self, tmp_path):
        db, url = self._seed_db(tmp_path)
        # Add another table
        df2 = pd.DataFrame([{"deviceId": "D1", "status": "on", "timestamp": 170}])
        db.Insert(df2, "sensorStatus")
        with patch.object(dol_mod, 'alive_bar') as mock_bar:
            bar_inst = MagicMock()
            mock_bar.return_value.__enter__ = MagicMock(return_value=bar_inst)
            mock_bar.return_value.__exit__ = MagicMock(return_value=False)
            result = db.Export(None)
        assert isinstance(result, dict)
        assert "sensorData" in result
        assert "sensorStatus" in result

    def test_export_to_excel_creates_file(self, tmp_path):
        db, _ = self._seed_db(tmp_path)
        xlsx = str(tmp_path / "out.xlsx")
        with patch.object(dol_mod, 'alive_bar') as mock_bar:
            bar_inst = MagicMock()
            mock_bar.return_value.__enter__ = MagicMock(return_value=bar_inst)
            mock_bar.return_value.__exit__ = MagicMock(return_value=False)
            result = db.ExportToExcel(xlsx)
        assert result is True
        assert os.path.exists(xlsx)

    def test_export_to_excel_no_data(self, tmp_path):
        url = _sqlite_url(tmp_path)
        db = Database(url)
        xlsx = str(tmp_path / "empty.xlsx")
        with patch.object(dol_mod, 'alive_bar') as mock_bar:
            bar_inst = MagicMock()
            mock_bar.return_value.__enter__ = MagicMock(return_value=bar_inst)
            mock_bar.return_value.__exit__ = MagicMock(return_value=False)
            result = db.ExportToExcel(xlsx)
        assert result is False

    def test_export_returns_date_column(self, tmp_path):
        db, _ = self._seed_db(tmp_path)
        result = db.Export(None, "sensorData")
        assert "date" in result.columns


# ===========================================================================
# 7. GenerateDiagram
# ===========================================================================

class TestGenerateDiagram:
    def test_random_color_valid(self):
        import matplotlib.colors as mcolors
        gd = GenerateDiagram()
        color = gd.RandomColor()
        assert color in mcolors.TABLEAU_COLORS

    def test_random_color_returns_string(self):
        gd = GenerateDiagram()
        assert isinstance(gd.RandomColor(), str)

    def test_generate_plot_calls_savefig(self):
        gd = GenerateDiagram()
        df = pd.DataFrame([{
            "deviceId": "D1", "sensorId": "S1", "sensorName": "Temp",
            "value": 22.5, "unit": "C", "date": "2024-01-01 12:00",
        }])
        with patch.object(dol_mod, 'plt') as mock_plt, \
             patch.object(dol_mod, 'alive_bar') as mock_bar:
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_plt.subplots.return_value = (mock_fig, mock_ax)
            bar_inst = MagicMock()
            mock_bar.return_value.__enter__ = MagicMock(return_value=bar_inst)
            mock_bar.return_value.__exit__ = MagicMock(return_value=False)
            gd.GeneratePlot(df, "/tmp/plot")
        mock_plt.savefig.assert_called_once()
        saved_path = mock_plt.savefig.call_args[0][0]
        assert saved_path.startswith("/tmp/plot-")
        assert saved_path.endswith(".png")


# ===========================================================================
# 8. ElasticMailClient
# ===========================================================================

class TestElasticMailClient:
    def _config(self):
        return {"elasticApiKey": "APIKEY", "user": "u@test.com"}

    def test_init_sets_paths(self):
        client = ElasticMailClient(self._config(), "/base", "2024-01-01")
        assert client.rootPath == os.path.join("/base", "2024-01-01")
        assert client.zipname == os.path.join("/base", "2024-01-01")

    def test_request_post(self):
        client = ElasticMailClient(self._config(), "/b", "dt")
        resp = MagicMock()
        resp.json.return_value = {"success": True}
        with patch("requests.post", return_value=resp) as mp:
            client.Request("POST", "/email/send", {"subject": "test"})
        mp.assert_called_once()

    def test_request_get(self):
        client = ElasticMailClient(self._config(), "/b", "dt")
        resp = MagicMock()
        resp.json.return_value = {"success": True}
        with patch("requests.get", return_value=resp) as mg:
            client.Request("GET", "/status", {"key": "val"})
        mg.assert_called_once()

    def test_request_error_raises(self):
        client = ElasticMailClient(self._config(), "/b", "dt")
        resp = MagicMock()
        resp.json.return_value = {"error": "bad request"}
        with patch("requests.post", return_value=resp), \
             pytest.raises(Exception, match="bad request"):
            client.Request("POST", "/email/send", {"subject": "test"})

    def test_send_creates_zip_and_posts(self):
        client = ElasticMailClient(self._config(), "/b", "dt")
        resp = MagicMock()
        resp.json.return_value = {"success": True}
        with patch("shutil.make_archive") as mock_archive, \
             patch("builtins.open", mock_open(read_data=b"zipdata")), \
             patch("requests.post", return_value=resp) as mp:
            client.Send()
        mock_archive.assert_called_once_with(client.zipname, "zip", client.rootPath)
        mp.assert_called_once()


# ===========================================================================
# 9. main() Function
# ===========================================================================

class TestMain:
    def _patch_main(self):
        """Return a dict of common patches for main()."""
        config_data = {"user": "u@test.com", "pwd": "pw", "url": "https://api/"}
        return {
            "config_data": config_data,
            "open_patch": patch("builtins.open", mock_open(read_data=json.dumps(config_data))),
            "json_load_patch": patch.object(dol_mod.json, "load", return_value=config_data),
            "dm_patch": patch.object(dol_mod, "DeviceManagement"),
            "db_patch": patch.object(dol_mod, "Database"),
            "gd_patch": patch.object(dol_mod, "GenerateDiagram"),
            "em_patch": patch.object(dol_mod, "ElasticMailClient"),
            "exists_patch": patch("os.path.exists", return_value=True),
            "mkdir_patch": patch("os.mkdir"),
        }

    def test_default_folder_uses_tempdir(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"], p["db_patch"], \
             p["exists_patch"], p["mkdir_patch"]:
            with patch.object(dol_mod.tempfile, "gettempdir", return_value="/tmp") as mock_tmp:
                main(config="cfg.json", folder=None, export_device="DEV1")
            mock_tmp.assert_called_once()

    def test_custom_folder(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"], p["db_patch"], \
             p["exists_patch"], p["mkdir_patch"]:
            # Should not call gettempdir when folder is provided
            with patch.object(dol_mod.tempfile, "gettempdir") as mock_tmp:
                main(config="cfg.json", folder="/custom", export_device="DEV1")
            mock_tmp.assert_not_called()

    def test_sqlite_uri_backslash_replacement(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"], \
             p["exists_patch"], p["mkdir_patch"]:
            with patch.object(dol_mod, "Database") as mock_db:
                main(config="cfg.json", folder="/tmp", export_device="DEV1")
            call_url = mock_db.call_args[0][0]
            assert "\\" not in call_url
            assert call_url.startswith("sqlite:///")

    def test_claim_device_arg_parsing(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"] as mock_dm:
            mock_instance = mock_dm.return_value
            main(config="cfg.json", claim_device="MAC1 KEY1 GW owner name1")
        mock_instance.Claim.assert_called_once_with("MAC1", "KEY1", "GW", "owner", "name1")

    def test_unclaim_device(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"] as mock_dm:
            mock_instance = mock_dm.return_value
            main(config="cfg.json", unclaim_device="MAC1")
        mock_instance.Unclaim.assert_called_once_with("MAC1")

    def test_add_lora_sensor_arg_parsing(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"] as mock_dm:
            mock_instance = mock_dm.return_value
            main(config="cfg.json", add_lora_sensor="MAC1 Sensor1 EUI1 TYPE 120")
        mock_instance.AddLoraSensor.assert_called_once_with("MAC1", "Sensor1", "EUI1", "TYPE", 120)

    def test_remove_lora_sensor_arg_parsing(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"] as mock_dm:
            mock_instance = mock_dm.return_value
            main(config="cfg.json", remove_lora_sensor="MAC1 EUI1")
        mock_instance.RemoveLoraSensor.assert_called_once_with("MAC1", "EUI1")

    def test_export_device_workflow(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"] as mock_dm, \
             p["db_patch"] as mock_db, p["exists_patch"], p["mkdir_patch"]:
            mock_dev = mock_dm.return_value
            main(config="cfg.json", folder="/tmp", export_device="DEV1")
        assert mock_dev.EmptyQueue.call_count == 2  # DATA + STATUS

    def test_export_all_workflow(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"] as mock_dm, \
             p["db_patch"] as mock_db, p["exists_patch"], p["mkdir_patch"]:
            mock_dev = mock_dm.return_value
            main(config="cfg.json", folder="/tmp", export_all="integrator1")
        assert mock_dev.EmptyQueue.call_count == 2

    def test_excel_flag(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"], \
             p["db_patch"] as mock_db, p["exists_patch"], p["mkdir_patch"]:
            mock_db_inst = mock_db.return_value
            main(config="cfg.json", folder="/tmp", export_device="DEV1", excel=True)
        mock_db_inst.ExportToExcel.assert_called_once()

    def test_plot_flag(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"], \
             p["db_patch"] as mock_db, p["gd_patch"] as mock_gd, \
             p["exists_patch"], p["mkdir_patch"]:
            mock_db_inst = mock_db.return_value
            main(config="cfg.json", folder="/tmp", export_device="DEV1", plot=True)
        mock_db_inst.Export.assert_called_once()

    def test_folder_creation(self):
        p = self._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"], \
             p["db_patch"], p["mkdir_patch"] as mock_mkdir:
            with patch("os.path.exists", return_value=False):
                main(config="cfg.json", folder="/tmp", export_device="DEV1")
        assert mock_mkdir.call_count == 2  # folderBase + folderSubPath


# ===========================================================================
# 10. Cross-Platform Paths
# ===========================================================================

class TestCrossPlatformPaths:
    def test_os_path_join_for_folder(self):
        """os.path.join is used for folder construction in main()."""
        p = TestMain()._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"], \
             p["db_patch"], p["exists_patch"], p["mkdir_patch"]:
            with patch("os.path.join", wraps=os.path.join) as mock_join:
                main(config="cfg.json", folder="/base", export_device="DEV1")
            # os.path.join must have been called for path construction
            assert mock_join.call_count >= 2

    def test_sqlite_uri_windows_backslashes(self):
        """Backslashes in Windows paths should be replaced in SQLite URI."""
        p = TestMain()._patch_main()
        with p["open_patch"], p["json_load_patch"], p["dm_patch"], \
             p["exists_patch"], p["mkdir_patch"]:
            with patch("os.path.join", return_value="C:\\Users\\joe\\data.db"):
                with patch.object(dol_mod, "Database") as mock_db:
                    main(config="cfg.json", folder="C:\\Users\\joe", export_device="DEV1")
                url = mock_db.call_args[0][0]
                assert "\\" not in url
                assert "C:/Users/joe/data.db" in url

    def test_tempfile_gettempdir_returns_valid(self):
        result = tempfile.gettempdir()
        assert os.path.isdir(result)
