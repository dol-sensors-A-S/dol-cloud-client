# README #

### Python Libraries Required ###

* **alive-progress** - For progress bars during data processing
  - Install: `pip install alive-progress>=2.4.1`

* **requests** - For REST API communication
  - Install: `pip install requests>=2.28.0`

* **pandas** - For data manipulation and analysis
  - Install: `pip install pandas>=1.5.3`

* **azure-servicebus** - For cloud queue operations
  - Install: `pip install azure-servicebus>=7.11.1`
  - Documentation: https://learn.microsoft.com/en-us/python/api/overview/azure/servicebus-readme

* **matplotlib** - For generating plots and charts
  - Install: `pip install matplotlib>=3.7.1`

* **SQLAlchemy** - For database operations
  - Install: `pip install sqlalchemy>=2.0.0`

* **xlsxwriter** - For Excel file generation
  - Install: `pip install xlsxwriter>=3.1.0`

* **plac** - For command line argument parsing
  - Install: `pip install plac>=1.3.5`

* **ElasticEmail** - For sending email notifications
  - Install: `pip install git+https://github.com/elasticemail/elasticemail-python.git@4.0.23`

* **json**, **sys**, **datetime**, **os**, **shutil**, **random** - Standard library modules (no installation required)

### One-line Installation ###

```bash
pip install alive-progress requests pandas azure-servicebus matplotlib sqlalchemy xlsxwriter plac git+https://github.com/elasticemail/elasticemail-python.git@4.0.23
```

### Getting started ###

Your login must be attached to an integrator account (done by a dol-sensors employee).
The MAC address and key are printed on the label of the gateway / camera, the devEui on the label of the sensor.
All commands that change a device require it to be online.

Options that take several values (`-cd`, `-als`, `-uls`, `-rls`, `-mcal`) are given as one string, split on spaces.
To use a name or owner **with spaces**, put it in double quotes inside the single-quoted string,
e.g. `-als '000ecd020000 "Pen 3 outside" f2b3d57ed8522302 DOL53 600'`.

**Windows** (cmd / PowerShell):
* Use `python` (or `py`) instead of `python3`.
* Swap the quotes: `-als "000ecd020000 'Pen 3 outside' f2b3d57ed8522302 DOL53 600"`.
* For `-aws` the JSON keeps its double quotes. In **cmd** escape them with `\`:

  ```bat
  python dol-cloud-client.py -c config-prod.json -aws "000ecd020000 [{\"port\":1,\"wiredSensorType\":\"DOL139\",\"samplingRate\":60}]"
  ```

  In **PowerShell 7.3+** use single quotes as on macOS/Linux:
  `-aws '000ecd020000 [{"port":1,"wiredSensorType":"DOL139","samplingRate":60}]'`
  (older Windows PowerShell 5.1 strips the inner quotes; use cmd for `-aws` there).
* Paths use backslashes as normal, e.g. `-f C:\Users\joe\work`.

**1. Create a config file**

Copy `config-qa-example.json` to `config-qa.json` (test) or `config-prod-example.json` to `config-prod.json`
(production) and fill in your login. These two file names are ignored by git, so your password is not committed.

```json
{
    "user": "you@company.com",
    "pwd": "your-password",
    "url": "https://iot.dol-sensors.com/api/",
    "elasticApiKey": "only needed for -m (mail)"
}
```

**2. Check the login and list your devices**

```bash
python3 dol-cloud-client.py -c config-prod.json -ld
```

**3a. IDOL64 gateway: claim it and add sensors**

```bash
# claim: MAC key type owner name
python3 dol-cloud-client.py -c config-prod.json -cd '000ecd020000 nMNLPSNT IDOL64 "Joe Farm" "Gateway 1"'

# add a LoRa sensor: MAC name devEui type sampleRate(seconds)
python3 dol-cloud-client.py -c config-prod.json -als '000ecd020000 "Pen 3 outside" f2b3d57ed8522302 DOL53 600'

