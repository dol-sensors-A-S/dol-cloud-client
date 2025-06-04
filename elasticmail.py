import requests
import shutil

class ElasticMailClient:
    
    def __init__(self, config, folder, datetime):
        self.apiUri = "https://api.elasticemail.com/v2"
        self.apiKey = config["elasticApiKey"]
        self.rootPath = folder + datetime + "/"
        self.attachments = []
        self.email = config["user"]
        self.subject = "Measurements report"
        self.datetime = datetime
        self.zipname = folder + datetime
        self.reply = "no-reply@dol-sensors.com"
       
    def Request(self, method, url, data, attachs=None):
        data['apikey'] = self.apiKey
        if method == 'POST':
            result = requests.post(self.apiUri + url, params = data, files = attachs)
        elif method == 'PUT':
            result = requests.put(self.apiUri + url, params = data)
        elif method == 'GET':
            attach = ''
            for key in data:
                attach = attach + key + '=' + data[key] + '&' 
            url = url + '?' + attach[:-1]
            result = requests.get(self.apiUri + url)    
            
        jsonMy = result.json()
        if 'error' in jsonMy:
            raise Exception(jsonMy['error'])

    def Send(self):
        print("Sending zip file to: " + self.email)
        
        shutil.make_archive(self.zipname, 'zip', self.rootPath)

        self.attachments.append(('attachments', open(self.zipname + ".zip", 'rb')))
            
        self.Request('POST', '/email/send', { 
                    'subject': self.subject + " - " + self.datetime,
                    'from': self.reply,
                    'fromName': self.reply,
                    'to': self.email,
                    'bodyHtml': "<p>Please find excel and graph attached attached</p><br><p>Best regards,</p><p>dol sensors</p>",
                    'bodyText': "",
                    'isTransactional': True}, self.attachments)