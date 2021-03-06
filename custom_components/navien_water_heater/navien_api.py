""" 
This module makes it possible to interact with Navien tankless water heater, 
combi-boiler or boiler connected via NaviLink.

Please refer to the documentation provided in the README.md,
which can be found at https://github.com/rudybrian/PyNavienSmartControl/

This is a modified version that uses async for easier integration with hass

"""

import aiohttp
import asyncio
import struct
import collections
import enum
import json
import logging 
from datetime import datetime
_LOGGER = logging.getLogger(__name__)

class ControlType(enum.Enum):
    UNKNOWN = 0
    CHANNEL_INFORMATION = 1
    STATE = 2
    TREND_SAMPLE = 3
    TREND_MONTH = 4
    TREND_YEAR = 5
    ERROR_CODE = 6


class ChannelUse(enum.Enum):
    UNKNOWN = 0
    CHANNEL_1_USE = 1
    CHANNEL_2_USE = 2
    CHANNEL_1_2_USE = 3
    CHANNEL_3_USE = 4
    CHANNEL_1_3_USE = 5
    CHANNEL_2_3_USE = 6
    CHANNEL_1_2_3_USE = 7


class DeviceSorting(enum.Enum):
    NO_DEVICE = 0
    NPE = 1
    NCB = 2
    NHB = 3
    CAS_NPE = 4
    CAS_NHB = 5
    NFB = 6
    CAS_NFB = 7
    NFC = 8
    NPN = 9
    CAS_NPN = 10
    NPE2 = 11
    CAS_NPE2 = 12
    NCB_H = 13
    NVW = 14
    CAS_NVW = 15


class TemperatureType(enum.Enum):
    UNKNOWN = 0
    CELSIUS = 1
    FAHRENHEIT = 2


class OnDemandFlag(enum.Enum):
    UNKNOWN = 0
    ON = 1
    OFF = 2
    WARMUP = 3


class HeatingControl(enum.Enum):
    UNKNOWN = 0
    SUPPLY = 1
    RETURN = 2
    OUTSIDE_CONTROL = 3


class WWSDFlag(enum.Enum):
    OK = False
    FAIL = True


class WWSDMask(enum.Enum):
    WWSDFLAG = 0x01
    COMMERCIAL_LOCK = 0x02
    HOTWATER_POSSIBILITY = 0x04
    RECIRCULATION_POSSIBILITY = 0x08


class CommercialLockFlag(enum.Enum):
    OK = False
    LOCK = True


class NFBWaterFlag(enum.Enum):
    OFF = False
    ON = True


class RecirculationFlag(enum.Enum):
    OFF = False
    ON = True


class HighTemperature(enum.Enum):
    TEMPERATURE_60 = 0
    TEMPERATURE_83 = 1


class OnOFFFlag(enum.Enum):
    UNKNOWN = 0
    ON = 1
    OFF = 2


class DayOfWeek(enum.Enum):
    UN_KNOWN = 0
    SUN = 1
    MON = 2
    TUE = 3
    WED = 4
    THU = 5
    FRI = 6
    SAT = 7


class ControlSorting(enum.Enum):
    INFO = 1
    CONTROL = 2


class DeviceControl(enum.Enum):
    POWER = 1
    HEAT = 2
    WATER_TEMPERATURE = 3
    HEATING_WATER_TEMPERATURE = 4
    ON_DEMAND = 5
    WEEKLY = 6
    RECIRCULATION_TEMPERATURE = 7


class AutoVivification(dict):
    """Implementation of perl's autovivification feature."""

    def __getitem__(self, item):
        try:
            return dict.__getitem__(self, item)
        except KeyError:
            value = self[item] = type(self)()
            return value

