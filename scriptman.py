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
import threading
import httpx
import wget
import os
import glob

SCRIPT_CLIENT_VERSION = '0.3.0'

PI_NAME = os.uname()[1]
if '-dev-' in PI_NAME.lower():
    BASE_URL = 'https://scriptman.sagebrush.dev/scriptman_be'
else:
    BASE_URL = 'https://scriptman.sagebrush.work/scriptman_be'

logList = []

operating_system = platform.system()

def clearFiles():
    """clears all temp files, ensures nothing is re-used"""

    oldScripts = glob.glob('/tmp/script.*')

    if operating_system == "Linux":
        for path in oldScripts:
            os.remove(path)

def recentLogs(logMessage: str):
    """
    Keeps track of the previous 50 debug messages for sending to server

    Args:
        logMessage (str): the log message

    Returns:
        logList: list of log messages
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
        ['hostname',
         '-I'],
         stdout=subprocess.PIPE,
         check=True)
    ipAddress = ipAddressInfo.stdout.decode()

    return ipAddress

def run_script(script_type, script_path):
    def target():
        nonlocal process
        process = subprocess.Popen(
            [script_type, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        for line in iter(process.stdout.readline, ''):
            print(line, end='', flush=True)
            recentLogs(line.strip())

    process = None
    thread = threading.Thread(target=target)
    thread.start()

def main():
    """
    Pings server to check scripts
    and running them when updated.
    """

    clearFiles()
    loopDelayCounter = 0
    ipAddress = getIP()
    timeSinceLastConnection = 0

    while True:
        if loopDelayCounter == 5:
            ipAddress = getIP()
            loopDelayCounter = 0
        loopDelayCounter += 1

        # Build data parameters for server post request
        deviceName = os.uname()[1]
        parameters = {}
        parameters["Name"] = deviceName
        parameters["Logs"] = logList
        parameters["IP"] = ipAddress
        parameters["Version"] = SCRIPT_CLIENT_VERSION

        try:
            # Did timeout=None cuz in some cases the posts would time out.
            # Might need to change to 5 seconds if going too long causes crash.

            response = httpx.post(
                f'{BASE_URL}/clientConnect',
                json=parameters,
                timeout=5)

            # Check for status of 2XX in httpx response
            response.raise_for_status()

            status = response.json()['Tag']
            if not (status == "Do Nothing" and logList[-1]["log"]) == "Status: Do Nothing":
                recentLogs(f"Status: {status}")

            # Special case "command" keyword from scriptPath, causes device
            # to execute command script using flags included in scriptPath.

            if status == "Do Nothing":
                recentLogs("No command received")
                sleep(30)

            elif status != "Do Nothing":

                if status == "Run Script":
                    # clear all files before we download more
                    clearFiles()

                    scriptFile = response.json()['ScriptPath']
                    scriptName = response.json()['ScriptName']

                    if scriptFile.endswith('.sh'):
                        wget.download(scriptFile, out='/tmp/script.sh')
                    elif scriptFile.endswith('.py'):
                        wget.download(scriptFile, out='/tmp/script.py')

                    try:
                        if os.path.exists('/tmp/script.sh'):
                            recentLogs(f"Running script: {scriptName}")
                            run_script(script_type='usr/bin/bash', script_path='/tmp/script.sh')

                        elif os.path.exists('/tmp/script.py'):
                            recentLogs(f"Running script: {scriptName}")
                            run_script(script_type='usr/bin/python3', script_path='/tmp/script.py')

                        else:
                            recentLogs("Unknown Script Type, please check file extension.")
                    # Problems can happen. This records the errors to the logList
                    except subprocess.CalledProcessError as process_error:
                        recentLogs(str(process_error))
                    except Exception as e:
                        recentLogs(str(e))
                        print_exc()
                        sleep(5)
                    recentLogs(scriptFile)

                if status == "Reboot":
                    os.system('sudo reboot')

        except httpx.HTTPError:
            # At each failed response add 1 attempt to the tally
            # After 48 failed attempts (4 hours), reboot the pi
            timeSinceLastConnection += 1
            if timeSinceLastConnection >= 100:
                os.system('sudo reboot')
            print(f"Unable to contact Scriptman. Current tally is {timeSinceLastConnection}")
            sleep(30)
        except Exception as e:
            # General exception so that loop never crashes out, it will print it to the logs
            recentLogs('type is: ' + e.__class__.__name__)
            recentLogs(str(e))
            print_exc()
            recentLogs("Caught an error. Waiting and will try again")
            # This timeout is if server is down or has minor issue, small delay to let it sort out
            sleep(15)

main()