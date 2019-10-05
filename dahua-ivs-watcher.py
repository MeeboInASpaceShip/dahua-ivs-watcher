#!/usr/bin/python3 -u
# -*- coding: utf-8 -*-
import logging
import socket
import pycurl
import time
import shlex
import subprocess
import requests
import json

# The minimum amount of seconds that has to pass between an EVENT END and new
# EVENT START
ALARM_DELAY = 90

URL_TEMPLATE = "http://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&codes=%5B{events}%5D"

CAMERAS = [
        {
                "host": "aaa.bbb.ccc.ddd",
                "port": 80,
                "user": "admin",
                "pass": "PASSWORD",
# There may be more events than these, not sure
#		"events": "VideoMotion,CrossLineDetection,CrossRegionDetection,LeftDetection,SceneChange,TakenAwayDetection,FaceDetection,RioterDetection,MoveDetection,WanderDetection,CrossFenceDetection,ParkingDetection,NumberStat,RetrogradeDetection,TrafficJunction"
# CrossLineDetection = Tripwire
# CrossRegionDetection = Intrusion [Box]
                "events": "CrossLineDetection,CrossRegionDetection"
        }
]

class DahuaCamera():
        def __init__(self, master, index, camera):
                self.Master = master
                self.Index = index
                self.Camera = camera
                self.CurlObj = None
                self.Connected = None
                self.Reconnect = None

                self.Alarm = dict({
                        "Active": None,
                        "Last": None
                })

        def OnAlarm(self, State):
                print("--- [{0}] IVS Event Trigger {1}".format(self.Index, "START" if State else "END"))

                if State:
                    synoresponse = requests.get(
                            # This part might need to be configured for your
                            # environment in Surveillance Station under
                            # Action Rules with an External Event trigger
                            'https://aaa.bbb.ccc.ddd:5001/webapi/entry.cgi',
                            params={
                                'api': 'SYNO.SurveillanceStation.ExternalEvent',        
                                'method': 'Trigger',
                                'version': '1',
                                'eventId': '1',
                                'eventName': 'Dahua IPC: CrossLineDetection',
                                'account': 'A-SURVEILLANCE-STATION-ACCOUNT',
                                'password': 'ACCOUNT-PASSWORD',
                                },
                            # If you connect through https, the Synology
                            # certificate needs to be verified by OpenSSL
                            # Download this in DSM under Control Panel > 
                            # Security > Certificate > Export certificate
                            verify='/usr/local/share/ca-certificates/syno-ca-cert.pem',
                            )
                    print("[{0}] Surveillance Station API response was: {1}".format(self.Index, synoresponse.text))

                    # Send event push notification via Pushover
                    # 
                    # CHANGE CODE TO USE requests.get()
                    #pushresponse = http.request(
                    #        'POST',
                    #        'https://api.pushover.net/1/messages.json',
                    #        fields={
                    #            'token': 'TOKEN',
                    #            'user': 'USER',
                    #            'message': 'Dahua HDW1230S: CrossLineDetection',
                    #            }
                    #        )
#
#                    print("[{0}] Pushover API response was: {1}".format(self.Index, pushresponse.data))

        def OnConnect(self):
                print("[{0}] OnConnect()".format(self.Index))
                self.Connected = True

        def OnDisconnect(self, reason):
                print("[{0}] OnDisconnect({1})".format(self.Index, reason))
                self.Connected = False

        def OnTimer(self):
                if self.Alarm["Active"] == False and time.time() - self.Alarm["Last"] > ALARM_DELAY:
                        self.Alarm["Active"] = None
                        self.Alarm["Last"] = None

                        self.OnAlarm(False)

        def OnReceive(self, data):
                Data = data.decode("utf-8", errors="ignore")
                # HTTP header output
                #print("[{0}]: {1}".format(self.Index, Data))

                for Line in Data.split("\r\n"):
                        if Line == "HTTP/1.1 200 OK":
                                self.OnConnect()

                        if not Line.startswith("Code="):
                                continue

                        Alarm = dict()
                        for KeyValue in Line.split(';'):
                                Key, Value = KeyValue.split('=')
                                Alarm[Key] = Value

                        self.ParseAlarm(Alarm)

        def ParseAlarm(self, Alarm):
                print("[{0}] ParseAlarm({1})".format(self.Index, Alarm))

                if Alarm["Code"] not in self.Camera["events"].split(','):
                        return

                if Alarm["action"] == "Start":
                        if self.Alarm["Active"] == None:
                                self.OnAlarm(True)
                        self.Alarm["Active"] = True
                elif Alarm["action"] == "Stop":
                        self.Alarm["Active"] = False
                        self.Alarm["Last"] = time.time()


