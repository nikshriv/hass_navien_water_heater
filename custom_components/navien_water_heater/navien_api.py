""" 
This module makes it possible to interact with Navien tankless water heater, 
combi-boiler or boiler connected via NaviLink.

Please refer to the documentation provided in the README.md,
which can be found at https://github.com/rudybrian/PyNavienSmartControl/

This is a slightly modified version that uses async for easier integration with hass

"""

__version__ = "1.0"
__author__ = "Brian Rudy"
__email__ = "brudy@praecogito.com"
__credits__ = ["matthew1471", "Gary T. Giesen"]
__date__ = "3/15/2022"
__license__ = "GPL"


# Third party library
import aiohttp

# We use asyncio for tcp i/o.
import asyncio

# We unpack structures.
import struct

# We use namedtuple to reduce index errors.
import collections

# We use Python enums.
import enum

# We need json support for parsing the REST API response
import json


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


class NavienSmartControl:
    """The main NavienSmartControl class"""

    # The Navien server.
    navienServer = "uscv2.naviensmartcontrol.com"
    navienWebServer = "https://" + navienServer
    navienServerSocketPort = 6001

    def __init__(self, userID, passwd):
        """
        Construct a new 'NavienSmartControl' object.

        :param userID: The user ID used to log in to the mobile application
        :param passwd: The corresponding user's password
        :return: returns nothing
        """
        self.userID = userID
        self.passwd = passwd
        self.reader = None
        self.writer = None

    async def login(self):
        """
        Login to the REST API
        
        :return: The REST API response
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(NavienSmartControl.navienWebServer + "/api/requestDeviceList", json={"userID": self.userID, "password": self.passwd}) as response:
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

    async def connect(self, gatewayID):
        """
        Connect to the binary API service
        
        :param gatewayID: The gatewayID that we want to connect to
        :return: The response data (normally a channel information response)
        """

        self.reader, self.writer = await asyncio.open_connection(NavienSmartControl.navienServer, NavienSmartControl.navienServerSocketPort)
        self.writer.write((self.userID + "$" + "iPhone1.0" + "$" + gatewayID).encode())
        await self.writer.drain()

        # Receive the status.
        data = await self.reader.read(1024)

        # Return the parsed data.
        return self.parseResponse(data)
        
    async def disconnect(self):
        """
        Disconnect the from the API
        """
        if (self.writer):
            self.writer.close()
            await self.writer.wait_closed()

    def parseResponse(self, data):
        """
        Main handler for handling responses from the binary protocol.
        This function passes on the response data to the appopriate response-specific parsing function.

        :param data: Data received from a response
        :return: The parsed response data from the corresponding response-specific parser.
        """
        # The response is returned with a fixed header for the first 12 bytes
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
        elif commonResponseData.controlType == ControlType.TREND_SAMPLE.value:
            retval = self.parseTrendSampleResponse(commonResponseData, data)
        elif commonResponseData.controlType == ControlType.TREND_MONTH.value:
            retval = self.parseTrendMYResponse(commonResponseData, data)
        elif commonResponseData.controlType == ControlType.TREND_YEAR.value:
            retval = self.parseTrendMYResponse(commonResponseData, data)
        elif commonResponseData.controlType == ControlType.ERROR_CODE.value:
            retval = self.parseErrorCodeResponse(commonResponseData, data)
        elif commonResponseData.controlType == ControlType.UNKNOWN.value:
            raise Exception("Error: Unknown controlType. Please restart to retry.")
        else:
            raise Exception(
                "An error occurred in the process of retrieving data; please restart to retry."
            )

        return retval

    def parseChannelInformationResponse(self, commonResponseData, data):
        """
        Parse channel information response
        
        :param commonResponseData: The common response data from the response header
        :param data: The full channel information response data
        :return: The parsed channel information response data
        """
        # This tells us which serial channels are in use
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
            tmpChannelResponseData = {"channel": channelResponseData}
            result = dict(commonResponseData._asdict(), **tmpChannelResponseData)
            result["deviceID"] = bytes.hex(result["deviceID"])
            return result
        else:
            raise Exception(
                "Error: Unknown Channel: An error occurred in the process of parsing channel information; please restart to retry."
            )

    def parseStateResponse(self, commonResponseData, data):
        """
        Parse state response
        
        :param commonResponseData: The common response data from the response header
        :param data: The full state response data
        :return: The parsed state response data
        """
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
        if len(data) > 271:
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
                struct.unpack("B B B B B B", data[267:274])
            )
        else:
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
                struct.unpack("B B B B", data[267:272])
            )
        tmpDaySequences = {"daySequences": daySequences}
        result = dict(stateResponseData._asdict(), **tmpDaySequences)
        result.update(stateResponseData2._asdict())
        result.update(commonResponseData._asdict())
        result["deviceID"] = bytes.hex(result["deviceID"])
        return result

    def parseTrendSampleResponse(self, commonResponseData, data):
        """
        Parse trend sample response
        
        :param commonResponseData: The common response data from the response header
        :param data: The full trend sample response data
        :return: The parsed trend sample response data
        """
        if len(data) > 39:
            trendSampleResponseColumns = collections.namedtuple(
                "response",
                [
                    "controllerVersion",
                    "pannelVersion",
                    "deviceSorting",
                    "deviceCount",
                    "currentChannel",
                    "deviceNumber",
                    "modelInfo",
                    "totalOperatedTime",
                    "totalGasAccumulateSum",
                    "totalHotWaterAccumulateSum",
                    "totalCHOperatedTime",
                    "totalDHWUsageTime",
                ],
            )
            trendSampleResponseData = trendSampleResponseColumns._make(
                struct.unpack("2s 2s B B B B 3s 4s 4s 4s 4s 4s", data[12:43])
            )
        else:
            trendSampleResponseColumns = collections.namedtuple(
                "response",
                [
                    "controllerVersion",
                    "pannelVersion",
                    "deviceSorting",
                    "deviceCount",
                    "currentChannel",
                    "deviceNumber",
                    "modelInfo",
                    "totalOperatedTime",
                    "totalGasAccumulateSum",
                    "totalHotWaterAccumulateSum",
                    "totalCHOperatedTime",
                ],
            )
            trendSampleResponseData = trendSampleResponseColumns._make(
                struct.unpack("2s 2s B B B B 3s 4s 4s 4s 4s", data[12:39])
            )
        result = trendSampleResponseData._asdict()
        result.update(commonResponseData._asdict())
        return result

    def parseTrendMYResponse(self, commonResponseData, data):
        """
        Parse trend month or year response
        
        :param commonResponseData: The common response data from the response header
        :param data: The full trend (month or year) response data
        :return: The parsed trend (month or year) response data
        """
        trendSampleMYResponseColumns = collections.namedtuple(
            "response",
            [
                "controllerVersion",
                "pannelVersion",
                "deviceSorting",
                "deviceCount",
                "currentChannel",
                "deviceNumber",
                "totalDaySequence",
            ],
        )
        trendSampleMYResponseData = trendSampleMYResponseColumns._make(
            struct.unpack("2s 2s B B B B B", data[12:21])
        )

        # Read the trend sequence data
        trendSequenceColumns = collections.namedtuple(
            "response",
            [
                "modelInfo",
                "gasAccumulatedUse",
                "hotWaterAccumulatedUse",
                "hotWaterOperatedCount",
                "onDemandUseCount",
                "heatAccumulatedUse",
                "outdoorAirMaxTemperature",
                "outdoorAirMinTemperature",
                "dHWAccumulatedUse",
            ],
        )

        trendSequences = AutoVivification()
        # loops 31 times for month and 24 times for year
        for i in range(trendSampleMYResponseData.totalDaySequence):
            i2 = i * 22
            trendSequences[i]["dMIndex"] = data[i2 + 21]
            trendData = trendSequenceColumns._make(
                struct.unpack("3s 4s 4s 2s 2s 2s B B 2s", data[i2 + 22 : i2 + 43])
            )
            trendSequences[i]["trendData"] = trendData._asdict()

        tmpTrendSequences = {"trendSequences": trendSequences}
        result = dict(trendSampleMYResponseData._asdict(), **tmpTrendSequences)
        result.update(commonResponseData._asdict())
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
        gatewayID,
        currentControlChannel,
        deviceNumber,
        controlSorting,
        infoItem,
        controlItem,
        controlValue,
        WeeklyDay,
    ):
        """
        Main handler for sending a request to the binary API
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :param controlSorting: Corresponds with the ControlSorting enum (info or control)
        :param infoItem: Corresponds with the ControlType enum
        :param controlItem: Corresponds with the ControlType enum when controlSorting is control
        :param controlValue: Value being changed when controlling
        :param WeeklyDay: WeeklyDay dictionary (values are ignored when not changing schedule, but must be present)
        :return: Parsed response data
        
        """
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
        if type(gatewayID) == str:
            gatewayID = bytes.fromhex(gatewayID)
        sendData.extend(gatewayID)
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

        # We should ensure that the socket is still connected, and abort if not
        self.writer.write(sendData)
        await self.writer.drain()

        # Receive the status.
        data = await self.reader.read(1024)
        return self.parseResponse(data)

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

    async def sendStateRequest(self, gatewayID, currentControlChannel, deviceNumber):
        """
        Send state request
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :return: Parsed response data
        """
        return await self.sendRequest(
            gatewayID,
            currentControlChannel,
            deviceNumber,
            ControlSorting.INFO.value,
            ControlType.STATE.value,
            0x00,
            0x00,
            self.initWeeklyDay(),
        )

    async def sendChannelInfoRequest(self, gatewayID, currentControlChannel, deviceNumber):
        """
        Send channel information request (we already get this when we log in)
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :return: Parsed response data
        """
        return await self.sendRequest(
            gatewayID,
            currentControlChannel,
            deviceNumber,
            ControlSorting.INFO.value,
            ControlType.CHANNEL_INFORMATION.value,
            0x00,
            0x00,
            self.initWeeklyDay(),
        )

    async def sendTrendSampleRequest(self, gatewayID, currentControlChannel, deviceNumber):
        """
        Send trend sample request
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :return: Parsed response data
        """
        return await self.sendRequest(
            gatewayID,
            currentControlChannel,
            deviceNumber,
            ControlSorting.INFO.value,
            ControlType.TREND_SAMPLE.value,
            0x00,
            0x00,
            self.initWeeklyDay(),
        )

    async def sendTrendMonthRequest(self, gatewayID, currentControlChannel, deviceNumber):
        """
        Send trend month request
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :return: Parsed response data
        """
        return await self.sendRequest(
            gatewayID,
            currentControlChannel,
            deviceNumber,
            ControlSorting.INFO.value,
            ControlType.TREND_MONTH.value,
            0x00,
            0x00,
            self.initWeeklyDay(),
        )

    async def sendTrendYearRequest(self, gatewayID, currentControlChannel, deviceNumber):
        """
        Send trend year request
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :return: Parsed response data
        """
        return await self.sendRequest(
            gatewayID,
            currentControlChannel,
            deviceNumber,
            ControlSorting.INFO.value,
            ControlType.TREND_YEAR.value,
            0x00,
            0x00,
            self.initWeeklyDay(),
        )

    async def sendPowerControlRequest(
        self, gatewayID, currentControlChannel, deviceNumber, powerState
    ):
        """
        Send device power control request
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :param powerState: The power state as identified in the OnOFFFlag enum
        :return: Parsed response data
        """
        return await self.sendRequest(
            gatewayID,
            currentControlChannel,
            deviceNumber,
            ControlSorting.CONTROL.value,
            ControlType.UNKNOWN.value,
            DeviceControl.POWER.value,
            OnOFFFlag(powerState).value,
            self.initWeeklyDay(),
        )

    async def sendHeatControlRequest(
        self, gatewayID, currentControlChannel, deviceNumber, channelData, heatState
    ):
        """
        Send device heat control request
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :param heatState: The heat state as identified in the OnOFFFlag enum
        :return: Parsed response data
        """
        if (
            NFBWaterFlag(
                (
                    channelData["channel"][str(currentControlChannel)]["wwsdFlag"]
                    & WWSDMask.HOTWATER_POSSIBILITY.value
                )
                > 0
            )
            == NFBWaterFlag.OFF
        ):
            raise Exception("Error: Heat is disabled.")
        else:
            return await self.sendRequest(
                gatewayID,
                currentControlChannel,
                deviceNumber,
                ControlSorting.CONTROL.value,
                ControlType.UNKNOWN.value,
                DeviceControl.HEAT.value,
                OnOFFFlag(heatState).value,
                self.initWeeklyDay(),
            )

    async def sendOnDemandControlRequest(
        self, gatewayID, currentControlChannel, deviceNumber, channelData
    ):
        """
        Send device on demand control request

        Note that no additional state parameter is required as this is the equivalent of pressing the HotButton.

        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :return: Parsed response data
        """
        if (
            RecirculationFlag(
                (
                    channelData["channel"][str(currentControlChannel)]["wwsdFlag"]
                    & WWSDMask.RECIRCULATION_POSSIBILITY.value
                )
                > 0
            )
            == RecirculationFlag.OFF
        ):
            raise Exception("Error: Recirculation is disabled.")
        else:
            return await self.sendRequest(
                gatewayID,
                currentControlChannel,
                deviceNumber,
                ControlSorting.CONTROL.value,
                ControlType.UNKNOWN.value,
                DeviceControl.ON_DEMAND.value,
                OnOFFFlag.ON.value,
                self.initWeeklyDay(),
            )

    async def sendDeviceWeeklyControlRequest(
        self, gatewayID, currentControlChannel, deviceNumber, weeklyState
    ):
        """
        Send device weekly control (enable or disable weekly schedule)
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :param weeklyState: The weekly control state as identified in the OnOFFFlag enum
        :return: Parsed response data

        """
        return await self.sendRequest(
            gatewayID,
            currentControlChannel,
            deviceNumber,
            ControlSorting.CONTROL.value,
            ControlType.UNKNOWN.value,
            DeviceControl.WEEKLY.value,
            OnOFFFlag(weeklyState).value,
            self.initWeeklyDay(),
        )

    async def sendWaterTempControlRequest(
        self, gatewayID, currentControlChannel, deviceNumber, tempVal
    ):
        """
        Send device water temperature control request
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :param channelData: The parsed channel information data used to determine limits and units
        :param tempVal: The temperature to set
        :return: Parsed response data
        """
        return await self.sendRequest(
            gatewayID,
            currentControlChannel,
            deviceNumber,
            ControlSorting.CONTROL.value,
            ControlType.UNKNOWN.value,
            DeviceControl.WATER_TEMPERATURE.value,
            tempVal,
            self.initWeeklyDay(),
        )

    async def sendHeatingWaterTempControlRequest(
        self, gatewayID, currentControlChannel, deviceNumber, channelData, tempVal
    ):
        """
        Send device heating water temperature control request
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :param channelData: The parsed channel information data used to determine limits and units
        :param tempVal: The temperature to set
        :return: Parsed response data
        """
        if (
            NFBWaterFlag(
                (
                    channelData["channel"][str(currentControlChannel)]["wwsdFlag"]
                    & WWSDMask.HOTWATER_POSSIBILITY.value
                )
                > 0
            )
            == NFBWaterFlag.OFF
        ):
            raise Exception("Error: Heat is disabled. Unable to set temperature")
        elif (
            tempVal
            > channelData["channel"][str(currentControlChannel)][
                "heatingMaximumSettingWaterTemperature"
            ]
        ) or (
            tempVal
            < channelData["channel"][str(currentControlChannel)][
                "heatingMinimumSettingWaterTemperature"
            ]
        ):
            raise Exception("Error: Invalid tempVal requested.")
        else:
            return await self.sendRequest(
                gatewayID,
                currentControlChannel,
                deviceNumber,
                ControlSorting.CONTROL.value,
                ControlType.UNKNOWN.value,
                DeviceControl.HEATING_WATER_TEMPERATURE.value,
                tempVal,
                self.initWeeklyDay(),
            )

    async def sendRecirculationTempControlRequest(
        self, gatewayID, currentControlChannel, deviceNumber, channelData, tempVal
    ):
        """
        Send recirculation temperature control request
        
        :param gatewayID: The gatewayID (NaviLink) the device is connected to
        :param currentControlChannel: The serial port channel on the Navilink that the device is connected to
        :param deviceNumber: The device number on the serial bus corresponding with the device
        :param channelData: The parsed channel information data used to determine limits and units
        :param tempVal: The temperature to set
        :return: Parsed response data
        """
        if (
            RecirculationFlag(
                (
                    channelData["channel"][str(currentControlChannel)]["wwsdFlag"]
                    & WWSDMask.RECIRCULATION_POSSIBILITY.value
                )
                > 0
            )
            == RecirculationFlag.OFF
        ):
            raise Exception(
                "Error: Recirculation is disabled. Unable to set temperature"
            )
        elif (
            tempVal
            > channelData["channel"][str(currentControlChannel)][
                "maximumSettingWaterTemperature"
            ]
        ) or (
            tempVal
            < channelData["channel"][str(currentControlChannel)][
                "minimumSettingWaterTemperature"
            ]
        ):
            raise Exception("Error: Invalid tempVal requested.")
        else:
            return await self.sendRequest(
                gatewayID,
                currentControlChannel,
                deviceNumber,
                ControlSorting.CONTROL.value,
                ControlType.UNKNOWN.value,
                DeviceControl.RECIRCULATION_TEMPERATURE.value,
                tempVal,
                self.initWeeklyDay(),
            )

    # Send request to set weekly schedule
    async def sendDeviceControlWeeklyScheduleRequest(self, stateData, WeeklyDay, action):
        """
        Send request to set weekly schedule
        
        The state information contains the gatewayID, currentControlChannel, deviceNumber and all current WeeklyDay schedules. We need to compare current WeeklyDay schedule with requested modifications and apply as needed.

        Note: Only one schedule entry can be modified at a time.

        :param stateData: The state information contains the gatewayID, currentControlChannel, deviceNumber and all current WeeklyDay schedules.
        :param WeeklyDay: We need to compare current schedule in the stateData with requested WeeklyDay and apply as needed.
        :param action: add or delete the requested WeeklyDay.
        :return: Parsed response data
        """

        if (WeeklyDay["hour"] > 23) or (WeeklyDay["minute"] > 59):
            raise Exception("Error: Invalid weeklyday schedule time requested")

        # Check if the entry already exists and set a flag
        foundScheduleEntry = False
        if "daySequence" in stateData["daySequences"][WeeklyDay["dayOfWeek"] - 1]:
            for j in stateData["daySequences"][WeeklyDay["dayOfWeek"] - 1][
                "daySequence"
            ]:
                if (
                    (
                        stateData["daySequences"][WeeklyDay["dayOfWeek"] - 1][
                            "daySequence"
                        ][j]["hour"]
                        == WeeklyDay["hour"]
                    )
                    and (
                        stateData["daySequences"][WeeklyDay["dayOfWeek"] - 1][
                            "daySequence"
                        ][j]["minute"]
                        == WeeklyDay["minute"]
                    )
                    and (
                        stateData["daySequences"][WeeklyDay["dayOfWeek"] - 1][
                            "daySequence"
                        ][j]["isOnOFF"]
                        == WeeklyDay["isOnOFF"]
                    )
                ):
                    foundScheduleEntry = True
                    foundIndex = j

        tmpWeeklyDay = self.initWeeklyDay()
        tmpWeeklyDay["WeeklyDay"] = WeeklyDay["dayOfWeek"]

        if action == "add":
            if foundScheduleEntry:
                raise Exception(
                    "Error: unable to add. Already have matching schedule entry."
                )
            else:
                if (
                    "daySequence"
                    in stateData["daySequences"][WeeklyDay["dayOfWeek"] - 1]
                ):
                    currentWDCount = len(
                        stateData["daySequences"][WeeklyDay["dayOfWeek"] - 1][
                            "daySequence"
                        ]
                    )
                    for i in stateData["daySequences"][WeeklyDay["dayOfWeek"] - 1][
                        "daySequence"
                    ]:
                        tmpWeeklyDay[str(int(i) + 1) + "_Hour"] = stateData[
                            "daySequences"
                        ][WeeklyDay["dayOfWeek"] - 1]["daySequence"][i]["hour"]
                        tmpWeeklyDay[str(int(i) + 1) + "_Minute"] = stateData[
                            "daySequences"
                        ][WeeklyDay["dayOfWeek"] - 1]["daySequence"][i]["minute"]
                        tmpWeeklyDay[str(int(i) + 1) + "_Flag"] = stateData[
                            "daySequences"
                        ][WeeklyDay["dayOfWeek"] - 1]["daySequence"][i]["isOnOFF"]
                else:
                    currentWDCount = 0
                tmpWeeklyDay["WeeklyCount"] = currentWDCount + 1
                tmpWeeklyDay[str(currentWDCount + 1) + "_Hour"] = WeeklyDay["hour"]
                tmpWeeklyDay[str(currentWDCount + 1) + "_Minute"] = WeeklyDay["minute"]
                tmpWeeklyDay[str(currentWDCount + 1) + "_Flag"] = WeeklyDay["isOnOFF"]
        elif action == "delete":
            if not foundScheduleEntry:
                raise Exception("Error: unable to delete. No matching schedule entry.")
            else:
                dSIndex = 0
                for c in stateData["daySequences"][WeeklyDay["dayOfWeek"] - 1][
                    "daySequence"
                ]:
                    if c != foundIndex:
                        dSIndex += 1
                        tmpWeeklyDay[str(dSIndex) + "_Hour"] = stateData[
                            "daySequences"
                        ][WeeklyDay["dayOfWeek"] - 1]["daySequence"][c]["hour"]
                        tmpWeeklyDay[str(dSIndex) + "_Minute"] = stateData[
                            "daySequences"
                        ][WeeklyDay["dayOfWeek"] - 1]["daySequence"][c]["minute"]
                        tmpWeeklyDay[str(dSIndex) + "_Flag"] = stateData[
                            "daySequences"
                        ][WeeklyDay["dayOfWeek"] - 1]["daySequence"][c]["isOnOFF"]
                tmpWeeklyDay["WeeklyCount"] = dSIndex
        else:
            raise Exception("Error: unsupported action " + action)

        # print(json.dumps(tmpWeeklyDay, indent=2, default=str))
        return await self.sendRequest(
            stateData["deviceID"],
            stateData["currentChannel"],
            stateData["deviceNumber"],
            ControlSorting.CONTROL.value,
            ControlType.UNKNOWN.value,
            DeviceControl.WEEKLY.value,
            OnOFFFlag(stateData["weeklyControl"]).value,
            tmpWeeklyDay,
        )

    def convertState(self, stateData, temperatureType):
        """
        Print State response data
        
        :param responseData: The parsed state response data
        :param temperatureType: The temperature type is used to determine if responses should be in metric or imperial units.
        """

        if temperatureType == TemperatureType.CELSIUS.value:
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
        elif temperatureType == TemperatureType.FAHRENHEIT.value:
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
        stateData["useOnDemand"] = OnDemandFlag(stateData["useOnDemand"]).name
        stateData["weeklyControl"] = OnOFFFlag(stateData["weeklyControl"]).value < 2
        return stateData