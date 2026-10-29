from enum import Enum
from alive_progress import alive_bar
import base64
import json
import datetime
import re
import shlex
import pandas as pd
import plac
import sqlalchemy
import os
import tempfile
import matplotlib.colors as mcolors
import random
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests

from elasticmail import ElasticMailClient

# API and queue messages mix camelCase and PascalCase keys e.g. messageText / MessageText
def _lowerKeys(data):
    return {str(k).lower(): v for k, v in data.items()} if isinstance(data, dict) else {}

class DeviceManagement:
    from azure.servicebus import ServiceBusClient, ServiceBusMessage

    def __init__(self, config):
        self.token = ""
        self.tokenExpiresTime = 0
        self.queueConn = ""
        self.queueSize = ""
        self.queueName = ""
        self.queueDeadletterSize = ""
        self.devices = ""
        self.user = config["user"]
        self.pwd = config["pwd"]
        self.apiURL = config["url"]
        self.tokenCachePath = os.path.join(os.path.expanduser("~"), ".cloud_api_token_cache.json")
        self.current_time = int(datetime.datetime.now().timestamp())
                                
        # Try to load token from cache first
        self._loadTokenFromCache()
        
        # If token not valid, login to get a new one
        if not self._isTokenValid():
            self._login()
    
    def _loadTokenFromCache(self):
        try:
            if os.path.exists(self.tokenCachePath):
                with open(self.tokenCachePath, 'r') as f:
                    cache = json.load(f)
                    # token belongs to one login on one environment (qa / prod)
                    if cache.get("user") != self.user or cache.get("url") != self.apiURL:
                        print("Cached token is for another login or environment, ignoring it")
                        return
                    self.token = cache.get("token", "")
                    self.tokenExpiresTime = cache.get("expireTime", 0)
                    print(f"Token loaded from cache, valid for {self.tokenExpiresTime - self.current_time} more seconds")
        except Exception as e:
            print(f"Error loading token cache: {e}")

    def _invalidateTokenCache(self):
        self.token = ""
        self.tokenExpiresTime = 0
        try:
            if os.path.exists(self.tokenCachePath):
                os.remove(self.tokenCachePath)
                print("Cached token rejected by server; cleared it. Re-run to log in again.")
        except Exception as e:
            print(f"Error clearing token cache: {e}")
    
    def _isTokenValid(self):
        
        if not self.token or self.tokenExpiresTime < self.current_time:
            print("Token is not valid or has expired")
            return False
        else:
            remaining = self.tokenExpiresTime - self.current_time
            print(f"Token valid for {remaining} more seconds")
            return True
    
    def _saveTokenToCache(self):
        try:
            cache = {
                "user": self.user,
                "url": self.apiURL,
                "token": self.token,
                "expireTime": self.tokenExpiresTime
            }
            with open(self.tokenCachePath, 'w') as f:
                json.dump(cache, f)
            print(f"Token saved to cache, expires at {self.tokenExpiresTime}")
        except Exception as e:
            print(f"Error saving token cache: {e}")
    
    # login to cloud account
    def _login(self):
        print("Login to cloud account: " + self.user)
        result = requests.post(self.apiURL + 'auth/login', 
                            json={"email": self.user,"password": self.pwd})
        self._checkResponse(result)
        response = result.json()
        
        self.token = response['accessToken']
        
        # Store expiration time as Unix timestamp (seconds since epoch)
        
        expires_in_seconds = int(response['expiresIn'])
        self.tokenExpiresTime = self.current_time + expires_in_seconds
        
        print(f"Token expires after { expires_in_seconds } seconds")
        self._saveTokenToCache()

    # check request response
    def _checkResponse(self, result):
        if result.status_code >= 200 and result.status_code < 300:
            if result.text.strip():  # Check if response has content
                try:
                    response = result.json()
                    return {"success": True, "data": response}
                except json.JSONDecodeError:
                    print(f"Request returned non-JSON response: {result.text}")
                    return {"success": True, "data": result.text}  # Return text as data
            else:
                print("Request successful (empty response)")
                return {"success": True, "data": None}
        else:
            print(f"Request failed: {result.status_code} - {result.text}")
            # A 401 on an authenticated call means the cached token is stale or
            # the account is not authorized. Drop the cache so the next run logs
            # in fresh instead of replaying the same rejected token.
            if result.status_code == 401:
                self._invalidateTokenCache()
            raise RuntimeError(
                f"Request failed: {result.status_code} - {result.text}")

        
    # add gateway to account
    def Claim(self, mac, key, type, owner, name):
        result = requests.post(
            self.apiURL + 'devices/claim', 
            headers={'Authorization': 'Bearer ' + self.token},
            json={
                "macAddress": mac,
                "key": key,
                "deviceType": type,
                "owner": owner,
                "deviceName": name
            } )
        
        self._checkResponse(result)

    # remove gateway from account and will reset configuration
    def Unclaim(self, mac):
        result = requests.delete(
            self.apiURL + 'devices/claim/' + mac, 
            headers={'Authorization': 'Bearer ' + self.token}
        )
        
        self._checkResponse(result)

    # add LoRa sensor to given already claimed gateway
    def AddLoraSensor(self, mac, name, dev_eui, type, sample_rate=60):
        result = requests.post(
            self.apiURL + f'devices/{mac}/sensor', 
            headers={'Authorization': 'Bearer ' + self.token},
            json = {
            "devEui": dev_eui,
            "name": name,
            "type": type,
            "sampleRate": sample_rate
        } )
        
        self._checkResponse(result)

    # remove LoRa sensor from given gateway
    def RemoveLoraSensor(self, mac, dev_eui):
        result = requests.delete(self.apiURL + 'devices/' + mac + '/sensor/' + dev_eui, 
                                headers={'Authorization': 'Bearer ' + self.token} )
        
        self._checkResponse(result)

    # update LoRa sensor configuration
    def UpdateLoraSensor(self, mac, dev_eui, sample_rate):
        result = requests.put(self.apiURL + 'devices/'+mac+'/sensor', 
                                headers={'Authorization': 'Bearer ' + self.token},
                                json={
                                        "devEui": dev_eui,
                                        "sampleRate": sample_rate
                                } )
        
        self._checkResponse(result)

    # add wired sensor to given already claimed gateway (TBD: more user friendly way to add wired sensors)   
    def AddWiredSensor(self, mac, sensors):
        result = requests.put(self.apiURL + 'devices/'+mac+'/wiredSensor', 
                                headers={'Authorization': 'Bearer ' + self.token},
                                json={ "sensors": sensors } )
        
        self._checkResponse(result)

    # auto calibrate IDOL65 camera, result arrives later as VisionStatus on the status queue
    def Calibrate(self, mac):
        result = requests.post(self.apiURL + f'devices/{mac}/calibrate',
                                headers={'Authorization': 'Bearer ' + self.token} )

        response = self._checkResponse(result)
        print(f"Calibration requested: {response['data']}")

    # manually calibrate IDOL65 camera with angles and height (mm) from the floor
    def ManualCalibrate(self, mac, angle_x, angle_y, height):
        if not -4 <= angle_x <= 4:
            raise ValueError(f"angleX must be between -4 and 4, got {angle_x}")
        if not -4 <= angle_y <= 4:
            raise ValueError(f"angleY must be between -4 and 4, got {angle_y}")
        if not 2000 <= height <= 2500:
            raise ValueError(f"height must be between 2000 and 2500, got {height}")

        result = requests.post(self.apiURL + f'devices/{mac}/manualCalibrate',
                                headers={'Authorization': 'Bearer ' + self.token},
                                json={
                                        "angleX": angle_x,
                                        "angleY": angle_y,
                                        "height": height
                                } )

        response = self._checkResponse(result)
        print(f"Manual calibration requested: {response['data']}")

    # request a pair of IR images from IDOL65 camera and save them in folder
    def GetImage(self, mac, folder):
        result = requests.post(self.apiURL + f'devices/{mac}/getImage',
                                headers={'Authorization': 'Bearer ' + self.token},
                                timeout=180 )

        # binary body, so only use _checkResponse for the error case
        if not 200 <= result.status_code < 300:
            self._checkResponse(result)

        baseName = mac + "_" + datetime.datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
        images = []
        if 'json' in result.headers.get('Content-Type', ''):
            # images may come back base64 encoded as a string or a list of strings
            body = result.json()
            for item in (body if isinstance(body, list) else [body]):
                if isinstance(item, str):
                    images.append(base64.b64decode(item))
                else:
                    print(f"Unexpected image item in response: {str(item)[:200]}")
        else:
            images.append(result.content)

        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?',
                          result.headers.get('Content-Disposition', ''))
        os.makedirs(folder, exist_ok=True)
        paths = []
        for i, image in enumerate(images):
            if match and len(images) == 1:
                fileName = os.path.basename(match.group(1))
            else:
                suffix = f"_{i + 1}" if len(images) > 1 else ""
                fileName = baseName + suffix + self._imageExtension(image)
            path = os.path.join(folder, fileName)
            with open(path, 'wb') as f:
                f.write(image)
            print(f"Saved image: {path}")
            paths.append(path)
        return paths

    @staticmethod
    def _imageExtension(content):
        if content.startswith(b'PK'):
            return ".zip"
        if content.startswith(b'\x89PNG'):
            return ".png"
        if content.startswith(b'\xff\xd8'):
            return ".jpg"
        if content.startswith(b'II*\x00') or content.startswith(b'MM\x00*'):
            return ".tiff"
        return ".bin"

    # get queue metadata
    def GetQueueMetaData(self, type):
        result = requests.get(self.apiURL + 'management/queue/',
                            headers={'Authorization': 'Bearer ' + self.token} )

        self._checkResponse(result)
        queue = result.json()

        if type == Table.DATA.value:
            self.queueConn = queue['dataQueueConnection']
            self.queueName = queue['dataQueueName']
            self.queueSize = int(queue['dataQueueMessageCount'])
            self.queueDeadletterSize = int(queue['dataQueueDeadLetterCount'])
        elif type == Table.STATUS.value:
            self.queueConn = queue['statusQueueConnection']
            self.queueName = queue['statusQueueName']
            self.queueSize = int(queue['statusQueueMessageCount'])
            self.queueDeadletterSize = int(queue['statusQueueDeadLetterCount'])

    # list all devices on account    
    def ListDevices(self, pageSize=100):
        page = 1
        devices = []
        while True:
            result = requests.get(self.apiURL + f'devices?page={page}&pageSize={pageSize}',
                                headers={'Authorization': 'Bearer ' + self.token} )
            self._checkResponse(result)
            response = result.json()
            devices.extend(response["devices"])

            total = response.get("deviceTotal", len(devices))
            if not response["devices"] or len(devices) >= total:
                break
            page += 1

        self.devices = {**response, "devices": devices}

        for device in devices:
            print(device)

    # get device by mac address
    def GetDevice(self, mac):
        result = requests.get(self.apiURL + 'devices/' + mac,
                            headers={'Authorization': 'Bearer ' + self.token} )
        self._checkResponse(result)
        device = result.json()

        print(f"Mac: {device.get('mac')}")
        print(f"Key: {device.get('key')}")
        print(f"Type: {device.get('deviceType')}")
        print(f"Owner: {device.get('owner')}")
        print(f"Name: {device.get('deviceName')}")
        print(f"Created: {device.get('createdAt')}")
        print(f"Updated: {device.get('updatedAt')}")
        print(f"Connected: {device.get('connectionState')}")
        print(f"Firmware: {device.get('firmwareVersion')}")
        print(f"Online: {device.get('isOnline')}")
        print(f"lastActivityUtc: {device.get('lastActivityUtc')}")
        print(f"cloudToDeviceMessages: {device.get('cloudToDeviceMessages')}")

        # IDOL65 cameras have no sensors, so these are null
        for loraSensor in device.get("sensors") or []:
            print(loraSensor)

        for wiredSensor in device.get("wiredSensors") or []:
            print(wiredSensor)

        camera = device.get("cameraStatus")
        if camera:
            print(f"Camera dirty: {camera.get('cameraDirty')}")
            print(f"Dirty detection enabled: {camera.get('dirtyDetectionEnabled')}")
            print(f"Manually calibrated: {camera.get('manuallyCalibrated')}")
            print(f"Calibration status: {camera.get('calibrationStatus')}")
            print(f"Calibration update: {camera.get('calibrationUpdate')}")
            print(f"Last calibration: {camera.get('lastCalibrationTime')}")
            for message in camera.get("messages") or []:
                message = _lowerKeys(message)
                print(f"Camera message {message.get('messageid')}: {message.get('messagetext')} {message.get('messagepayload') or ''}")

    # empty queue to local database based on type, device or integrator
    # if device is None, then all devices will be processed
    def EmptyQueue(self, type, device, integrator, db, deadletter=False, readonly=False):
        totalCount = 0
        foundCount = 0
        
        self.GetQueueMetaData(type)
        
        if deadletter:
            queueSize = self.queueDeadletterSize
            sub_queue = "deadletter" 
        else:
            queueSize = self.queueSize
            sub_queue = None

        with alive_bar(int(queueSize), title="Receive data from " + (sub_queue or "queue") + ": " + self.queueName) as bar:
            servicebusClient = self.ServiceBusClient.from_connection_string(conn_str=self.queueConn)
            with servicebusClient:
                receiver = servicebusClient.get_queue_receiver(queue_name=self.queueName, sub_queue=sub_queue, max_wait_time=5, prefetch_count=20)
                with receiver:
                    try:
                        for msg in receiver:  # type: ignore
                            dataJson = json.loads(str(msg))
                            # subject tells status messages apart e.g. VisionStatus, SensorBatteryUpdates
                            subject = getattr(msg, 'subject', None)
                            if device != None:
                                # if device match desired
                                if str(dataJson['deviceId']) == str(device):
                                    self._storeMessage(receiver, msg, db, dataJson, type, subject, readonly)
                                    foundCount += 1
                                else:
                                    receiver.abandon_message(msg)
                            elif integrator != None:
                                # if integrator match desired
                                self._storeMessage(receiver, msg, db, dataJson, type, subject, readonly)
                                foundCount += 1
                            bar()
                            bar.text("found: " + str(foundCount) + " of " + str(queueSize) + " total messages")
                            totalCount += 1

                    except KeyboardInterrupt:
                        pass

            print("Found: " + str(foundCount))

    # insert message and only remove it from the queue when it was stored
    def _storeMessage(self, receiver, msg, db, dataJson, type, subject, readonly):
        stored = db.Insert(dataJson, type, subject)
        if readonly:
            return
        if stored:
            receiver.complete_message(msg)
        else:
            print(f"Message kept in queue, insert failed: {str(dataJson)[:200]}")
            receiver.abandon_message(msg)