class NavienAccountInfo:

    # The Navien server.
    navienWebServer = "https://uscv2.naviensmartcontrol.com"

    def __init__(self, userID, passwd):
        """
        Construct a new 'NavienSmartControl' object.

        :param userID: The user ID used to log in to the mobile application
        :param passwd: The corresponding user's password
        :return: returns nothing
        """
        self.userID = userID
        self.passwd = passwd

    async def login(self):
        """
        Login to the REST API
        
        :return: The REST API response
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(NavienAccountInfo.navienWebServer + "/api/requestDeviceList", json={"userID": self.userID, "password": self.passwd}) as response:
                # If an error occurs this will raise it, otherwise it returns the gateway list.
                return await self.handleResponse(response)

    async def handleResponse(self, response):
        """
        HTTP response handler

        :param response: The response returned by the REST API request
        :return: The gateway list JSON in dictionary form
        """
        # We need to check for the HTTP response code before attempting to parse the data
        if response.status != 200:
            raise Exception("Login error, please try again")

        response_data = await response.json()

        try:
            response_data["data"]
            gateway_data = json.loads(response_data["data"])
        except NameError:
            raise Exception("Error: Unexpected JSON response to gateway list request.")

        return gateway_data
    

class NavienSmartControl:
    """The main NavienSmartControl class"""

    # The Navien TCP server.
    navienTcpServer = "uscv2.naviensmartcontrol.com"
    navienTcpServerSocketPort = 6001

    def __init__(self, userID, gatewayID):
        """
        Construct a new 'NavienSmartControl' object.

        :param userID: The user ID used to log in to the mobile application
        :return: returns nothing
        """
        self.userID = userID
        self.gatewayID = gatewayID
        self.reader = None
        self.writer = None
        self.connecting = False
        self.logged_in = False
        self.last_connect = None
        self.channelInfo= {}
        self.last_state = {}
        self.queue = asyncio.Queue(maxsize=1)

    async def connect(self):
        """
        Connect to the binary API service
        
        :return: The response data (normally a channel information response)
        """
        self.connecting = True
        while self.connecting:
            try:
                self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(NavienSmartControl.navienTcpServer, NavienSmartControl.navienTcpServerSocketPort),timeout=5)
                self.connecting = False
            except Exception as e:
                _LOGGER.error(str(type(e).__name__) + ": " + str(e) + " This error occurred while attempting to reconnect to Navien server")

        try:
            channelInfo = await self.send_and_receive((self.userID + "$" + "iPhone1.0" + "$" + self.gatewayID).encode())
            if channelInfo.get('channel') is not None:
                self.channelInfo = channelInfo
                self.logged_in = True
                self.last_connect = datetime.now() 
        except Exception as e:
            _LOGGER.error(str(type(e).__name__) + ": " + str(e))
        finally:
            return self.channelInfo

    async def disconnect(self):
        """
        Disconnect the from the API
        """
        try:
            if not self.writer.is_closing():
                self.writer.close()
            await self.writer.wait_closed()
        except Exception as e:
            _LOGGER.error(str(type(e).__name__) + ": " + str(e))
        finally:
            self.logged_in = False
            self.writer = None
            self.reader = None
            return True

    async def send_and_receive(self,data, read_response = True):
        """Attempt to send request and receive response from Navien TCP server"""
        await self.queue.put("data received")
        received_data = None
        try:
            self.writer.write(data)
            await self.writer.drain()
            if read_response:
                received_data = await asyncio.wait_for(self.reader.read(1024),5)
        except ConnectionResetError as e:
            _LOGGER.error("Connection reset by Navien server, reconnecting...")
            self.logged_in = False
            self.writer = None
            self.reader = None
        except Exception as e:
            _LOGGER.error(str(type(e).__name__) + ": " + str(e))
        finally:
            await self.queue.get()
            return self.parseResponse(received_data)        



    def parseResponse(self, data):
        """
        Main handler for handling responses from the binary protocol.
        This function passes on the response data to the appopriate response-specific parsing function.

        :param data: Data received from a response
        :return: The parsed response data from the corresponding response-specific parser.
        """
        # The response is returned with a fixed header for the first 12 bytes
        if data is not None:
            if len(data) > 12:
                commonResponseColumns = collections.namedtuple(
                    "response",
                    [
                        "deviceID",
                        "countryCD",
                        "controlType",
                        "swVersionMajor",
                        "swVersionMinor",
                    ],
                )
                commonResponseData = commonResponseColumns._make(
                    struct.unpack("8s B B B B", data[:12])
                )
                # Based on the controlType, parse the response accordingly
                if commonResponseData.controlType == ControlType.CHANNEL_INFORMATION.value:
                    retval = self.parseChannelInformationResponse(commonResponseData, data)
                elif commonResponseData.controlType == ControlType.STATE.value:
                    retval = self.parseStateResponse(commonResponseData, data)
                else:
                    retval = None
            else:
                retval = None
        else:
            retval = None

        return retval

    def parseChannelInformationResponse(self, commonResponseData, data):
        """
        Parse channel information response
        
        :param commonResponseData: The common response data from the response header
        :param data: The full channel information response data
        :return: The parsed channel information response data
        """
        # This tells us which serial channels are in use
        try:
            chanUse = data[12]
            fwVersion = int(
                commonResponseData.swVersionMajor * 100 + commonResponseData.swVersionMinor
            )
            channelResponseData = {}
            if fwVersion > 1500:
                chanOffset = 15
            else:
                chanOffset = 13

            if chanUse != ChannelUse.UNKNOWN.value:
                if fwVersion < 1500:
                    channelResponseColumns = collections.namedtuple(
                        "response",
                        [
                            "channel",
                            "deviceSorting",
                            "deviceCount",
                            "deviceTempFlag",
                            "minimumSettingWaterTemperature",
                            "maximumSettingWaterTemperature",
                            "heatingMinimumSettingWaterTemperature",
                            "heatingMaximumSettingWaterTemperature",
                            "useOnDemand",
                            "heatingControl",
                            "wwsdFlag",
                            "highTemperature",
                            "useWarmWater",
                        ],
                    )
                    for x in range(3):
                        tmpChannelResponseData = channelResponseColumns._make(
                            struct.unpack(
                                "B B B B B B B B B B B B B",
                                data[
                                    (13 + chanOffset * x) : (13 + chanOffset * x)
                                    + chanOffset
                                ],
                            )
                        )
                        channelResponseData[str(x + 1)] = tmpChannelResponseData._asdict()
                        channelResponseData[str(x + 1)]["useOnDemand"] = OnDemandFlag(channelResponseData[str(x + 1)]["useOnDemand"]).value == 1
                else:
                    channelResponseColumns = collections.namedtuple(
                        "response",
                        [
                            "channel",
                            "deviceSorting",
                            "deviceCount",
                            "deviceTempFlag",
                            "minimumSettingWaterTemperature",
                            "maximumSettingWaterTemperature",
                            "heatingMinimumSettingWaterTemperature",
                            "heatingMaximumSettingWaterTemperature",
                            "useOnDemand",
                            "heatingControl",
                            "wwsdFlag",
                            "highTemperature",
                            "useWarmWater",
                            "minimumSettingRecirculationTemperature",
                            "maximumSettingRecirculationTemperature",
                        ],
                    )
                    for x in range(3):
                        tmpChannelResponseData = channelResponseColumns._make(
                            struct.unpack(
                                "B B B B B B B B B B B B B B B",
                                data[
                                    (13 + chanOffset * x) : (13 + chanOffset * x)
                                    + chanOffset
                                ],
                            )
                        )
                        channelResponseData[str(x + 1)] = tmpChannelResponseData._asdict()
                        channelResponseData[str(x + 1)]["useOnDemand"] = OnDemandFlag(channelResponseData[str(x + 1)]["useOnDemand"]).value == 1
                tmpChannelResponseData = {"channel": channelResponseData}
                result = dict(commonResponseData._asdict(), **tmpChannelResponseData)
                result["deviceID"] = bytes.hex(result["deviceID"])
                return result
            else:
                return {}
        except:
            return {}

    def parseStateResponse(self, commonResponseData, data):
        """
        Parse state response
        
        :param commonResponseData: The common response data from the response header
        :param data: The full state response data
        :return: The parsed state response data
        """
        try:
            stateResponseColumns = collections.namedtuple(
                "response",
                [
                    "controllerVersion",
                    "pannelVersion",
                    "deviceSorting",
                    "deviceCount",
                    "currentChannel",
                    "deviceNumber",
                    "errorCD",
                    "operationDeviceNumber",
                    "averageCalorimeter",
                    "gasInstantUse",
                    "gasAccumulatedUse",
                    "hotWaterSettingTemperature",
                    "hotWaterCurrentTemperature",
                    "hotWaterFlowRate",
                    "hotWaterTemperature",
                    "heatSettingTemperature",
                    "currentWorkingFluidTemperature",
                    "currentReturnWaterTemperature",
                    "powerStatus",
                    "heatStatus",
                    "useOnDemand",
                    "weeklyControl",
                    "totalDaySequence",
                ],
            )
            stateResponseData = stateResponseColumns._make(
                struct.unpack(
                    "2s 2s B B B B 2s B B 2s 4s B B 2s B B B B B B B B B", data[12:43]
                )
            )

            # Load each of the 7 daily sets of day sequences
            daySequenceResponseColumns = collections.namedtuple(
                "response", ["hour", "minute", "isOnOFF"]
            )

            daySequences = AutoVivification()
            for i in range(7):
                i2 = i * 32
                i3 = i2 + 43
                # Note Python 2.x doesn't convert these properly, so need to explicitly unpack them
                daySequences[i]["dayOfWeek"] = self.bigHexToInt(data[i3])
                weeklyTotalCount = self.bigHexToInt(data[i2 + 44])
                for i4 in range(weeklyTotalCount):
                    i5 = i4 * 3
                    daySequence = daySequenceResponseColumns._make(
                        struct.unpack("B B B", data[i2 + 45 + i5 : i2 + 45 + i5 + 3])
                    )
                    daySequences[i]["daySequence"][str(i4)] = daySequence._asdict()
            if len(data) >= 273:
                stateResponseColumns2 = collections.namedtuple(
                    "response",
                    [
                        "hotWaterAverageTemperature",
                        "inletAverageTemperature",
                        "supplyAverageTemperature",
                        "returnAverageTemperature",
                        "recirculationSettingTemperature",
                        "recirculationCurrentTemperature",
                    ],
                )
                stateResponseData2 = stateResponseColumns2._make(
                    struct.unpack("B B B B B B", data[267:273])
                )
            elif len(data) >= 271 and len(data) < 273:
                stateResponseColumns2 = collections.namedtuple(
                    "response",
                    [
                        "hotWaterAverageTemperature",
                        "inletAverageTemperature",
                        "supplyAverageTemperature",
                        "returnAverageTemperature",
                    ],
                )
                stateResponseData2 = stateResponseColumns2._make(
                    struct.unpack("B B B B", data[267:271])
                )            
            tmpDaySequences = {"daySequences": daySequences}
            result = dict(stateResponseData._asdict(), **tmpDaySequences)
            if stateResponseData2 is not None:
                result.update(stateResponseData2._asdict())
            result.update(commonResponseData._asdict())
            result["deviceID"] = bytes.hex(result["deviceID"])
        except:
            result = {}
        finally:
            return result

    def parseErrorCodeResponse(self, commonResponseData, data):
        """
        Parse error code response
        
        :param commonResponseData: The common response data from the response header
        :param data: The full error response data
        :return: The parsed error response data
        """
        errorResponseColumns = collections.namedtuple(
            "response",
            [
                "controllerVersion",
                "pannelVersion",
                "deviceSorting",
                "deviceCount",
                "currentChannel",
                "deviceNumber",
                "errorFlag",
                "errorCD",
            ],
        )
        errorResponseData = errorResponseColumns._make(
            struct.unpack("2s 2s B B B B B 2s", data[12:23])
        )
        result = errorResponseData._asdict()
        result.update(commonResponseData._asdict())
        return result

    def bigHexToInt(self, hex):
        """
        Convert from a list of big endian hex byte array or string to an integer
        
        :param hex: Big-endian string, int or byte array to be converted
        :return: Integer after little-endian conversion
        """
        if isinstance(hex, str):
            hex = bytearray(hex)
        if isinstance(hex, int):
            # This is already an int, just return it
            return hex
        bigEndianStr = "".join("%02x" % b for b in hex)
        littleHex = bytearray.fromhex(bigEndianStr)
        littleHex.reverse()
        littleHexStr = "".join("%02x" % b for b in littleHex)
        return int(littleHexStr, 16)

    async def sendRequest(
        self,
        currentControlChannel,
        deviceNumber,
        controlSorting,
        infoItem,
        controlItem,
        controlValue,
        WeeklyDay,
        read_response = True,
    ):
        """
        Main handler for sending a request to the binary API
        
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :param controlSorting: Corresponds with the ControlSorting enum (info or control)
        :param infoItem: Corresponds with the ControlType enum
        :param controlItem: Corresponds with the ControlType enum when controlSorting is control
        :param controlValue: Value being changed when controlling
        :param WeeklyDay: WeeklyDay dictionary (values are ignored when not changing schedule, but must be present)
        :return: Parsed response data
        
        """
        try:
            requestHeader = {
                "stx": 0x07,
                "did": 0x99,
                "reserve": 0x00,
                "cmd": 0xA6,
                "dataLength": 0x37,
                "dSid": 0x00,
            }
            sendData = bytearray(
                [
                    requestHeader["stx"],
                    requestHeader["did"],
                    requestHeader["reserve"],
                    requestHeader["cmd"],
                    requestHeader["dataLength"],
                    requestHeader["dSid"],
                ]
            )
            gwID = bytes.fromhex(self.gatewayID)
            sendData.extend(gwID)
            sendData.extend(
                [
                    0x01,  # commandCount
                    currentControlChannel,
                    deviceNumber,
                    controlSorting,
                    infoItem,
                    controlItem,
                    controlValue,
                ]
            )
            sendData.extend(
                [
                    WeeklyDay["WeeklyDay"],
                    WeeklyDay["WeeklyCount"],
                    WeeklyDay["1_Hour"],
                    WeeklyDay["1_Minute"],
                    WeeklyDay["1_Flag"],
                    WeeklyDay["2_Hour"],
                    WeeklyDay["2_Minute"],
                    WeeklyDay["2_Flag"],
                    WeeklyDay["3_Hour"],
                    WeeklyDay["3_Minute"],
                    WeeklyDay["3_Flag"],
                    WeeklyDay["4_Hour"],
                    WeeklyDay["4_Minute"],
                    WeeklyDay["4_Flag"],
                    WeeklyDay["5_Hour"],
                    WeeklyDay["5_Minute"],
                    WeeklyDay["5_Flag"],
                    WeeklyDay["6_Hour"],
                    WeeklyDay["6_Minute"],
                    WeeklyDay["6_Flag"],
                    WeeklyDay["7_Hour"],
                    WeeklyDay["7_Minute"],
                    WeeklyDay["7_Flag"],
                    WeeklyDay["8_Hour"],
                    WeeklyDay["8_Minute"],
                    WeeklyDay["8_Flag"],
                    WeeklyDay["9_Hour"],
                    WeeklyDay["9_Minute"],
                    WeeklyDay["9_Flag"],
                    WeeklyDay["10_Hour"],
                    WeeklyDay["10_Minute"],
                    WeeklyDay["10_Flag"],
                ]
            )
            
            if not self.connecting:
                if not self.logged_in:
                    await self.connect()
                
                time_diff  = (datetime.now() - self.last_connect).total_seconds()
                
                if time_diff >= 600:
                    await self.disconnect()
                    await self.connect()                    
                
                response = await self.send_and_receive(sendData, read_response = read_response)
        except Exception as e:
            response = {}
            _LOGGER.error(str(type(e).__name__) + ": " + str(e))
        finally:
            return response

    def initWeeklyDay(self):
        """
        Helper function to initialize and populate the WeeklyDay dict
        
        :return: An initialized but empty weeklyDay dict
        """
        weeklyDay = {}
        weeklyDay["WeeklyDay"] = 0x00
        weeklyDay["WeeklyCount"] = 0x00
        for i in range(1, 11):
            weeklyDay[str(i) + "_Hour"] = 0x00
            weeklyDay[str(i) + "_Minute"] = 0x00
            weeklyDay[str(i) + "_Flag"] = 0x00
        return weeklyDay

    # ----- Convenience methods for sending requests ----- #

    async def sendStateRequest(self, currentControlChannel, deviceNumber):
        """
        Send state request
        
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :return: Parsed response data
        """

        state = await self.sendRequest(
            currentControlChannel,
            deviceNumber,
            ControlSorting.INFO.value,
            ControlType.STATE.value,
            0x00,
            0x00,
            self.initWeeklyDay(),
        )

        return self.uodate_last_state(state,currentControlChannel,deviceNumber)

    async def sendPowerControlRequest(
        self, currentControlChannel, deviceNumber, powerState
    ):
        """
        Send device power control request
        
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :param powerState: The power state as identified in the OnOFFFlag enum
        :return: Parsed response data
        """
        state = await self.sendRequest(
            currentControlChannel,
            deviceNumber,
            ControlSorting.CONTROL.value,
            ControlType.UNKNOWN.value,
            DeviceControl.POWER.value,
            OnOFFFlag(powerState).value,
            self.initWeeklyDay(),
        )

        return self.uodate_last_state(state,currentControlChannel,deviceNumber)

    async def sendOnDemandControlRequest(
        self, currentControlChannel, deviceNumber
    ):
        """
        Send device on demand control request

        Note that no additional state parameter is required as this is the equivalent of pressing the HotButton.

        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :return: Parsed response data
        """
        state = await self.sendRequest(
            currentControlChannel,
            deviceNumber,
            ControlSorting.CONTROL.value,
            ControlType.UNKNOWN.value,
            DeviceControl.ON_DEMAND.value,
            OnOFFFlag.ON.value,
            self.initWeeklyDay(),
        )

        return self.uodate_last_state(state,currentControlChannel,deviceNumber)

    async def sendWaterTempControlRequest(
        self, currentControlChannel, deviceNumber, tempVal
    ):
        """
        Send device water temperature control request
        
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :param channelData: The parsed channel information data used to determine limits and units
        :param tempVal: The temperature to set
        :return: Parsed response data
        """
        state = await self.sendRequest(
            currentControlChannel,
            deviceNumber,
            ControlSorting.CONTROL.value,
            ControlType.UNKNOWN.value,
            DeviceControl.WATER_TEMPERATURE.value,
            int(tempVal),
            self.initWeeklyDay(),
            read_response = False
        )

        return self.uodate_last_state(state,currentControlChannel,deviceNumber)

    def uodate_last_state(self,stateData,channel,deviceNum):
        """
        Print State response data
        
        :param responseData: The parsed state response data
        :param temperatureType: The temperature type is used to determine if responses should be in metric or imperial units.
        """

        try:
            if self.channelInfo['channel'][str(channel)]['deviceTempFlag'] == TemperatureType.CELSIUS.value:
                if stateData["deviceSorting"] in [
                    DeviceSorting.NFC.value,
                    DeviceSorting.NCB_H.value,
                    DeviceSorting.NFB.value,
                    DeviceSorting.NVW.value,
                ]:
                    GIUFactor = 100
                else:
                    GIUFactor = 10
                stateData["gasInstantUse"] = round((self.bigHexToInt(stateData["gasInstantUse"]) * GIUFactor)/ 10.0, 1)
                stateData["gasAccumulatedUse"] = round(self.bigHexToInt(stateData["gasAccumulatedUse"]) / 10.0, 1)
                if stateData["deviceSorting"] in [
                    DeviceSorting.NPE.value,
                    DeviceSorting.NPN.value,
                    DeviceSorting.NPE2.value,
                    DeviceSorting.NCB.value,
                    DeviceSorting.NFC.value,
                    DeviceSorting.NCB_H.value,
                    DeviceSorting.CAS_NPE.value,
                    DeviceSorting.CAS_NPN.value,
                    DeviceSorting.CAS_NPE2.value,
                    DeviceSorting.NFB.value,
                    DeviceSorting.NVW.value,
                    DeviceSorting.CAS_NFB.value,
                    DeviceSorting.CAS_NVW.value,
                ]:
                    stateData["hotWaterSettingTemperature"] = round(stateData["hotWaterSettingTemperature"] / 2.0, 1)
                    if str(DeviceSorting(stateData["deviceSorting"]).name).startswith(
                        "CAS_"
                    ):
                        stateData["hotWaterAverageTemperature"] = round(stateData["hotWaterAverageTemperature"] / 2.0, 1)
                        stateData["inletAverageTemperature"] = round(stateData["inletAverageTemperature"] / 2.0, 1)
                    stateData["hotWaterCurrentTemperature"] = round(stateData["hotWaterCurrentTemperature"] / 2.0, 1)
                    stateData["hotWaterFlowRate"] = round(self.bigHexToInt(stateData["hotWaterFlowRate"]) / 10.0, 1)
                    stateData["hotWaterTemperature"] = round(stateData["hotWaterTemperature"] / 2.0, 1)
            elif self.channelInfo['channel'][str(channel)]['deviceTempFlag'] == TemperatureType.FAHRENHEIT.value:
                if stateData["deviceSorting"] in [
                    DeviceSorting.NFC.value,
                    DeviceSorting.NCB_H.value,
                    DeviceSorting.NFB.value,
                    DeviceSorting.NVW.value,
                ]:
                    GIUFactor = 10
                else:
                    GIUFactor = 1
                stateData["gasInstantUse"] = round(self.bigHexToInt(stateData["gasInstantUse"]) * GIUFactor * 3.968, 1)
                stateData["gasAccumulatedUse"] = round((self.bigHexToInt(stateData["gasAccumulatedUse"]) * 35.314667) / 10.0, 1)
                if stateData["deviceSorting"] in [
                    DeviceSorting.NPE.value,
                    DeviceSorting.NPN.value,
                    DeviceSorting.NPE2.value,
                    DeviceSorting.NCB.value,
                    DeviceSorting.NFC.value,
                    DeviceSorting.NCB_H.value,
                    DeviceSorting.CAS_NPE.value,
                    DeviceSorting.CAS_NPN.value,
                    DeviceSorting.CAS_NPE2.value,
                    DeviceSorting.NFB.value,
                    DeviceSorting.NVW.value,
                    DeviceSorting.CAS_NFB.value,
                    DeviceSorting.CAS_NVW.value,
                ]:
                    stateData["hotWaterFlowRate"] = round((self.bigHexToInt(stateData["hotWaterFlowRate"]) / 3.785) / 10.0, 1)

            stateData["controllerVersion"] = self.bigHexToInt(stateData["controllerVersion"])
            stateData["pannelVersion"] = self.bigHexToInt(stateData["pannelVersion"])
            stateData["errorCD"] = self.bigHexToInt(stateData["errorCD"])       
            stateData["powerStatus"] = OnOFFFlag(stateData["powerStatus"]).value < 2
            stateData["useOnDemand"] = OnDemandFlag(stateData["useOnDemand"]).value == 1
            stateData["weeklyControl"] = OnOFFFlag(stateData["weeklyControl"]).value < 2
            
            if self.last_state.get(str(channel)) is None:
                self.last_state[str(channel)] = {}
            self.last_state[str(channel)][str(deviceNum)] = stateData
        except Exception as e:
            if self.last_state.get(str(channel)) is not None:
                if stateData is not None:
                    if stateData.get('channel') is not None and self.last_state[str(channel)][str(deviceNum)].get("hotWaterFlowRate") is not None:
                        if self.last_state[str(channel)][str(deviceNum)]["hotWaterFlowRate"] == 0:
                            #This condition sometimes arises when the power is off and there is hot water flow
                            self.last_state[str(channel)][str(deviceNum)]["hotWaterFlowRate"] = 0.1 
            else:
                self.last_state[str(channel)] = {}
                self.last_state[str(channel)][str(deviceNum)] = {}
        finally:
            self.last_state[str(channel)][str(deviceNum)]["last_update"] = datetime.now()
            return self.last_state