# change its sample rate: MAC devEui sampleRate
python3 dol-cloud-client.py -c config-prod.json -uls '000ecd020000 f2b3d57ed8522302 300'

# configure wired sensors on port 1-4 (replaces the current wired configuration)
python3 dol-cloud-client.py -c config-prod.json -aws '000ecd020000 [{"port":1,"wiredSensorType":"DOL139","samplingRate":60}]'

# verify the gateway and its sensors
python3 dol-cloud-client.py -c config-prod.json -ls 000ecd020000
```

**3b. IDOL65 camera: claim it and calibrate**

```bash
# claim: MAC key type owner name
python3 dol-cloud-client.py -c config-prod.json -cd 'ddeecdff015f AbCdEfGh IDOL65 "Joe Farm" "Camera pen 1"'

# auto calibrate (recommended)
python3 dol-cloud-client.py -c config-prod.json -cal ddeecdff015f

# or manual calibration if auto fails: MAC angleX(-4..4) angleY(-4..4) height(mm, 2000..2500)
python3 dol-cloud-client.py -c config-prod.json -mcal 'ddeecdff015f 0 0 2300'

# check camera status (dirty, calibration status, messages)
python3 dol-cloud-client.py -c config-prod.json -ls ddeecdff015f

# save a pair of IR images to check the camera view
python3 dol-cloud-client.py -c config-prod.json -gi ddeecdff015f -f ./images
```

See [IDOL65 camera calibration](#idol65-camera-calibration) for how to follow the calibration result.

**4. Read the data**

Measurements and status changes are not available in the API, they are delivered to your queues.
Empty the queues to a local SQLite database and export it:

```bash
# one device, export to Excel and plots in ./export
python3 dol-cloud-client.py -c config-prod.json -ed 000ecd020000 -f ./export -e -p

# all devices on the integrator, named "Joe" in the output folder
python3 dol-cloud-client.py -c config-prod.json -ea Joe -f ./export -e

# peek without removing messages (each read counts, after 3 they go to the deadletter queue)
python3 dol-cloud-client.py -c config-prod.json -ed 000ecd020000 -ro

