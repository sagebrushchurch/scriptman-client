"""
Script Client:
Sends name to server and the server returns
what script the device should be running
"""
from traceback import print_exc
from datetime import datetime
from time import sleep
import subprocess
import platform
import httpx
import wget
import os

SCRIPT_CLIENT_VERSION = '0.1.0'
BASE_URL = 'https://scriptman.sagebrush.dev/scriptman_be'
# BASE_URL = 'https://scriptman.sagebrush.work/scriptman_be'

logList = []

operating_system = platform.system()

def clearFiles():
    """clears all temp files, ensures nothing is re-used"""

    if operating_system == "Linux":
        if os.path.exists('/tmp/script.sh'):
            os.remove('/tmp/script.sh')

def recentLogs(logMessage: str):
    """
    Keeps track of the previous 50 debug messages for sending to server

    Args:
        logMessage (str): the log message

    Returns:
        list: list of log messages
    """

    if len(logList) > 50:
        logList.pop(0)
    logList.append({
        "log": logMessage,
        "timestamp": datetime.now().strftime( "%m/%d/%Y %H:%M:%S" ),
        })

    return logList

def getIP():

    ipAddressInfo = subprocess.run(
        ['hostname', '-I'], stdout=subprocess.PIPE, check=True)
    ipAddress = ipAddressInfo.stdout.decode()

    return ipAddress

def main():
    """
    Pings server to check scripts
    and running them when updated.
    """

    clearFiles()
    loopDelayCounter = 0
    ipAddress = getIP()

    while True:
        if loopDelayCounter == 5:
            ipAddress = getIP()
            loopDelayCounter = 0
        loopDelayCounter += 1

        # Build data parameters for server post request
        deviceName = os.uname()[1]
        parameters = {}
        parameters["name"] = deviceName
        parameters["Logs"] = logList
        parameters["IP"] = ipAddress
        parameters["Version"] = SCRIPT_CLIENT_VERSION

        try:
            # Did timeout=None cuz in some cases the posts would time out.
            # Might need to change to 5 seconds if going too long causes crash.

            response = httpx.post(
                f'{BASE_URL}/clientConnect', json=parameters, timeout=None)
            status = response.json()['Tag']
            recentLogs(f"Status: {status}")

            # Special case "command" keyword from scriptPath, causes device
            # to execute command script using flags included in scriptPath.

            if status == "Run script":
                commandFile = response.json()['ScriptPath']
                scriptName = response.json()['ScriptName']
                wget.download(commandFile, out='/tmp/script.sh')

                try:
                    subprocess.Popen(["/usr/bin/python3", "/tmp/script.sh"])
                    recentLogs(f"Running script: {scriptName}")

                # Problems can happen. This records the errors to the logList
                except subprocess.CalledProcessError as e:
                        recentLogs(str(e))
                recentLogs(commandFile)

            elif status == "Reboot":
                os.system('sudo reboot')

            elif status == "Do Nothing":
                recentLogs("No Command")

                # clear all files before we download more
                clearFiles()

            recentLogs("Sleeping")
            # Main loop speed control
            sleep(30)

        except Exception as e:
            # General exception so that loop never crashes out, it will print it to the logs
            recentLogs('type is: ' + e.__class__.__name__)
            recentLogs(str(e))
            print_exc()
            recentLogs("Caught an error...waiting and will try again")
            # This timeout is if server is down or has minor issue, small delay to let it sort out
            sleep(15)