import asyncio
import enum
import json
import logging
import uuid
from datetime import datetime,timedelta
import AWSIoTPythonSDK.MQTTLib as mqtt
import aiohttp

_LOGGER = logging.getLogger(__name__)

class NavilinkConnect():

    # The Navien server.
    navienWebServer = "https://nlus.naviensmartcontrol.com/api/v2"

    def __init__(self, userId, passwd, device_index = 0, polling_interval = 15, aws_cert_path = "AmazonRootCA1.pem", subscribe_all_topics=False):
        """
        Construct a new 'NavilinkConnect' object.

        :param userId: The user ID used to log in to the mobile application
        :param passwd: The corresponding user's password
        :return: returns nothing
        """
        self.userId = userId
        self.passwd = passwd
        self.device_index = device_index
        self.polling_interval = polling_interval
        self.aws_cert_path = aws_cert_path
        self.subscribe_all_topics = subscribe_all_topics
        self.loop = asyncio.get_running_loop()
        self.connected = False
        self.shutting_down = False
        self.user_info = None
        self.device_info = None
        self.client = None
        self.client_id = ""
        self.topics = None
        self.messages = None
        self.channels = {}
        self.disconnect_event = asyncio.Event()
        self.channel_info_event = None
        self.response_events = {}
        self.client_lock = asyncio.Lock()
        self.last_poll = None

    async def start(self):
        if self.polling_interval > 0:
            valid_user = True
            while not self.connected and valid_user and not self.shutting_down:
                try:
                    await self.login()
                except (UserNotFound,UnableToConnect,NoResponseData) as err:
                    _LOGGER.error(err)
                    valid_user=False
                except Exception as e:
                    _LOGGER.error("Connection error during start up: " +str(e))
                    await asyncio.sleep(15)
                else:
                    asyncio.create_task(self._start())
                    if len(self.channels) > 0:
                        return self.channels
                    else:
                        raise NoNavienDevices("No Navien devices found with the given credentials")
        else:
            return await self.login()

    async def _start(self):
        if not self.shutting_down:
            tasks = [
                asyncio.create_task(self._poll_mqtt_server(), name = "Poll MQTT Server"),
                asyncio.create_task(self._server_connection_lost(), name = "Connection Lost Event"),
                asyncio.create_task(self._refresh_connection(), name = "Reresh Connection")
            ]
            done, pending = await asyncio.wait(tasks,return_when=asyncio.FIRST_EXCEPTION)
            for task in done:
                name = task.get_name()
                try:
                    task.result()
                except Exception as e:
                    _LOGGER.error(name + ": " + str(type(e).__name__) + ": " + str(e))
            for task in pending:
                task.cancel()     
            if not self.shutting_down:
                _LOGGER.warning("Connection to AWS IOT Navilink server reset, reconnecting in 15 seconds")
                self.connected = False
                await asyncio.sleep(15)
                asyncio.create_task(self.start())

    async def login(self):
        """
        Login to the REST API and save user information
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(NavilinkConnect.navienWebServer + "/user/sign-in", json={"userId": self.userId, "password": self.passwd}) as response:
                # If an error occurs this will raise it, otherwise it calls get_device and returns after device is obtained from the server
                if response.status != 200:
                    raise UnableToConnect("Unexpected response during login")
                response_data = await response.json()
                if response_data.get('msg','') == "USER_NOT_FOUND":
                    raise UserNotFound("Unable to log in with given credentials")
                try:
                    response_data["data"]
                    self.user_info = response_data["data"]
                except:
                    raise NoResponseData("Unexpected problem while retrieving user data")
                
                return await self._get_device_list()

    async def _get_device_list(self):
        """
        Get list of devices for the given user credentials
        """
        headers = {"Authorization":self.user_info.get("token",{}).get("accessToken","")}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(NavilinkConnect.navienWebServer + "/device/list", json={"offset":0,"count":20,"userId":self.userId}) as response:
                # If an error occurs this will raise it, otherwise it returns the gateway list.
                if response.status != 200:
                    raise UnableToConnect("Unexpected response while retrieving device list")
                response_data = await response.json()
                try:
                    response_data["data"]
                    device_info_list = response_data["data"]
                    self.device_info = device_info_list[self.device_index]
                except:
                    raise NoResponseData("Unexpected problem while retrieving device list")
                
                if self.polling_interval > 0:
                    await self._connect_aws_mqtt()
                return device_info_list

    async def _connect_aws_mqtt(self):
        self.client_id = str(uuid.uuid4())
        self.topics = Topics(self.user_info, self.device_info, self.client_id)
        self.messages = Messages(self.device_info, self.client_id, self.topics)
        accessKeyId = self.user_info.get("token",{}).get("accessKeyId",None)
        secretKey = self.user_info.get("token",{}).get("secretKey",None)
        sessionToken = self.user_info.get("token",{}).get("sessionToken",None)

        if accessKeyId and secretKey and sessionToken:
            self.client = mqtt.AWSIoTMQTTClient(clientID = self.client_id, protocolType=4, useWebsocket=True, cleanSession=True)
            self.client.configureEndpoint(hostName= 'a1t30mldyslmuq-ats.iot.us-east-1.amazonaws.com', portNumber= 443)
            self.client.configureUsernamePassword(username='?SDK=Android&Version=2.16.12', password=None)
            self.client.configureLastWill(topic = self.topics.app_connection(), payload = json.dumps(self.messages.last_will(),separators=(',',':')), QoS=1, retain=False)
            self.client.configureCredentials(self.aws_cert_path)
            self.client.configureIAMCredentials(AWSAccessKeyID=accessKeyId, AWSSecretAccessKey=secretKey, AWSSessionToken=sessionToken)
            self.client.configureConnectDisconnectTimeout(5)
            self.client.onOffline=self._on_offline
            self.client.onOnline=self._on_online
            await self.loop.run_in_executor(None,self.client.connect)
            await self._subscribe_to_topics()
            if not len(self.channels):
                await self._get_channel_info()
            await self._get_channel_status_all(wait_for_response = True)
            self.last_poll = datetime.now()
        else:
            raise NoAccessKey("Missing Access key, Secret key, or Session token")

    async def _poll_mqtt_server(self):
        time_delta = 0
        while self.connected and not self.shutting_down:
            if time_delta < self.polling_interval:
                interval = self.polling_interval - time_delta
            else:
                interval = 0.1
            await asyncio.sleep(self.polling_interval - time_delta)
            pre_poll = datetime.now()
            if not self.client_lock.locked():
                await self._get_channel_status_all()
            self.last_poll = datetime.now()
            time_delta = (self.last_poll - pre_poll).total_seconds()
        if not self.shutting_down:
            raise PollingError("Polling of AWS IOT Navilink server completed")

    async def _server_connection_lost(self):
        await self.disconnect_event.wait()
        self.disconnect_event.clear()
        raise DisconnectEvent("Disconnected from Navilink server...")

    async def _refresh_connection(self):
        now = datetime.now()
        target_time = datetime(now.year, now.month, now.day, 2, 0, 0)
        if now > target_time:
            # If it's already past 2 am, wait until tomorrow
            target_time += timedelta(days=1)
        delta = (target_time - now).total_seconds()
        await asyncio.sleep(delta)
        await self.disconnect(shutting_down=False)

    async def disconnect(self,shutting_down=True):
        if self.client and self.connected:
            self.shutting_down = shutting_down
            await self.loop.run_in_executor(None,self.client.disconnect)

    def _on_online(self):
        self.connected = True

    def _on_offline(self):
        if not self.shutting_down:
            self.disconnect_event.set()

    async def async_subscribe(self,topic,QoS=1,callback=None):
        try:
            def subscribe():
                self.client.subscribe(topic=topic,QoS=QoS,callback=callback)

            async with self.client_lock:
                await self.loop.run_in_executor(None,subscribe)
        except Exception as e:
            _LOGGER.debug("Error occurred in async_subscribe: " + str(e))
            await self.disconnect(shutting_down=False)           

    async def async_publish(self,topic,payload,QoS=1,session_id=""):
        try:
            def publish():
                self.client.publish(topic=topic,payload=json.dumps(payload,separators=(',',':')),QoS=QoS)
                                
            async with self.client_lock:
                await self.loop.run_in_executor(None,publish)

            if response_event :=  self.response_events.get(session_id,None):
                try:
                    await asyncio.wait_for(response_event.wait(),timeout=self.polling_interval)
                except:
                    pass
                response_event.clear()
                self.response_events.pop(session_id)
        except Exception as e:
            _LOGGER.debug("Error occurred in async_publish: " + str(e))
            if response_event :=  self.response_events.get(session_id,None):
                response_event.clear()
                self.response_events.pop(session_id)
            await self.disconnect(shutting_down=False)   


    async def _subscribe_to_topics(self):
        await self.async_subscribe(topic=self.topics.channel_info_sub(),callback=self.handle_other)
        await self.async_subscribe(topic=self.topics.channel_info_res(),callback=self.handle_channel_info)
        await self.async_subscribe(topic=self.topics.control_fail(),callback=self.handle_other)
        await self.async_subscribe(topic=self.topics.channel_status_sub(),callback=self.handle_other)
        await self.async_subscribe(topic=self.topics.channel_status_res(),callback=self.handle_channel_status)
        await self.async_subscribe(topic=self.topics.connection(),callback=self.handle_other)
        await self.async_subscribe(topic=self.topics.disconnect(),callback=self.handle_other)
        if self.subscribe_all_topics:
            await self.async_subscribe(topic=self.topics.weekly_schedule_sub(),callback=self.handle_other)
            await self.async_subscribe(topic=self.topics.weekly_schedule_res(),callback=self.handle_weekly_schedule)
            await self.async_subscribe(topic=self.topics.simple_trend_sub(),callback=self.handle_other)
            await self.async_subscribe(topic=self.topics.simple_trend_res(),callback=self.handle_simple_trend)
            await self.async_subscribe(topic=self.topics.hourly_trend_sub(),callback=self.handle_other)
            await self.async_subscribe(topic=self.topics.hourly_trend_res(),callback=self.handle_hourly_trend)
            await self.async_subscribe(topic=self.topics.daily_trend_sub(),callback=self.handle_other)
            await self.async_subscribe(topic=self.topics.daily_trend_res(),callback=self.handle_daily_trend)
            await self.async_subscribe(topic=self.topics.monthly_trend_sub(),callback=self.handle_other)
            await self.async_subscribe(topic=self.topics.monthly_trend_res(),callback=self.handle_monthly_trend)

    async def _get_channel_info(self):
        topic = self.topics.start()
        payload = self.messages.channel_info()
        session_id = self.get_session_id()
        payload["sessionID"] = session_id
        self.response_events[session_id] = asyncio.Event()
        await self.async_publish(topic=topic,payload=payload,session_id=session_id)
        if len(self.channels) == 0:
            raise NoChannelInformation("Unable to get channel information")

    async def _get_channel_status_all(self,wait_for_response=False):
        for channel in self.channels.values():
            topic = self.topics.channel_status_req()
            payload = self.messages.channel_status(channel.channel_number,channel.channel_info.get("unitCount",1))
            session_id = self.get_session_id()
            payload["sessionID"] = session_id
            if wait_for_response:
                self.response_events[session_id] = asyncio.Event()
            else:
                session_id = ""
            await self.async_publish(topic=topic,payload=payload,session_id=session_id)

    async def _get_channel_status(self,channel_number):
        channel = self.channels.get(channel_number,{})
        topic = self.topics.channel_status_req()
        payload = self.messages.channel_status(channel.channel_number,channel.channel_info.get("unitCount",1))
        session_id = self.get_session_id()
        payload["sessionID"] = session_id
        self.response_events[session_id] = asyncio.Event()
        await self.async_publish(topic=topic,payload=payload,session_id=session_id)

    async def _power_command(self,state,channel_number):
        state_num = 2
        if state:
            state_num = 1
        topic = self.topics.control()
        payload = self.messages.power(state_num, channel_number)
        session_id = self.get_session_id()
        payload["sessionID"] = session_id
        self.response_events[session_id] = asyncio.Event()
        await self.async_publish(topic=topic,payload=payload,session_id=session_id)
        await self._get_channel_status(channel_number)

    async def _hot_button_command(self,state,channel_number):
        state_num = 2
        if state:
            state_num = 1
        topic = self.topics.control()
        payload = self.messages.hot_button(state_num, channel_number)
        session_id = self.get_session_id()
        payload["sessionID"] = session_id
        self.response_events[session_id] = asyncio.Event()
        await self.async_publish(topic=topic,payload=payload,session_id=session_id)
        await self._get_channel_status(channel_number)

    async def _temperature_command(self,temp,channel_number):
        topic = self.topics.control()
        payload = self.messages.temperature(temp, channel_number)
        session_id = self.get_session_id()
        payload["sessionID"] = session_id
        self.response_events[session_id] = asyncio.Event()
        await self.async_publish(topic=topic,payload=payload,session_id=session_id)
        await self._get_channel_status(channel_number)

    def get_session_id(self):
        return str(int(round((datetime.utcnow() - datetime(1970, 1, 1)).total_seconds()*1000)))

    def async_handle_channel_info(self, client, userdata, message):
        response = json.loads(message.payload)
        channel_info = response.get("response",{})
        session_id = response.get("sessionID","unknown")
        self.channels = {channel.get("channelNumber",0):NavilinkChannel(channel.get("channelNumber",0),channel.get("channel",{}),self) for channel in channel_info.get("channelInfo",{}).get("channelList",[])}
        if response_event := self.response_events.get(session_id,None):
            response_event.set()

    def handle_channel_info(self, client, userdata, message):
        self.loop.call_soon_threadsafe(self.async_handle_channel_info, client, userdata, message)

    def async_handle_channel_status(self, client, userdata, message):
        response = json.loads(message.payload)
        channel_status = response.get("response",{}).get("channelStatus",{})
        session_id = response.get("sessionID","unknown")
        if channel := self.channels.get(channel_status.get("channelNumber",0),None):
            channel.update_channel_status(channel_status.get("channel",{}))
        if response_event := self.response_events.get(session_id,None):
            response_event.set()

    def handle_channel_status(self, client, userdata, message):
        self.loop.call_soon_threadsafe(self.async_handle_channel_status, client, userdata, message)

    def handle_weekly_schedule(self, client, userdata, message):
        _LOGGER.info("WEEKLY SCHEDULE: " + message.payload.decode('utf-8') + '\n')

    def handle_simple_trend(self, client, userdata, message):
        _LOGGER.info("SIMPLE TREND: " + message.payload.decode('utf-8') + '\n')

    def handle_hourly_trend(self, client, userdata, message):
        _LOGGER.info("HOURLY TREND: " + message.payload.decode('utf-8') + '\n')

    def handle_daily_trend(self, client, userdata, message):
        _LOGGER.info("DAILY TREND: " + message.payload.decode('utf-8') + '\n')

    def handle_monthly_trend(self, client, userdata, message):
        _LOGGER.info("MONTHLY TREND: " + message.payload.decode('utf-8') + '\n')

    def handle_other(self, client, userdata, message):
        _LOGGER.info(message.payload.decode('utf-8') + '\n')

class NavilinkChannel:

    def __init__(self, channel_number, channel_info, hub) -> None:
        self.channel_number = channel_number
        self.channel_info = self.convert_channel_info(channel_info)
        self.hub = hub
        self.callbacks = []
        self.channel_status = {}
        self.unit_list = {}
        self.waiting_for_response = False

    def register_callback(self,callback):
        self.callbacks.append(callback)

    def deregister_callback(self,callback):
        if self.callbacks:
            self.callbacks.pop(self.callbacks.index(callback))

    def update_channel_status(self,channel_status):
        self.channel_status = self.convert_channel_status(channel_status)
        if not self.waiting_for_response:
            self.publish_update()

    def publish_update(self):
        if len(self.callbacks) > 0:
            [callback() for callback in self.callbacks]

    async def set_power_state(self,state):
        if not self.waiting_for_response:
            self.waiting_for_response = True
            await self.hub._power_command(state,self.channel_number)
            self.publish_update()
            self.waiting_for_response = False

    async def set_hot_button_state(self,state):
        if not self.waiting_for_response:
            self.waiting_for_response = True
            await self.hub._hot_button_command(state,self.channel_number)
            self.publish_update()
            self.waiting_for_response = False

    async def set_temperature(self,temp):
        if not self.waiting_for_response:
            self.waiting_for_response = True
            await self.hub._temperature_command(temp,self.channel_number)
            self.publish_update()
            self.waiting_for_response = False

    def convert_channel_status(self,channel_status):
        channel_status["powerStatus"] = channel_status["powerStatus"] == 1
        channel_status["onDemandUseFlag"] = channel_status["onDemandUseFlag"] == 1
        channel_status["avgCalorie"] = channel_status["avgCalorie"]/2.0
        if self.channel_info.get("temperatureType",2) == TemperatureType.CELSIUS.value:
            if channel_status["unitType"] in [DeviceSorting.NFC.value,DeviceSorting.NCB_H.value,DeviceSorting.NFB.value,DeviceSorting.NVW.value,]:
                GIUFactor = 100
            else:
                GIUFactor = 10

            if channel_status["unitType"] in [
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
                channel_status["DHWSettingTemp"] = round(channel_status["DHWSettingTemp"] / 2.0, 1)
                channel_status["avgInletTemp"] = round(channel_status["avgInletTemp"] / 2.0, 1)
                channel_status["avgOutletTemp"] = round(channel_status["avgOutletTemp"] / 2.0, 1)            
                for i in range(channel_status.get("unitCount",0)):
                    channel_status["unitInfo"]["unitStatusList"][i]["gasInstantUsage"] = round((channel_status["unitInfo"]["unitStatusList"][i]["gasInstantUsage"] * GIUFactor)/ 10.0, 1)
                    channel_status["unitInfo"]["unitStatusList"][i]["accumulatedGasUsage"] = round(channel_status["unitInfo"]["unitStatusList"][i]["accumulatedGasUsage"] / 10.0, 1)
                    channel_status["unitInfo"]["unitStatusList"][i]["DHWFlowRate"] = round(channel_status["unitInfo"]["unitStatusList"][i]["DHWFlowRate"] / 10.0, 1)
                    channel_status["unitInfo"]["unitStatusList"][i]["currentOutletTemp"] = round(channel_status["unitInfo"]["unitStatusList"][i]["currentOutletTemp"] / 2.0, 1)
                    channel_status["unitInfo"]["unitStatusList"][i]["currentInletTemp"] = round(channel_status["unitInfo"]["unitStatusList"][i]["currentInletTemp"] / 2.0, 1)
        elif self.channel_info.get("temperatureType",2) == TemperatureType.FAHRENHEIT.value:
            if channel_status["unitType"] in [DeviceSorting.NFC.value,DeviceSorting.NCB_H.value,DeviceSorting.NFB.value,DeviceSorting.NVW.value,]:
                GIUFactor = 10
            else:
                GIUFactor = 1

            if channel_status["unitType"] in [
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
                for i in range(channel_status.get("unitCount",0)):
                    channel_status["unitInfo"]["unitStatusList"][i]["gasInstantUsage"] = round(channel_status["unitInfo"]["unitStatusList"][i]["gasInstantUsage"] * GIUFactor * 3.968, 1)
                    channel_status["unitInfo"]["unitStatusList"][i]["accumulatedGasUsage"] = round(channel_status["unitInfo"]["unitStatusList"][i]["accumulatedGasUsage"] * 35.314667 / 10.0, 1)
                    channel_status["unitInfo"]["unitStatusList"][i]["DHWFlowRate"] = round(channel_status["unitInfo"]["unitStatusList"][i]["DHWFlowRate"] / 37.85, 1)

        return channel_status

    def convert_channel_info(self,channel_info):
        if channel_info.get("temperatureType",2) == TemperatureType.CELSIUS.value:
            channel_info["setupDHWTempMin"] = round(channel_info["setupDHWTempMin"]/ 2.0, 1)
            channel_info["setupDHWTempMax"] = round(channel_info["setupDHWTempMax"]/ 2.0, 1)

        return channel_info
        
    def is_available(self):
        return self.hub.connected

class Topics:

    def __init__(self, user_info, device_info, client_id) -> None:
        self.user_seq = str(user_info.get("userInfo",{}).get("userSeq",""))
        self.mac_address = device_info.get("deviceInfo",{}).get("macAddress","")
        self.home_seq = str(device_info.get("deviceInfo",{}).get("homeSeq",""))
        self.device_type = str(device_info.get("deviceInfo",{}).get("deviceType",""))
        self.client_id = client_id
        self.req = f'cmd/{self.device_type}/navilink-{self.mac_address}/'
        self.res = f'cmd/{self.device_type}/{self.home_seq}/{self.user_seq}/{self.client_id}/res/'

    def start(self):
        return self.req + 'status/start'

    def channel_info_sub(self):
        return self.req + 'res/channelinfo'

    def channel_info_res(self):
        return self.res + 'channelinfo'
    
    def control_fail(self):
        return self.req + 'res/controlfail'
    
    def channel_status_sub(self):
        return self.req + 'res/channelstatus'

    def channel_status_req(self):
        return self.req + 'status/channelstatus'

    def channel_status_res(self):
        return self.res + 'channelstatus'

    def weekly_schedule_sub(self):
        return self.req + 'res/weeklyschedule'

    def weekly_schedule_req(self):
        return self.req + 'status/weeklyschedule'

    def weekly_schedule_res(self):
        return self.res + 'weeklyschedule'

    def simple_trend_sub(self):
        return self.req + 'res/simpletrend'

    def simple_trend_req(self):
        return self.req + 'status/simpletrend'

    def simple_trend_res(self):
        return self.res + 'simpletrend'

    def hourly_trend_sub(self):
        return self.req + 'res/hourlytrend'

    def hourly_trend_req(self):
        return self.req + 'status/hourlytrend'

    def hourly_trend_res(self):
        return self.res + 'hourlytrend'

    def daily_trend_sub(self):
        return self.req + 'res/dailytrend'

    def daily_trend_req(self):
        return self.req + 'status/dailytrend'

    def daily_trend_res(self):
        return self.res + 'dailytrend'

    def monthly_trend_sub(self):
        return self.req + 'res/monthlytrend'

    def monthly_trend_req(self):
        return self.req + 'status/monthlytrend'

    def monthly_trend_res(self):
        return self.res + 'monthlytrend'

    def control(self):
        return self.req + 'control'

    def connection(self):
        return self.req + 'connection'

    def disconnect(self):
        return 'evt/+/mobile/event/disconnect-mqtt'

    def app_connection(self):
        return f'evt/1/navilink-{self.mac_address}/app-connection'

class Messages:

    def __init__(self, device_info, client_id, topics) -> None:
        self.mac_address = device_info.get("deviceInfo",{}).get("macAddress","")
        self.device_type = int(device_info.get("deviceInfo",{}).get("deviceType",1))
        self.additional_value = device_info.get("deviceInfo",{}).get("additionalValue","")   
        self.client_id = client_id
        self.topics = topics

    def channel_info(self):
        return {
            "clientID": self.client_id,
            "protocolVersion":1,
            "request":{"additionalValue":self.additional_value,"command":16777217,"deviceType":self.device_type,"macAddress":self.mac_address},
            "requestTopic":self.topics.start(),
            "responseTopic":self.topics.channel_info_res(),
            "sessionID":""
        }

    def channel_status(self,channel_number,unit_count):
        return {
            "clientID": self.client_id,
            "protocolVersion":1,
            "request":{"additionalValue":self.additional_value,"command":16777220,"deviceType":self.device_type,"macAddress":self.mac_address,"status":{"channelNumber":channel_number,"unitNumberEnd":unit_count,"unitNumberStart":1}},
            "requestTopic": self.topics.channel_status_req(),
            "responseTopic": self.topics.channel_status_res(),
            "sessionID": ""
        }

    def power(self, state, channel_number):
        return {
            "clientID": self.client_id,
            "protocolVersion":1,
            "request":{"additionalValue":self.additional_value,"command":33554433,"control":{"channelNumber":channel_number,"mode":"power","param":[state]},"deviceType":self.device_type,"macAddress":self.mac_address},
            "requestTopic": self.topics.control(),
            "responseTopic": self.topics.channel_status_res(),
            "sessionID": ""
        }

    def hot_button(self, state, channel_number):
        return {
            "clientID": self.client_id,
            "protocolVersion":1,
            "request":{"additionalValue":self.additional_value,"command":33554437,"control":{"channelNumber":channel_number,"mode":"onDemand","param":[state]},"deviceType":self.device_type,"macAddress":self.mac_address},
            "requestTopic": self.topics.control(),
            "responseTopic": self.topics.channel_status_res(),
            "sessionID": ""
        }

    def temperature(self, temp, channel_number):
        return {
            "clientID": self.client_id,
            "protocolVersion":1,
            "request":{"additionalValue":self.additional_value,"command":33554435,"control":{"channelNumber":channel_number,"mode":"DHWTemperature","param":[temp]},"deviceType":self.device_type,"macAddress":self.mac_address},
            "requestTopic": self.topics.control(),
            "responseTopic": self.topics.channel_status_res(),
            "sessionID": ""
        }

    def last_will(self):
        return {
            "clientID": self.client_id,
            "event":{"additionalValue":self.additional_value,"connection":{"os":"A","status":0},"deviceType":self.device_type,"macAddress":self.mac_address},
            "protocolVersion":1,
            "requestTopic": self.topics.app_connection(),
            "sessionID": ""
        }

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

class UnableToConnect(Exception):
    """Unable to connect to Navien Server Error"""

class UserNotFound(Exception):
    """Bad User Credentials Error"""

class NoNavienDevices(Exception):
    """No Navien Devices Found Error"""

class NoNetworkConnection(Exception):
    """Network is unavailable"""

class NoResponseData(Exception):
    """No Data in Response"""

class PollingError(Exception):
    """Error during polling"""

class DisconnectEvent(Exception):
    """Server disconnected"""

class NoChannelInformation(Exception):
    """No Channel Information"""

class NoAccessKey(Exception):
    """Access key, Secret key, or Session token missing"""
