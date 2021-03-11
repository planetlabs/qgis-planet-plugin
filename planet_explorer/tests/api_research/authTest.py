import requests
import json
import jwt

# Setup request
URL = "https://api.planet.com/auth/v1/experimental/public/users/authenticate"
email = "someone@federal.planet.com"
password = "xxx"
data = {"email": email,
        "password": password}
headers = {'content-type': 'application/json'}

# Make request
r = requests.post(url=URL, data=json.dumps(data), headers=headers)

# Get token from request
resultJson = r.json()
token = resultJson["token"]

# Decode token
decodedJWT = jwt.decode(token, '', '')
apiKey = decodedJWT["api_key"]

# Build string for QgsApplication.authManager
authMgrString = email + "||" + password + "||" + apiKey

# QGIS CODE
# setup
# authMgr = QgsApplication.authManager()
#
# Store encrypted into `pe_plugin_auth` key
#  authMgr.storeAuthSetting("pe_plugin_auth", authMgrString, True)
#
# Retreive
# authStr = authMgr.authSetting("pe_plugin_auth", ,True)
# apiKey = authStr.split("||")[2]


print(authMgrString.split("||")[2])