class Database:
    def __init__(self, fileURL):
        self.numberInserted = ""
        self.fileURL = fileURL

    # IDOL65 weight statistics, stored next to sensorData and joined on id
    WEIGHT_KEYS = ['count', 'countdelta', 'minweight', 'maxweight', 'timespan', 'sd', 'skewness', 'withinspec']

    # insert a queue message (dict) or a dataframe into table, returns True when stored
    def Insert(self, data, table, subject=None):
        if isinstance(data, dict):
            try:
                data = self._splitMessage(data, table, subject)
            except Exception as e:
                print(f"Error while storing message: {e}")
                return False
            # message fully stored in its own tables
            if not data:
                return True
            df = pd.json_normalize(data)
        else:
            df = data

        if df.size > 0:
            try:
                # Special handling for sensorData table with explicit schema
                if table == 'sensorData':
                    # Define the exact schema we want
                    expected_columns = ['id', 'deviceId', 'sensorId', 'sensorName',
                                    'value', 'type', 'unit', 'timestamp']
                    column_types = {
                        'id': 'TEXT',
                        'deviceId': 'TEXT',
                        'sensorId': 'TEXT',
                        'sensorName': 'TEXT',
                        'value': 'FLOAT',
                        'type': 'TEXT',
                        'unit': 'TEXT',
                        'timestamp': 'BIGINT'
                    }

                    # Create a filtered dataframe with only the expected columns
                    filtered_df = pd.DataFrame()
                    for col in expected_columns:
                        if col in df.columns:
                            filtered_df[col] = df[col]
                        else:
                            # Create empty column with appropriate type if missing
                            if col == 'value':
                                filtered_df[col] = float('nan')
                            elif col == 'timestamp':
                                filtered_df[col] = 0
                            else:
                                filtered_df[col] = ''

                    # Create engine
                    engine = sqlalchemy.create_engine(self.fileURL)

                    # Check if table exists, if not create it with proper schema
                    if not sqlalchemy.inspect(engine).has_table(table):
                        # Create the table with exact schema
                        with engine.connect() as conn:
                            cols = []
                            for col_name, col_type in column_types.items():
                                cols.append(f'"{col_name}" {col_type}')
                            schema = ', '.join(cols)

                            # Use SQLAlchemy text() to create a proper executable statement
                            from sqlalchemy import text
                            create_statement = text(f'CREATE TABLE IF NOT EXISTS "{table}" ({schema})')
                            conn.execute(create_statement)

                            # Commit the transaction (required in SQLAlchemy 2.0+)
                            conn.commit()

                            print(f"Created {table} table with explicit schema")

                    # Insert the filtered data
                    self.numberInserted = filtered_df.to_sql(str(table), self.fileURL,
                                                        if_exists='append', index=False)

                # Regular handling for other tables
                else:
                    # Handle inactiveSensors if present
                    if 'inactiveSensors' in df.columns:
                        # Prepare data for inactiveSensor table
                        inactive_records = []
                        # Process each row that had inactiveSensors
                        for i, row in df.iterrows():
                            sensors = row['inactiveSensors']

                            # Convert to list if it's a string
                            if isinstance(sensors, str):
                                try:
                                    sensors = json.loads(sensors)
                                except json.JSONDecodeError:
                                    # If not valid JSON, skip
                                    continue

                            # Process each sensor in the array
                            if isinstance(sensors, list):
                                for sensor in sensors:
                                    if isinstance(sensor, dict):
                                        inactive_records.append({
                                            'deviceId': row['deviceId'],
                                            'timestamp': row['timestamp'],
                                            'name': sensor.get('name', ''),
                                            'devEui': sensor.get('devEui', ''),
                                            'lastSeenAt': sensor.get('lastSeenAt', '')
                                        })

                        if inactive_records:
                            self._append(pd.DataFrame(inactive_records), Table.INACTIVE.value)

                        # Remove inactiveSensors column from main data
                        df = df.drop(columns=['inactiveSensors'])

                    # unknown nested values are kept as json text, sqlite can't store lists
                    df = df.apply(lambda col: col.map(
                        lambda v: json.dumps(v) if isinstance(v, (list, dict)) else v))
                    self._append(df, table)
                return True

            except sqlalchemy.exc.OperationalError as e:
                print(f'Error occurred while executing a query: {e.args}')
            except Exception as general_error:
                print(f"Unexpected error: {general_error}")
            return False
        else:
            print("Skipped insert to database, since data size is 0")
            return True

    # store nested lists of a queue message in their own tables and return the flat remainder
    def _splitMessage(self, data, table, subject):
        data = dict(data)
        deviceId = data.get('deviceId')
        timestamp = data.get('timestamp')

        if table == Table.DATA.value:
            lower = _lowerKeys(data)
            if any(key in lower for key in self.WEIGHT_KEYS):
                weight = {'id': data.get('id'), 'deviceId': deviceId,
                          'sensorId': data.get('sensorId'), 'timestamp': timestamp}
                weight.update({key: lower.get(key) for key in self.WEIGHT_KEYS})
                self._append(pd.DataFrame([weight]), Table.WEIGHT.value)
            return data

        if subject == 'VisionStatus' or 'visionStatus' in data:
            vision = _lowerKeys(data.pop('visionStatus', None))
            self._append(pd.DataFrame([{
                'deviceId': deviceId,
                'timestamp': timestamp,
                'isDirty': vision.get('isdirty'),
                'isDetectingDirty': vision.get('isdetectingdirty'),
                'isDeviceManuallyCalibrated': vision.get('isdevicemanuallycalibrated'),
                'calibration': vision.get('calibration'),
                'calibrationLastUpdate': vision.get('calibrationlastupdate'),
                'lastWeightCacheClearCount': vision.get('lastweightcacheclearcount'),
                'lastWeightCacheClearedUpdate': vision.get('lastweightcacheclearedupdate'),
            }]), Table.VISION.value)

            messages = [_lowerKeys(m) for m in vision.get('messages') or []]
            if messages:
                self._append(pd.DataFrame([{
                    'deviceId': deviceId,
                    'timestamp': timestamp,
                    'messageId': m.get('messageid'),
                    'messageText': m.get('messagetext'),
                    'messagePayload': m.get('messagepayload'),
                } for m in messages]), Table.VISION_MESSAGE.value)
            return {}

        if subject == 'SensorBatteryUpdates' or 'batteryUpdates' in data:
            updates = [_lowerKeys(u) for u in data.pop('batteryUpdates', None) or []]
            if updates:
                self._append(pd.DataFrame([{
                    'deviceId': deviceId,
                    'timestamp': timestamp,
                    'devEui': u.get('deveui'),
                    'code': u.get('code'),
                    'batteryStatus': u.get('batterystatus'),
                } for u in updates]), Table.BATTERY.value)
            return {}

        if subject:
            data['subject'] = subject
        return data

    # append dataframe, creating the table or keeping only the columns it already has
    def _append(self, df, table):
        engine = sqlalchemy.create_engine(self.fileURL)
        inspector = sqlalchemy.inspect(engine)
        if inspector.has_table(table):
            existing_columns = [col['name'] for col in inspector.get_columns(table)]
            df = df[[col for col in df.columns if col in existing_columns]]
            if df.empty:
                print(f"No matching columns found between data and table {table}")
                return
        else:
            print(f"Created new table {table}")
        self.numberInserted = df.to_sql(str(table), self.fileURL, if_exists='append', index=False)

    def Export(self, since, tableName=None):
        if since:
            sort = " WHERE date > '" + since + "'"
        else:
            sort = ""
        
        # If a specific table is requested, just export that one
        if tableName:
            return self._export_table(tableName, sort)
        
        # Otherwise, get all tables and export each one
        tables = self._get_all_tables()
        result = {}
        
        with alive_bar(len(tables), title="Exporting tables") as bar:
            for table in tables:
                result[table] = self._export_table(table, sort, progress_bar=bar)
                
        return result

    def _export_table(self, tableName, filter_clause="", progress_bar=None):
        df = pd.DataFrame()
        try:
            query = f"SELECT *, DATETIME(timestamp, 'unixepoch') AS date FROM {tableName}{filter_clause} ORDER BY date ASC"
            df = pd.read_sql_query(query, self.fileURL)
            if progress_bar:
                progress_bar.text(f"Exported {len(df)} rows from {tableName}")
        except sqlalchemy.exc.OperationalError as e:
            print(f'Error occurred while executing query on {tableName}: {e.args}')
        return df

    def _get_all_tables(self):
        try:
            engine = sqlalchemy.create_engine(self.fileURL)
            inspector = sqlalchemy.inspect(engine)
            return inspector.get_table_names()
        except Exception as e:
            print(f"Error getting table names: {e}")
            return []

    def ExportToExcel(self, filename, since=None):
        tables_data = self.Export(since)
        
        if not tables_data:
            print("No data to export")
            return False
        
        try:
            with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
                for table_name, df in tables_data.items():
                    if not df.empty:
                        # Limit sheet name to 31 characters (Excel limitation)
                        sheet_name = table_name[:31]
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                        print(f"Exported {len(df)} rows to sheet '{sheet_name}'")
                        
                        # Auto-adjust columns width for better readability
                        worksheet = writer.sheets[sheet_name]
                        for i, col in enumerate(df.columns):
                            # Set column width based on max content length
                            max_len = max(
                                df[col].astype(str).map(len).max(),  # max content length
                                len(str(col))  # header length
                            ) + 2  # add a little extra space
                            worksheet.set_column(i, i, min(max_len, 50))  # cap at 50
                            
            print(f"Successfully created Excel file: {filename}")
            return True
        except Exception as e:
            print(f"Error exporting to Excel: {e}")
            return False