# read the deadletter queue
python3 dol-cloud-client.py -c config-prod.json -ed 000ecd020000 -dl -e
```

**Remove a sensor or a device**

```bash
python3 dol-cloud-client.py -c config-prod.json -rls '000ecd020000 f2b3d57ed8522302'
python3 dol-cloud-client.py -c config-prod.json -ud 000ecd020000   # unclaim, resets the configuration
```

### data-export ###
* Connect to cloud API with login credentials from config.json 
* List devices and sensors from integrator accounts
* Empty cloud queue based on device MAC address or integrator name
* Save data to SQLite database (append if exists)
* Automatically handle inactiveSensors data in a separate table
* Export all database tables to a single Excel file
* Plot sensor data from database with automatic unit detection
* Zip Excel files and plots and send via email
* Filter data by date using the --since parameter


### Features ###

* **Database Management**
  - SQLite database with automatic schema handling
  - Proper handling of inactiveSensors data in a separate table
  - Dynamic table creation with appropriate column types
  - Adds new columns to existing tables when messages bring new fields (sensorData keeps its fixed schema)
  - Export all tables to different sheets in a single Excel file

* **Plotting**
  - Generate time-series plots for each sensor/device/unit combination
  - Automatic color assignment for different sensors
  - Auto-formatted date and time axes
  - Proper handling of units in axis labels

* **Excel Export**
  - All database tables exported to a single Excel file
  - Auto-sized columns for better readability
  - Data from each table placed in separate sheets
  - Timestamp conversion to human-readable dates

* **Improved Error Handling**
  - Better error messages for database operations
  - Graceful handling of schema mismatches
  - Recovery mechanisms for database errors

### Python libraries used ###

* alive_progress - For progress bars during data processing
* json - For config file parsing and JSON data handling
* requests - For REST API communication
* datetime - For timestamp handling
* pandas - For data manipulation and analysis
* azure.servicebus - For cloud queue operations
* matplotlib - For generating plots and charts
* sqlalchemy - For database operations
* xlsxwriter - For Excel file generation
* plac - For command line argument parsing
* os, shutil - For file and directory operations

### Database Tables ###

* **sensorData** - Contains all sensor measurements with explicit schema:
  - id (TEXT)
  - deviceId (TEXT)
  - sensorId (TEXT)
  - sensorName (TEXT)
  - value (FLOAT)
  - type (TEXT)
  - unit (TEXT)
  - timestamp (BIGINT)

* **sensorStatus** - Contains device status information

* **inactiveSensor** - Contains information about inactive sensors from status messages

* **visionStatus** - IDOL65 camera status from `VisionStatus` status messages, one row per message:
  deviceId, timestamp, isDirty, isDetectingDirty, isDeviceManuallyCalibrated, calibration (Required/Started/Done),
  calibrationLastUpdate, lastWeightCacheClearCount, lastWeightCacheClearedUpdate

* **visionMessage** - The `messages` list of each VisionStatus message (e.g. "In-pen calibration successful"):
  deviceId, timestamp, messageId, messageText, messagePayload

  A VisionStatus message only contains the fields that changed, so most columns in a visionStatus row are empty.
  A failed calibration typically arrives as two messages, one second apart:

  ```json
  {"deviceId":"000ecdff0427","visionStatus":{"calibrationLastUpdate":"2025-01-31T08:13:55Z","messages":[{"messageId":2,"messageText":"Max image has too few pixels withing distance limits.","messagePayload":""}]},"timestamp":1738311235}
  {"deviceId":"000ecdff0427","visionStatus":{"calibration":"Required","messages":[]},"timestamp":1738311236}
  ```

  and a successful one as `"In-pen calibration successful "` followed by `"calibration":"Done"`.
  Dirty lens: `{"deviceId":"000ecdff0422","visionStatus":{"isDirty":"Very Dirty","messages":[]},"timestamp":1744835030}`.

* **visionStatusLatest** (Excel sheet only) - Current state per camera: the last known value of every visionStatus
  field, plus the last message (lastMessageId, lastMessageText, lastMessageDate). Built from all history, also with `-s`.

* **weightStatistics** - IDOL65 weight statistics from the data queue, join with sensorData on `id`:
  id, deviceId, sensorId, timestamp, count, countDelta, minWeight, maxWeight, timespan, sd, skewness, withinSpec

  Example IDOL65 data message (`value` is the mean weight, stored in sensorData; the rest in weightStatistics):

  ```json
  {"id":"ebf49df6-2773-4f0c-8196-2600375fc919","deviceId":"000ecdff0564","sensorId":"000ecdff0564_Camera01_kg",
   "sensorName":"Camera01","value":24.75,"type":"Weight","unit":"kg","timestamp":1765152060,"withinSpec":true,
   "count":17215,"minWeight":16.26,"maxWeight":33.25,"timespan":3600,"sd":4.25,"countDelta":391}
  ```

  Mean weight with its statistics:

  ```sql
  SELECT d.deviceId, d.sensorName, d.value AS meanWeight, w.minWeight, w.maxWeight, w.sd, w.count, w.withinSpec,
         DATETIME(d.timestamp, 'unixepoch') AS date
  FROM sensorData d JOIN weightStatistics w ON w.id = d.id
  ORDER BY d.timestamp;
  ```

* **batteryUpdate** - Sensor battery changes from `SensorBatteryUpdates` status messages:
  deviceId, timestamp, devEui, code, batteryStatus

Status messages with any other subject go to **sensorStatus** with a `subject` column. A message is only
removed from the queue after it was stored; if the insert fails it is abandoned and stays in the queue.

### IDOL65 camera calibration ###

Auto calibration is recommended; use manual calibration only when auto calibration fails.

```bash
python3 dol-cloud-client.py -c config-prod.json -cal 000ecd020000                 # auto calibrate
python3 dol-cloud-client.py -c config-prod.json -mcal '000ecd020000 0 0 2300'    # angleX angleY height(mm)
python3 dol-cloud-client.py -c config-prod.json -ls 000ecd020000                  # current cameraStatus
python3 dol-cloud-client.py -c config-prod.json -gi 000ecd020000 -f ./images      # save IR image pair
```

The calibrate call only sends the command to the camera. The progress (Started -> Done) and the camera
messages arrive later on the status queue, so empty the queue after a few minutes to read them:

```bash
python3 dol-cloud-client.py -c config-prod.json -ed 000ecd020000 -e
```

and look at the `visionStatus` and `visionMessage` sheets / tables.

### Command line options ###

```bash
usage: dol-cloud-client.py [-h] [-c config-qa-example.json] [-f /tmp] [-cd None] [-ud None] [-als None] [-rls None] [-uls None] [-aws None] [-cal None] [-mcal None] [-gi None] [-ld] [-ls None] [-ea None] [-ed None] [-dl] [-ro] [-e] [-p] [-m] [-s None]

