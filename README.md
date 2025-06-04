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

### Command line usage ###
`python3 data-export.py --config config.json --output /path/to/output`
`python3 data-export.py --device 000ecd020000 --queue --excel --plot --mail`

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
  - Filters DataFrame columns to match existing tables
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

### Command line options ###

```bash
usage: dol-cloud-client.py [-h] [-c config-qa-example.json] [-f /tmp] [-cd None] [-ud None] [-als None] [-rls None] [-uls None] [-aws None] [-ld] [-ls None] [-ea None] [-ed None] [-dl] [-ro] [-e] [-p] [-m] [-s None]

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