class GenerateDiagram:

    def RandomColor(self):
        color = random.choice(list(mcolors.TABLEAU_COLORS.keys()))
        return color

    def GeneratePlot(self, dataFrame, pngPath):
        # Filter data to include only these specific columns
        filteredData = dataFrame[['deviceId', 'sensorId', 'sensorName', 'value', 'unit', 'date']]
        deviceList = filteredData['deviceId'].unique()
    
        for device in deviceList:
            deviceData = filteredData[filteredData['deviceId'] == device]
            sensorList = deviceData['sensorId'].unique()
            for sensor in sensorList:
                sensorData = deviceData[deviceData['sensorId'] == sensor]
                unitList = sensorData['unit'].unique()
                sensorName = str(sensorData['sensorName'].iloc[0])
                with alive_bar(len(unitList), title="Generate plot for " + sensor) as bar:
                    for unit in unitList:
                        # Prepare the plot
                        fig, ax = plt.subplots(figsize=(30, 7))
            
                        sensorUnitData = sensorData[sensorData['unit'] == unit]
                        bar.text(sensor + " - " + sensorName)
                        
                        SensorTimestamp = pd.to_datetime(sensorUnitData['date'])
                        
                        ax.scatter(SensorTimestamp, sensorUnitData['value'], label=sensor, color=self.RandomColor(), alpha=1)
                        ax.set_xlabel('date')
                        ax.set_ylabel(unit) 

                        # Title and legend
                        ax.set_title(device + ' - ' + sensorName + ' - ' + unit )
                        ax.legend()

                        # Format the x-axis to show dates and times, with each hour marked
                        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
                        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H'))

                        # Rotate date labels to avoid overlap
                        plt.xticks(rotation=90)
                        plt.tight_layout()

                        # Save the plot to a file
                        # units like m/s or %RH are not valid in file names
                        safeUnit = re.sub(r'[^\w.-]', '_', str(unit))
                        plt.savefig(pngPath + "-" + device + "-" + sensor + "-" + safeUnit + ".png")
                        plt.close()

                        bar()        

