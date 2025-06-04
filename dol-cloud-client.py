from enum import Enum
from turtle import title
from typing import Literal
from alive_progress import alive_bar
import json
import datetime
import pandas as pd
import plac
import sqlalchemy
import os
import matplotlib.colors as mcolors
import random
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests

from elasticmail import ElasticMailClient
     
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
                    self.token = cache.get("token", "")
                    self.tokenExpiresTime = cache.get("expireTime", 0)
                    print(f"Token loaded from cache, expires at {self.tokenExpiresTime - self.current_time } (Unix timestamp)")
        except Exception as e:
            print(f"Error loading token cache: {e}")
    
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
            return {"success": False, "error": result.text, "status_code": result.status_code}

        
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

    # get queue metadata
    def GetQueueMetaData(self, type):
        result = requests.get(self.apiURL + 'management/queue/', 
                            headers={'Authorization': 'Bearer ' + self.token} )
        
        self._checkResponse(result)
        queue = result.json()
        
        if type is Table.DATA.value:
            self.queueConn = queue['dataQueueConnection']
            self.queueName = queue['dataQueueName']
            self.queueSize = int(queue['dataQueueMessageCount'])
            self.queueDeadletterSize = int(queue['dataQueueDeadLetterCount'])
        elif type is Table.STATUS.value:
            self.queueConn = queue['statusQueueConnection']
            self.queueName = queue['statusQueueName']
            self.queueSize = int(queue['statusQueueMessageCount'])
            self.queueDeadletterSize = int(queue['statusQueueDeadLetterCount'])

    # list all devices on account    
    def ListDevices(self):
        result = requests.get(self.apiURL + 'devices?page=1&pageSize=100', 
                            headers={'Authorization': 'Bearer ' + self.token} )
        self._checkResponse(result)
        self.devices = result.json()
        
        for device in self.devices["devices"]:
            print(device)

    # get device by mac address            
    def GetDevice(self, mac):
        result = requests.get(self.apiURL + 'devices/' + mac, 
                            headers={'Authorization': 'Bearer ' + self.token} )
        device = result.json()
        self._checkResponse(result)

        print("Mac: " + device["mac"])
        print("Key: " + device["key"])
        print("Type: " + device["deviceType"])
        print("Owner: " + device["owner"])
        print("Name: " + device["deviceName"])
        print("Created: " + device["createdAt"])
        print("Updated: " + device["updatedAt"])
        print("Connected: " + device["connectionState"])
        print("Firmware: " + device["firmwareVersion"])
        print("Online: " + str(device["isOnline"]))
        print("lastActivityUtc: " + device["lastActivityUtc"])
        print("cloudToDeviceMessages: " + str(device["cloudToDeviceMessages"]))

        for loraSensor in device["sensors"]:
            print(loraSensor)
        
        for wiredSensor in device["wiredSensors"]:
            print(wiredSensor)

    # empty queue to local database based on type, device or integrator
    # if device is None, then all devices will be processed
    def EmptyQueue(self, type, device, integrator, db, deadletter=False, readonly=False):
        dataFrame = pd.DataFrame()
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
                            if device != None:
                                # if device match desired    
                                if str(dataJson['deviceId']) == str(device):
                                    dataFrame = pd.json_normalize(dataJson)
                                    db.Insert(dataFrame, type)
                                    if not readonly:
                                        receiver.complete_message(msg)
                                    foundCount += 1
                                else:
                                    receiver.abandon_message(msg)
                            elif integrator != None:
                                # if integrator match desired
                                dataFrame = pd.json_normalize(dataJson)
                                db.Insert(dataFrame, type)
                                if not readonly:
                                    receiver.complete_message(msg)
                                foundCount += 1                            
                            bar()
                            bar.text("found: " + str(foundCount) + " of " + str(queueSize) + " total messages")    
                            totalCount += 1

                    except KeyboardInterrupt:
                        pass
                
            receiver.close()
            servicebusClient.close()
            print("Found: " + str(foundCount))