class DahuaMaster():
        def __init__(self):
                self.Cameras = []

                self.CurlMultiObj = pycurl.CurlMulti()
                self.NumCurlObjs = 0

                for Index, Camera in enumerate(CAMERAS):
                        DahuaCam = DahuaCamera(self, Index, Camera)
                        self.Cameras.append(DahuaCam)
                        Url = URL_TEMPLATE.format(**Camera)

                        CurlObj = pycurl.Curl()
                        DahuaCam.CurlObj = CurlObj

                        CurlObj.setopt(pycurl.URL, Url)
                        CurlObj.setopt(pycurl.CONNECTTIMEOUT, 30)
                        CurlObj.setopt(pycurl.TCP_KEEPALIVE, 1)
                        CurlObj.setopt(pycurl.TCP_KEEPIDLE, 30)
                        CurlObj.setopt(pycurl.TCP_KEEPINTVL, 15)
                        CurlObj.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_DIGEST)
                        CurlObj.setopt(pycurl.USERPWD, "%s:%s" % (Camera["user"], Camera["pass"]))
                        CurlObj.setopt(pycurl.WRITEFUNCTION, DahuaCam.OnReceive)

                        self.CurlMultiObj.add_handle(CurlObj)
                        self.NumCurlObjs += 1

        def OnTimer(self):
                for Camera in self.Cameras:
                        Camera.OnTimer()

        def Run(self, timeout = 1.0):
                while 1:
                        Ret, NumHandles = self.CurlMultiObj.perform()
                        if Ret != pycurl.E_CALL_MULTI_PERFORM:
                                break

                while 1:
                        Ret = self.CurlMultiObj.select(timeout)
                        if Ret == -1:
                                self.OnTimer()
                                continue

                        while 1:
                                Ret, NumHandles = self.CurlMultiObj.perform()

                                if NumHandles != self.NumCurlObjs:
                                        _, Success, Error = self.CurlMultiObj.info_read()

                                        for CurlObj in Success:
                                                Camera = next(filter(lambda x: x.CurlObj == CurlObj, self.Cameras))
                                                if Camera.Reconnect:
                                                        continue

                                                Camera.OnDisconnect("Success")
                                                Camera.Reconnect = time.time() + 5

                                        for CurlObj, ErrorNo, ErrorStr in Error:
                                                Camera = next(filter(lambda x: x.CurlObj == CurlObj, self.Cameras))
                                                if Camera.Reconnect:
                                                        continue

                                                Camera.OnDisconnect("{0} ({1})".format(ErrorStr, ErrorNo))
                                                Camera.Reconnect = time.time() + 5

                                        for Camera in self.Cameras:
                                                if Camera.Reconnect and Camera.Reconnect < time.time():
                                                        self.CurlMultiObj.remove_handle(Camera.CurlObj)
                                                        self.CurlMultiObj.add_handle(Camera.CurlObj)
                                                        Camera.Reconnect = None

                                if Ret != pycurl.E_CALL_MULTI_PERFORM:
                                        break

                        self.OnTimer()

if __name__ == '__main__':
        # Enable debug logging
        #logging.basicConfig(level=logging.DEBUG)

        Master = DahuaMaster()
        Master.Run()