# split a CLI option value into its fields, quotes keep spaces e.g. '000ecd020000 "Pen 3" ...'
def _splitArgs(value, option, fields):
    try:
        args = shlex.split(value)
    except ValueError as e:
        raise SystemExit(f"{option}: {e} in '{value}'")
    if len(args) != len(fields.split()):
        raise SystemExit(f"{option} expects {len(fields.split())} values: {fields}, got {len(args)}: {args}\n"
                         f"Put values containing spaces in quotes, e.g. \"Pen 3\"")
    return args

class Table(Enum):
    DATA = "sensorData"
    STATUS = "sensorStatus"
    INACTIVE = "inactiveSensor"
    VISION = "visionStatus"
    VISION_MESSAGE = "visionMessage"
    WEIGHT = "weightStatistics"
    BATTERY = "batteryUpdate"

# cli command line
@plac.annotations(
    config=('json config file e.g. -c config.json', 'option', 'c', str),
    folder=('Work output folder e.g. -f /path/to/dir', 'option', 'f', str),
    claim_device=('Claim device by providing its MAC address, key, type, owner and name, quote values with spaces e.g. -cd \'000ecd020000 nMNLPSNT IDOL64 Joe "Gateway 1"\'', 'option', 'cd', str),
    unclaim_device=('Unclaim device by providing its MAC address e.g. -ud 000ecd020000', 'option', 'ud', str),
    add_lora_sensor=('Add LoRa sensor to device by providing its MAC address, name, devEui, type and sample rate, quote names with spaces e.g. -als \'000ecd020000 "Pen 3" f2b3d57ed8522302 DOL53 60\'', 'option', 'als', str),
    remove_lora_sensor=('Remove LoRa sensor from device by providing its MAC address and devEui e.g. -rls \'000ecd020000 f2b3d57ed8522302\'', 'option', 'rls', str),
    update_lora_sensor=('Update LoRa sensor configuration by providing its MAC address, devEui and sample rate e.g. -uls \'000ecd020000 f2b3d57ed8522302 60\'', 'option', 'uls', str),
    add_wired_sensor=('Add wired sensor to device by providing its MAC address and sensors e.g. -aws \'000ecd020000 [{"port":1,"wiredSensorType":"DOL139","samplingRate":60},{"port":2,"wiredSensorType":"DOL53","samplingRate":60}]\'', 'option', 'aws', str),
    calibrate=('Auto calibrate IDOL65 camera by providing its MAC address e.g. -cal 000ecd020000', 'option', 'cal', str),
    manual_calibrate=('Manually calibrate IDOL65 camera by providing its MAC address, angleX (-4..4), angleY (-4..4) and height in mm (2000..2500) e.g. -mcal \'000ecd020000 0 0 2300\'', 'option', 'mcal', str),
    get_image=('Request a pair of IR images from IDOL65 camera, saved in work folder e.g. -gi 000ecd020000', 'option', 'gi', str),
    list_devices=('list all gateways on account e.g. -ld', 'flag', 'ld'),
    list_sensors=('list all sensors for a device by providing its MAC address e.g. -ls 000ecd020000', 'option', 'ls', str),
    export_all=('Export all by given name -ea Joe', 'option', 'ea', str),
    export_device=('Export by device MAC address to use e.g -ed 000ecd020000', 'option', 'ed', str),
    dead_letter=('Select cloud deadletter queue instead of regular e.g. -dl', 'flag', 'dl'),
    read_only=('Only read the queue (max 3 times, then queue go to deadletter) e.g. -ro', 'flag', 'ro'),
    excel=('export db to excel i.e. -e', 'flag', 'e'),
    plot=('generate plot from excel i.e. -p', 'flag', 'p'),
    mail=('send mail with excel and plots. Require -e and/or -p e.g. -e -p -m', 'flag', 'm'),
    since=('Date in YYYY-MM-DD format', 'option', 's', str)
)
def main(config="config-qa-example.json", folder=None, claim_device=None, unclaim_device=None,
         add_lora_sensor=None, remove_lora_sensor=None, update_lora_sensor=None, 
         add_wired_sensor=None, calibrate=None, manual_calibrate=None, get_image=None,
         list_devices=False, list_sensors=None, export_all=None,
         export_device=None, dead_letter=False, read_only=False, excel=False, plot=False,
         mail=False, since=None):

    configData = json.load(open(config))

    if folder:
        folderDir = folder
    else:
        folderDir = tempfile.gettempdir()

    dateTimeNow = datetime.datetime.now().strftime("%d-%m-%Y_%H-%M")
    dev = DeviceManagement(configData) 
    
    if claim_device:
        print("Claiming device: " + claim_device)
        mac, key, type, owner, name = _splitArgs(claim_device, "-cd", "MAC key type owner name")
        dev.Claim(mac, key, type, owner, name)

    if unclaim_device:
        print("Unclaiming device: " + unclaim_device)
        dev.Unclaim(unclaim_device)

    if add_lora_sensor:
        print("Adding LoRa sensor to device: " + add_lora_sensor)
        mac, name, dev_eui, type, sample_rate = _splitArgs(add_lora_sensor, "-als", "MAC name devEui type sampleRate")
        dev.AddLoraSensor(mac, name, dev_eui, type, int(sample_rate))

    if remove_lora_sensor:  
        print("Removing LoRa sensor from device: " + remove_lora_sensor)
        mac, dev_eui = _splitArgs(remove_lora_sensor, "-rls", "MAC devEui")
        dev.RemoveLoraSensor(mac, dev_eui)

    if update_lora_sensor:  
        print("Updating LoRa sensor configuration for device: " + update_lora_sensor)
        mac, dev_eui, sample_rate = _splitArgs(update_lora_sensor, "-uls", "MAC devEui sampleRate")
        dev.UpdateLoraSensor(mac, dev_eui, int(sample_rate))

    if add_wired_sensor:
        print("Adding wired sensor to device: " + add_wired_sensor)
        mac, sensors = add_wired_sensor.split(maxsplit=1)
        try:
            sensors = json.loads(sensors)
            dev.AddWiredSensor(mac, sensors)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON for sensors: {e}")
            return

    if calibrate:
        print("Auto calibrating camera: " + calibrate)
        dev.Calibrate(calibrate)

    if manual_calibrate:
        print("Manually calibrating camera: " + manual_calibrate)
        mac, angle_x, angle_y, height = _splitArgs(manual_calibrate, "-mcal", "MAC angleX angleY height")
        dev.ManualCalibrate(mac, float(angle_x), float(angle_y), float(height))

    if get_image:
        print("Requesting IR images from camera: " + get_image)
        dev.GetImage(get_image, folderDir)

    if list_devices:
        print("Listing devices on account: " + dev.user)
        dev.ListDevices()
        
    if list_sensors:
        print("Listing sensors for device: " + list_sensors)
        dev.GetDevice(list_sensors)

    if export_all or export_device:
        deviceOrAll = export_device or export_all
        folderBase = os.path.join(folderDir, deviceOrAll)
        filePathDB = os.path.join(folderDir, deviceOrAll + ".db")
        db = Database("sqlite:///" + filePathDB.replace("\\", "/"))

        if not os.path.exists(folderBase):
            os.mkdir(folderBase)

        folderSubPath = os.path.join(folderBase, dateTimeNow)
        if not os.path.exists(folderSubPath):
            os.mkdir(folderSubPath)

        print("Using folder: " + folderSubPath)
        print("Emptying cloud queue to local database...")
        dev.EmptyQueue(Table.DATA.value, export_device, export_all, db, dead_letter, read_only)
        dev.EmptyQueue(Table.STATUS.value, export_device, export_all, db, dead_letter, read_only)

        if excel:
            print("Exporting data to Excel file...")
            filePathExcel = os.path.join(folderSubPath, deviceOrAll + "_" + dateTimeNow + ".xlsx")
            db.ExportToExcel(filePathExcel, since)

        if plot:
            print("Generating plots...")
            pathPlot = os.path.join(folderSubPath, deviceOrAll + "_" + dateTimeNow)
            exportDataFrame = db.Export(since, Table.DATA.value)
            plot = GenerateDiagram()
            plot.GeneratePlot(exportDataFrame, pathPlot)

        if mail and (excel or plot):
            print("Sending mail with excel and or plots attached...")
            mail = ElasticMailClient(configData, folderBase, dateTimeNow)
            mail.Send()
            
if __name__ == '__main__':
    try:
        plac.call(main)
    except RuntimeError as e:
        # API errors are already explained by _checkResponse, no traceback needed
        print(f"Error: {e}")
        exit(1)
    exit(0)