class Database:
    def __init__(self, fileURL):
        self.numberInserted = ""
        self.fileURL = fileURL

    def Insert(self, df, table):
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
                    #print(f"Inserted {len(filtered_df)} rows into {table} with explicit schema")
                    
                # Regular handling for other tables
                else:
                    # Check for inactiveSensors column
                    has_inactive_sensors = 'inactiveSensors' in df.columns
                    
                    # Handle inactiveSensors if present
                    if has_inactive_sensors:
                        # Process inactiveSensors into a separate table
                        try:
                            # Prepare data for inactiveSensor table
                            inactive_records = []
                            # Process each row that had inactiveSensors
                            for i, row in df.iterrows():
                                device_id = row['deviceId']
                                timestamp = row['timestamp']
                                sensors = row['inactiveSensors']
                                
                                # Convert to list if it's a string
                                if isinstance(sensors, str):
                                    try:
                                        sensors = json.loads(sensors)
                                    except:
                                        # If not valid JSON, skip
                                        continue
                                
                                # Process each sensor in the array
                                if isinstance(sensors, list) and len(sensors) > 0:
                                    for sensor in sensors:
                                        if isinstance(sensor, dict):
                                            record = {
                                                'deviceId': device_id,
                                                'timestamp': timestamp,
                                                'name': sensor.get('name', ''),
                                                'devEui': sensor.get('devEui', ''),
                                                'lastSeenAt': sensor.get('lastSeenAt', '')
                                            }
                                            inactive_records.append(record)
                            
                            # Create DataFrame from records and insert to inactiveSensor table
                            if inactive_records:
                                inactive_df = pd.DataFrame(inactive_records)
                                inactive_count = inactive_df.to_sql('inactiveSensor', self.fileURL, 
                                                                if_exists='append', index=False)
                                
                            # Remove inactiveSensors column from main data
                            df = df.drop(columns=['inactiveSensors'])
                                
                        except Exception as e:
                            print(f"Error while processing inactiveSensors: {e}")
                    
                    # Standard table handling
                    try:
                        engine = sqlalchemy.create_engine(self.fileURL)
                        # Check if table exists
                        inspector = sqlalchemy.inspect(engine)
                        if inspector.has_table(table):
                            existing_columns = [col['name'] for col in inspector.get_columns(table)]
                            
                            # Filter DataFrame to only include columns that exist in the table
                            df_filtered = df[[col for col in df.columns if col in existing_columns]]
                            
                            if not df_filtered.empty:
                                self.numberInserted = df_filtered.to_sql(str(table), self.fileURL, 
                                                                    if_exists='append', index=False)
                            else:
                                print("No matching columns found between DataFrame and table")
                        else:
                            # Table doesn't exist, create it
                            self.numberInserted = df.to_sql(str(table), self.fileURL, 
                                                        if_exists='append', index=False)
                            print(f"Created new table {table} and inserted {len(df)} rows")
                    except Exception as col_error:
                        print(f"Error filtering columns: {col_error}")
                        # Fallback - try insert with original dataframe
                        self.numberInserted = df.to_sql(str(table), self.fileURL, 
                                                    if_exists='append', index=False)
                    
            except sqlalchemy.exc.OperationalError as e:
                print(f'Error occurred while executing a query: {e.args}')
            except Exception as general_error:
                print(f"Unexpected error: {general_error}")
        else:
            print("Skipped insert to database, since data size is 0")

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
            sensorList = filteredData['sensorId'].unique()
            for sensor in sensorList:
                filteredData = dataFrame[['deviceId', 'sensorId', 'sensorName', 'value', 'unit', 'date']]
                sensorData = filteredData[(filteredData['sensorId'] == sensor) & (filteredData['deviceId'] == device)]
                unitList = sensorData['unit'].unique()
                sensorName = sensorData['sensorName'].unique()
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
                        plt.savefig(pngPath + "-" + device + "-" + sensor + "-" + unit + ".png")
                        plt.close()

                        bar()        

class Table(Enum):
    DATA = "sensorData"
    STATUS = "sensorStatus"
    INACTIVE = "inactiveSensor"