options:
  -h, --help            show this help message and exit
  -c config-qa-example.json, --config config-qa-example.json
                        json config file e.g. -c config.json
  -f /tmp, --folder /tmp
                        Work output folder e.g. -f /Users/user/dir/
  -cd None, --claim-device None
                        Claim device by providing its MAC address, key, type, owner and name e.g. -cd '000ecd020000 nMNLPSNT IDOL64 Joe Gateway1'
  -ud None, --unclaim-device None
                        Unclaim device by providing its MAC address e.g. -ud 000ecd020000
  -als None, --add-lora-sensor None
                        Add LoRa sensor to device by providing its MAC address, name, devEui, type and sample rate e.g. -als '000ecd020000 Sensor1 f2b3d57ed8522302 IDOL53 60'
  -rls None, --remove-lora-sensor None
                        Remove LoRa sensor from device by providing its MAC address and devEui e.g. -rls '000ecd020000 f2b3d57ed8522302'
  -uls None, --update-lora-sensor None
                        Update LoRa sensor configuration by providing its MAC address, devEui and sample rate e.g. -uls '000ecd020000 f2b3d57ed8522302 60'
  -aws None, --add-wired-sensor None
                        Add wired sensor to device by providing its MAC address and sensors e.g. -aws '000ecd020000 [{"port":1,"wiredSensorType":"DOL139","samplingRate":60},{"port":2,"wiredSensorType":"DOL53","samplingRate":60}]'
  -cal None, --calibrate None
                        Auto calibrate IDOL65 camera by providing its MAC address e.g. -cal 000ecd020000
  -mcal None, --manual-calibrate None
                        Manually calibrate IDOL65 camera by providing its MAC address, angleX (-4..4), angleY (-4..4) and height in mm (2000..2500) e.g. -mcal '000ecd020000 0 0 2300'
  -gi None, --get-image None
                        Request a pair of IR images from IDOL65 camera, saved in work folder e.g. -gi 000ecd020000
  -ld, --list-devices   list all gateways on account e.g. -ld
  -ls None, --list-sensors None
                        list all sensors for a device by providing its MAC address e.g. -ls 000ecd020000
  -ea None, --export-all None
                        Export all by given name -ea Joe
  -ed None, --export-device None
                        Export by device MAC address to use e.g -ed 000ecd020000
  -dl, --dead-letter    Select cloud deadletter queue instead of regular e.g. -dl
  -ro, --read-only      Only read the queue (max 3 times, then queue go to deadletter) e.g. -ro
  -e, --excel           export db to excel i.e. -e
  -p, --plot            generate plot from excel i.e. -p
  -m, --mail            send mail with excel and plots. Require -e and/or -p e.g. -e -p -m
  -s None, --since None
                        Date in YYYY-MM-DD format
```