# cli command line
@plac.annotations(
    config=('json config file e.g. -c config.json', 'option', 'c', str),
    folder=('Work output folder e.g. -f /Users/user/dir/', 'option', 'f', str),
    claim_device=('Claim device by providing its MAC address, key, type, owner and name e.g. -cd \'000ecd020000 nMNLPSNT IDOL64 Joe Gateway1\'', 'option', 'cd', str),
    unclaim_device=('Unclaim device by providing its MAC address e.g. -ud 000ecd020000', 'option', 'ud', str),
    add_lora_sensor=('Add LoRa sensor to device by providing its MAC address, name, devEui, type and sample rate e.g. -als \'000ecd020000 Sensor1 f2b3d57ed8522302 IDOL53 60\'', 'option', 'als', str),
    remove_lora_sensor=('Remove LoRa sensor from device by providing its MAC address and devEui e.g. -rls \'000ecd020000 f2b3d57ed8522302\'', 'option', 'rls', str),
    update_lora_sensor=('Update LoRa sensor configuration by providing its MAC address, devEui and sample rate e.g. -uls \'000ecd020000 f2b3d57ed8522302 60\'', 'option', 'uls', str),
    add_wired_sensor=('Add wired sensor to device by providing its MAC address and sensors e.g. -aws \'000ecd020000 [{"port":1,"wiredSensorType":"DOL139","samplingRate":60},{"port":2,"wiredSensorType":"DOL53","samplingRate":60}]\'', 'option', 'aws', str),
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
def main(config="config-qa-example.json", folder="/tmp", claim_device=None, unclaim_device=None, 
         add_lora_sensor=None, remove_lora_sensor=None, update_lora_sensor=None, 
         add_wired_sensor=None, list_devices=False, list_sensors=None, export_all=None, 
         export_device=None, dead_letter=False, read_only=False, excel=False, plot=False, 
         mail=False, since=None):
    
    if config:
        configData = json.load(open(config))

    if folder:
        folderDir = folder

    dateTimeNow = datetime.datetime.now().strftime("%d-%m-%Y_%H-%M")
    folderSub = dateTimeNow + "/"
    dev = DeviceManagement(configData) 
    
    if claim_device:
        print("Claiming device: " + claim_device)
        mac, key, type, owner, name = claim_device.split()
        dev.Claim(mac, key, type, owner, name)

    if unclaim_device:
        print("Unclaiming device: " + unclaim_device)
        dev.Unclaim(unclaim_device)

    if add_lora_sensor:
        print("Adding LoRa sensor to device: " + add_lora_sensor)
        mac, name, dev_eui, type, sample_rate = add_lora_sensor.split()
        dev.AddLoraSensor(mac, name, dev_eui, type, int(sample_rate))

    if remove_lora_sensor:  
        print("Removing LoRa sensor from device: " + remove_lora_sensor)
        mac, dev_eui = remove_lora_sensor.split()
        dev.RemoveLoraSensor(mac, dev_eui)

    if update_lora_sensor:  
        print("Updating LoRa sensor configuration for device: " + update_lora_sensor)
        mac, dev_eui, sample_rate = update_lora_sensor.split()
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

    if list_devices:
        print("Listing devices on account: " + dev.user)
        dev.ListDevices()
        
    if list_sensors:
        print("Listing sensors for device: " + list_sensors)
        dev.GetDevice(list_sensors)

    if export_all or export_device:
        folderBase = folderDir + "/" + (export_device or export_all) + "/"
        filePathDB = folderDir + "/" + (export_device or export_all) + ".db"
        db = Database("sqlite:////" + filePathDB)

        if not os.path.exists(folderBase):
            os.mkdir(folderBase)

        if not os.path.exists(folderBase + folderSub):
            os.mkdir(folderBase + folderSub)

        print("Using folder: " + folderBase + folderSub)
        print("Emptying cloud queue to local database...")
        dev.EmptyQueue(Table.DATA.value, export_device, export_all, db, dead_letter, read_only)
        dev.EmptyQueue(Table.STATUS.value, export_device, export_all, db, dead_letter, read_only)
        
        if excel:
            print("Exporting data to Excel file...")
            filePathExcel = folderBase + folderSub + (export_device or export_all) + "_" + dateTimeNow + ".xlsx"
            db.ExportToExcel(filePathExcel, since)

        if plot:
            print("Generating plots...")
            pathPlot = folderBase + folderSub + (export_device or export_all) + "_" + dateTimeNow
            exportDataFrame = db.Export(since, Table.DATA.value)
            plot = GenerateDiagram()
            plot.GeneratePlot(exportDataFrame, pathPlot)    

        if mail and (excel or plot):
            print("Sending mail with excel and or plots attached...")
            mail = ElasticMailClient(configData, folderBase, dateTimeNow)
            mail.Send()
            
if __name__ == '__main__':
    plac.call(main)
    exit(0)