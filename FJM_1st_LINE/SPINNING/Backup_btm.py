import os
import time
import json
import random
import paho.mqtt.client as mqtt
import schedule
import minimalmodbus
import logging
from pyModbusTCP.client import ModbusClient
import datetime
import serial
import serial.tools.list_ports
from database import DBHelper
import logging.handlers
from logging.handlers import TimedRotatingFileHandler
from conversions import word_list_to_long, f_list, decode_ieee
from statistics import mean

GL_AV_PRESSURE_HEAT = []
GL_AV_PRESSURE_CUTTING = []
GL_AV_PNG_PRESSURE = []
GL_AV_PROPANE_PRESSURE = []
GL_AV_DAACETYLENE_PRESSURE = []
GL_AV_FORMING_TEMP = []
GL_AV_HYDROLIC_POWER_PACK = []

# if values under threshold
GL_MAX_DAACETYLENE_PRESSURE = 0

# region Rotating Logs
dirname = os.path.dirname(os.path.abspath(__file__))

log_level = logging.INFO
#
FORMAT = "%(asctime)-15s %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s"

logFormatter = logging.Formatter(FORMAT)
log = logging.getLogger("LOGS")

# checking and creating logs directory here
if not os.path.isdir("./logs"):
    log.info("[-] logs directory doesn't exists")
    try:
        os.mkdir("./logs")
        log.info("[+] Created logs dir successfully")
    except Exception as e:
        log.error(f"[-] Can't create dir logs Error: {e}")

fileHandler = TimedRotatingFileHandler(
    os.path.join(dirname, f"logs/app_log"), when="midnight", interval=1
)

# fileHandler = TimedRotatingFileHandler(f"D:/HIS_LOGS", when='midnight', interval=1)
fileHandler.setFormatter(logFormatter)
fileHandler.suffix = "%Y-%m-%d.log"
log.addHandler(fileHandler)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
log.addHandler(consoleHandler)
log.setLevel(log_level)
# endregion

GL_MACHINE_INFO = {
    "Bottom Spinning": {
        "pub_topic": "STG004",
        "sub_topic": "TRIGGER_STG004",
        "energy_topic": "bottom_spinning_em",
        "param_list": [
            "inductionTemperature",
            "O2PressureHeating",
            "O2PressureCutting",
            "PNGPressure",
            "propanePressure",
            "DAAcetylenePressure",
            "energyConsumption",
            "formingTemperature",
            "hydraulicPowerPack",
        ],
        "ip": "192.168.33.45",
        "machine_id": "01",
        "stage": "BSPN",
        "line": "A",
    },
    "Neck Spinning": {
        "pub_topic": "STG007",
        "sub_topic": "TRIGGER_STG007",
        "energy_topic": "neck_spinning_em",
        "param_list": [
            "inductionTemperature",
            "O2PressureHeating",
            "O2PressureCutting",
            "PNGPressure",
            "propanePressure",
            "DAAcetylenePressure",
            "energyConsumption",
            "formingTemperature",
            "hydraulicPowerPack",
        ],
        "ip": "192.168.33.45",
        "machine_id": "01",
        "stage": "NSPN",
        "line": "A",
    },
}

GL_MACHINE_NAME = ""  # These variables will be initialized by init_conf
STAGE = ""
LINE = ""
MACHINE_ID = ""
GL_IP = ""
GL_U_ID = 1
GL_PARAM_LIST = []  # These variables will be initialized by init_conf
# endregion

# region MQTT params
MQTT_BROKER = "ec2-13-232-172-215.ap-south-1.compute.amazonaws.com"
MQTT_BROKER1 = "192.168.33.150"
MQTT_PORT = 1883
USERNAME = "mmClient"
PASSWORD = "ind4.0#2023"
GL_CLIENT_ID = f"HIS-MQTT-{random.randint(0, 1000)}"

PUBLISH_TOPIC = ""  # These variables will be initialized by init_conf
TRIGGER_TOPIC = ""  # These variables will be initialized by init_conf
ENERGY_TOPIC = ""  # These variables will be initialized by init_conf
# endregion

ob_db = DBHelper()  # Object for DBHelper database class

# region Program Global Variables
FL_FIRST_CYCLE_RUN = True
FL_PREV_STATUS = False
GL_WAIT_CYCLE = False
FL_STATUS = False
GL_SEND_DATA = True
GL_SERIAL_NUMBER = ""

GL_INDUCTION_TEMP = 0
GL_O2_PRESSURE_HEAT = 0
GL_PRESSURE_CUTTING = 0
GL_PNG_PRESSURE = 0
GL_PROPANE_PRESSURE = 0
GL_PRESSURE_HEAT = 0
GL_DAACETYLENE_PRESSURE = 0
GL_HYDROLIC_POWER_PACK = 0
GL_FORMING_TEMP = 0
GL_CURRENT_KWH = 0
GL_PREV_KWH = 0
power_consumption = 0
GL_MAX_POWER_CONSUMPTION = 0
GL_MAX_PRESSURE_HEATING = 0
GL_MAX_PRESSURE_CUTTING = 0
# average global parameters
GL_PRESSURE_HEAT_AVG = 0
GL_PRESSURE_CUTTING_AVG = 0
GL_PROPANE_PRESSURE_AVG = 0
GL_DAACETYLENE_PRESSURE_AVG = 0
GL_HYDROLIC_POWER_PACK_AVG = 0
GL_FORMING_TEMP_AVG = 0
GL_SERIAL_TOPIC = 'Acknowledgements'
GL_SERIAL_NUMBER_LIST = ""
GL_PREV_CYCL_START = time.time()


# endregion


# region Initialising Configuration here
def init_conf():
    global GL_MACHINE_NAME, GL_PARAM_LIST, PUBLISH_TOPIC, TRIGGER_TOPIC, ENERGY_TOPIC, GL_IP
    global MACHINE_ID, LINE, STAGE
    if not os.path.isdir("./conf"):
        log.info("[-] conf directory doesn't exists")
        try:
            os.mkdir("./conf")
            log.info("[+] Created conf dir successfully")
        except Exception as e:
            pass
            log.error(f"[-] Can't create conf dir Error: {e}")

    try:
        with open("./conf/machine_config.conf", "r") as f:
            data = f.readline().replace("\n", "")
            data = {data.split("=")[0]: data.split("=")[1]}
            print(data)
            print(type(data))

            GL_MACHINE_NAME = data["m_name"]
            GL_PARAM_LIST = GL_MACHINE_INFO[GL_MACHINE_NAME]["param_list"]  # para
            PUBLISH_TOPIC = GL_MACHINE_INFO[GL_MACHINE_NAME]["pub_topic"]
            TRIGGER_TOPIC = GL_MACHINE_INFO[GL_MACHINE_NAME]["sub_topic"]
            ENERGY_TOPIC = GL_MACHINE_INFO[GL_MACHINE_NAME]["energy_topic"]
            MACHINE_ID = GL_MACHINE_INFO[GL_MACHINE_NAME]["machine_id"]
            STAGE = GL_MACHINE_INFO[GL_MACHINE_NAME]["stage"]
            LINE = GL_MACHINE_INFO[GL_MACHINE_NAME]["line"]
            GL_IP = GL_MACHINE_INFO[GL_MACHINE_NAME]["ip"]
            print(f"[+] Machine_name is {GL_MACHINE_NAME}")
    except FileNotFoundError as e:
        log.error(f"[-] machine_config.conf not found {e}")
        with open("./conf/machine_config.conf", "w") as f:
            data = "m_name=NO_MACHINE"
            f.write(data)


log.info(f"[+] Initialising configuration")
init_conf()
log.info(f"[+] Machine is {GL_MACHINE_NAME}")
log.info(f"[+] Machine IP is {GL_IP}")
log.info(f"[+] Publish topic is {PUBLISH_TOPIC}")
log.info(f"[+] Trigger topic is {TRIGGER_TOPIC}")
log.info(f"[+] Energy topic is {ENERGY_TOPIC}")


# endregion

# region Machine Specific functions


def get_serial_port():
    try:
        ports = serial.tools.list_ports.comports()
        usb_ports = [p.device for p in ports if "USB" in p.description]
        log.info(usb_ports)
        if len(usb_ports) < 1:
            raise Exception("Could not find USB ports")
        return usb_ports[0]
    except Exception as e:
        log.error(f"[-] Error Can't Open Port {e}")
        return None


def initiate_modbus(slaveId):
    com_port = None
    for i in range(5):
        com_port = get_serial_port()
        if com_port:
            break
    i = int(slaveId)
    instrument = minimalmodbus.Instrument(com_port, i)
    instrument.serial.baudrate = 19200
    instrument.serial.bytesize = 8
    instrument.serial.parity = serial.PARITY_NONE
    instrument.serial.stopbits = 1
    instrument.serial.timeout = 3
    instrument.serial.close_after_each_call = True
    log.info("Modbus ID Initialized: " + str(i))
    return instrument


def get_machine_data():
    try:
        data_list = []
        param_list = [
            "O2PressureHeating//",
            "O2PressureHeating",
            "propanePressure//",
            "propanePressure",

            "O2PressureCutting//",
            "O2PressureCutting",
            "DAAcetylenePressure",
            "hydraulicPowerPack",

            "formingTemperature",
        ]

        for slave_id in [1, 2, 3]:
            log.info(f"[+] Getting data for slave id {slave_id}")
            reg_len = 4
            if slave_id == 3:
                reg_len = 1
            try:
                data = None
                for i in range(5):
                    mb_client = initiate_modbus(slave_id)
                    data = mb_client.read_registers(0, reg_len, 4)
                    if data:
                        break
                log.info(f"Got data {data}")
                if data is None:
                    for i in range(reg_len):
                        data_list.append(0)

                else:
                    data_list += data

            except Exception as e:
                log.error(f"[+] Failed to get data {e} slave id {slave_id}")
                for i in range(reg_len):
                    data_list.append(0)

        log.info(f"[*] Got data {data_list}")

        payload = {}
        for index, key in enumerate(param_list):
            payload[key] = data_list[index]

        payload["inductionTemperature"] = 0
        return payload


    except Exception as e:
        log.error(e)


def Connection():
    c = ModbusClient(host='192.168.33.45', port=510, unit_id=1, auto_open=True)
    return c


def Reading_data():
    try:
        c = Connection()
        regs = c.read_holding_registers(0, 5)
        log.info(f"values from register is {regs}")
        c.close()
        if not regs:
            a = [0, 0, 0, 0, 0]
            return a
        else:
            return regs
    except Exception as err:
        log.error(f'Error PLC disconnected {err}')


def on_message(client_, userdata, message):
    global GL_CURRENT_KWH, GL_SERIAL_NUMBER_LIST

    log.info(f"[+] Received message {str(message.payload.decode('utf-8'))}")
    log.info(f"[+] From topic {message.topic}")

    # if got message from the trigger topic run the main function and send the message
    data = json.loads(message.payload)
    log.info(f"[+] Data is {data}")

    if message.topic == TRIGGER_TOPIC:  # if message is from trigger topic for serial number

        if data is not None:
            if data.get("line") == 'A':
                GL_SERIAL_NUMBER_LIST = data.get("serialNumber")
                log.info(f"serial_number list is {GL_SERIAL_NUMBER_LIST}")

    elif message.topic == ENERGY_TOPIC:  # if message is from energy meter then update the energy value
        if data is not None:
            GL_CURRENT_KWH = data.get('energy')
            print(f"current kwh is {GL_CURRENT_KWH}")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to MQTT Broker!")
        client.subscribe(PUBLISH_TOPIC)
        client.subscribe(TRIGGER_TOPIC)
        client.subscribe(ENERGY_TOPIC)

    else:
        log.error("Failed to connect, return code %d\n", rc)


def try_connect_mqtt():
    client_mqtt = mqtt.Client(GL_CLIENT_ID)
    client_mqtt.on_connect = on_connect
    client_mqtt.on_message = on_message
    client_mqtt.username_pw_set(USERNAME, PASSWORD)
    for i in range(5):
        try:
            client_mqtt.connect(
                MQTT_BROKER,
                MQTT_PORT,
                clean_start=mqtt.MQTT_CLEAN_START_FIRST_ONLY,
                keepalive=60,
            )
            if client_mqtt.is_connected():
                break
        except Exception as e:
            log.error(f"[-] Unable to connect to mqtt broker {e}")
    try:
        client_mqtt.loop_start()
    except Exception as e:
        log.error(f"[-] Error while starting loop {e}")
    return client_mqtt


def publish_values(payload):
    global ob_client_mqtt
    payload_str = json.dumps(payload)
    log.info(f"{payload_str}")

    if GL_SEND_DATA:
        result = [None, None]  # set the result to None
        try:
            result = ob_client_mqtt.publish(
                PUBLISH_TOPIC, payload_str, qos=2
            )  # try to publish the data
            log.info(f"{result}")
        except:  # if publish gives exception
            try:
                ob_client_mqtt.disconnect()  # try to disconnect the client
                log.info(f"[+] Disconnected from Broker")
                time.sleep(2)
            except:
                pass
            if not ob_client_mqtt.is_connected():  # if client is not connected
                log.info(f"[+] Retrying....")
                for _ in range(5):
                    ob_client_mqtt = (
                        try_connect_mqtt()
                    )  # retry to connect to the broker
                    time.sleep(1)
                    if ob_client_mqtt.is_connected():  # if connected: break
                        break
        # result: [0, 1]
        status = result[0]
        log.info(f"{status}")
        if status == 0:  # if status is 0 (ok)
            log.info(f"[+] Send `{result}` to topic `{PUBLISH_TOPIC}`")
            sync_data = (
                ob_db.get_sync_data()
            )  # get all the data from the sync payload db
            if sync_data:  # if sync_data present
                for i in sync_data:  # for every payload
                    if i:  # if payload is not empty
                        ts = i.get("ts")  # save timestamp
                        sync_payload = json.dumps(i.get("payload"))
                        sync_result = ob_client_mqtt.publish(PUBLISH_TOPIC, sync_payload, qos=2
                                                             )  # send payload
                        if (sync_result[0] == 0):  # if payload sent successful remove that payload from db
                            ob_db.clear_sync_data(ts)
                        else:  # else break from the loop
                            log.error("[-] Can't send sync_payload")
                            break
        else:
            log.error(f"[-] Failed to send message to topic {PUBLISH_TOPIC}")
            ob_db.add_sync_data(payload)  # if status is not 0 (ok) then add the payload to the database


# endregion
def try_connect_mqtt1():
    client_mqtt = mqtt.Client(GL_CLIENT_ID)
    client_mqtt.on_connect = on_connect
    client_mqtt.on_message = on_message
    client_mqtt.username_pw_set(USERNAME, PASSWORD)
    for i in range(5):
        try:
            client_mqtt.connect(
                MQTT_BROKER1,
                MQTT_PORT,
                clean_start=mqtt.MQTT_CLEAN_START_FIRST_ONLY,
                keepalive=60,
            )
            if client_mqtt.is_connected():
                break
        except Exception as e:
            log.error(f"[-] Unable to connect to mqtt broker {e}")
    try:
        client_mqtt.loop_start()
    except Exception as e:
        log.error(f"[-] Error while starting loop {e}")
    return client_mqtt


def publish_values1(payload):
    global ob_client_mqtt1
    payload_str = json.dumps(payload)
    log.info(f"{payload_str}")

    if GL_SEND_DATA:
        result = [None, None]  # set the result to None
        try:
            result = ob_client_mqtt1.publish(PUBLISH_TOPIC, payload_str, qos=2)  # try to publish the data
        except:  # if publish gives exception
            try:
                ob_client_mqtt1.disconnect()  # try to disconnect the client
                log.info(f"[+] Disconnected from Broker")
                time.sleep(2)
            except:
                pass
            if not ob_client_mqtt1.is_connected():  # if client is not connected
                log.info(f"[+] Retrying....")
                for _ in range(5):
                    ob_client_mqtt1 = (try_connect_mqtt1())  # retry to connect to the broker
                    time.sleep(1)
                    if ob_client_mqtt1.is_connected():  # if connected: break
                        break
        # result: [0, 1]
        status = result[0]
        if status == 0:  # if status is 0 (ok)
            log.info(f"[+] Send `{result}` to topic `{PUBLISH_TOPIC}`")
            sync_data = (ob_db.get_sync_data2())  # get all the data from the sync payload db
            if sync_data:  # if sync_data present
                for i in sync_data:  # for every payload
                    if i:  # if payload is not empty
                        ts = i.get("ts")  # save timestamp
                        sync_payload = json.dumps(i.get("payload"))
                        sync_result = ob_client_mqtt1.publish(PUBLISH_TOPIC, sync_payload, qos=2)  # send payload
                        if (sync_result[0] == 0):  # if payload sent successful remove that payload from db
                            ob_db.clear_sync_data2(ts)
                        else:  # else break from the loop
                            log.error("[-] Can't send sync_payload")
                            break
        else:
            log.error(f"[-] Failed to send message to topic {PUBLISH_TOPIC}")
            ob_db.add_sync_data2(
                payload
            )  # if status is not 0 (ok) then add the payload to the database


# endregion


def publish_values2(payload):
    global ob_client_mqtt1
    payload_str = json.dumps(payload)
    log.info(f"{payload_str}")

    if GL_SEND_DATA:
        result = [None, None]  # set the result to None
        try:
            result = ob_client_mqtt1.publish(
                GL_SERIAL_TOPIC, payload_str, qos=2
            )  # try to publish the data
        except:  # if publish gives exception
            try:
                ob_client_mqtt1.disconnect()  # try to disconnect the client
                log.info(f"[+] Disconnected from Broker")
                time.sleep(2)
            except:
                pass
            if not ob_client_mqtt1.is_connected():  # if client is not connected
                log.info(f"[+] Retrying....")
                for _ in range(5):
                    ob_client_mqtt1 = (
                        try_connect_mqtt1()
                    )  # retry to connect to the broker
                    time.sleep(1)
                    if ob_client_mqtt1.is_connected():  # if connected: break
                        break
        # result: [0, 1]
        status = result[0]
        if status == 0:  # if status is 0 (ok)
            log.info(f"[+] Send `{result}` to topic `{GL_SERIAL_TOPIC}`")
            sync_data = (
                ob_db.get_sync_data2()
            )  # get all the data from the sync payload db
            if sync_data:  # if sync_data present
                for i in sync_data:  # for every payload
                    if i:  # if payload is not empty
                        ts = i.get("ts")  # save timestamp
                        sync_payload = json.dumps(i.get("values"))
                        sync_result = ob_client_mqtt1.publish(
                            GL_SERIAL_TOPIC, sync_payload, qos=2
                        )  # send payload
                        if (
                                sync_result[0] == 0
                        ):  # if payload sent successful remove that payload from db
                            ob_db.clear_sync_data2(ts)
                        else:  # else break from the loop
                            log.error("[-] Can't send sync_payload")
                            break
        else:
            log.error(f"[-] Failed to send message to topic {GL_SERIAL_TOPIC}")


def get_unknown_serial(line, stage, machine_id):
    stage = "{0:0>4}".format(stage)
    date_ = datetime.datetime.now()
    jd = date_.timetuple().tm_yday
    yr = date_.strftime("%y")
    dt = date_.strftime("%H%M%S")
    return f"U{line}{stage}{machine_id}{yr}{jd}{dt}"


# region for testing only

prev_time = time.time()


def get_status():
    global prev_time, status, tb_len, sqness
    if (time.time() - prev_time) > 130:
        GL_WAIT_CYCLE = True
        prev_time = time.time()
        return GL_WAIT_CYCLE


# endregion till here

if __name__ == "__main__":
    # ob_client_mqtt = try_connect_mqtt()
    ob_client_mqtt1 = try_connect_mqtt1()
    Threshold_forming_temp = 850
    MAX_VALUE = 1500
    End_thresh = 700
    while True:
        try:
            if GL_SERIAL_NUMBER_LIST:
                ob_db.enqueue_serial_number(GL_SERIAL_NUMBER_LIST)
                log.info(f"[+] Enqueueing serial number to db {GL_SERIAL_NUMBER_LIST}")

                if GL_SERIAL_NUMBER_LIST:
                    values = {
                        "topic": "TRIGGER_STG004",
                        "message": {
                            "currentStage": "STG004",
                            "serialNumber": GL_SERIAL_NUMBER_LIST,
                            "line": "A",
                            "model": "Y9T"
                        }, }

                    publish_values2(values)
                GL_SERIAL_NUMBER_LIST = ""
            data = get_machine_data()
            Cycle_time = 0
            log.info(f"[+] Data is {data}")
            prev_cycletime = time.time()
            status = Reading_data()
            log.info(f'status from plc is {status}')
            if data:
                if FL_FIRST_CYCLE_RUN:
                    FL_FIRST_CYCLE_RUN = False
                if status[1]:
                    FL_STATUS = True
                    try:
                        if (950 <= data.get("formingTemperature") <= 1200):
                            GL_AV_FORMING_TEMP.append(data.get("formingTemperature"))
                    except Exception as e:
                        log.error(f"[-] Error in GL_MAX_FORMING_TEMP {e}")

                    try:
                        if data.get("inductionTemperature") > GL_INDUCTION_TEMP:
                            GL_INDUCTION_TEMP = data.get("inductionTemperature")
                    except Exception as e:
                        log.error(f"[-] Error in inductionTemperature {e}")
                    try:
                        if 1 <= data.get("O2PressureHeating//") / 100 <= 3:
                            GL_AV_PRESSURE_HEAT.append(data.get("O2PressureHeating//") / 100)
                        elif GL_MAX_PRESSURE_HEATING < data.get("O2PressureHeating//") / 100 < 1:
                            GL_MAX_PRESSURE_HEATING = data.get("O2PressureHeating//") / 100

                    except Exception as e:
                        log.error(f"[-] Error in O2PressureHeating {e}")

                    try:
                        if (1 <= data.get("O2PressureCutting") / 100 <= 6):
                            GL_AV_PRESSURE_CUTTING.append(data.get("O2PressureCutting") / 100)
                        elif GL_MAX_PRESSURE_CUTTING < data.get("O2PressureCutting") / 100 < 4:
                            GL_MAX_PRESSURE_CUTTING = data.get("O2PressureCutting") / 100

                    except Exception as e:
                        log.error(f"[-] Error in O2PressureCutting {e}")

                    try:
                        if data.get("propanePressure") == 65535:
                            propanePressure = 0
                        else:
                            propanePressure = data.get("propanePressure") / 100

                        if 0.1 <= propanePressure <= 1.5:
                            GL_AV_PROPANE_PRESSURE.append(propanePressure)


                    except Exception as e:
                        log.error(f"[-] Error in propanePressure {e}")

                    try:
                        if data.get("DAAcetylenePressure") > 1000:
                            log.info(
                                f'[+]------------------value is more then 60000 <{data.get("DAAcetylenePressure")}')
                            DAAcetylenePressure = 0
                        else:
                            DAAcetylenePressure = data.get("DAAcetylenePressure") / 100

                        if 0.1 <= DAAcetylenePressure <= 0.5:
                            GL_AV_DAACETYLENE_PRESSURE.append(DAAcetylenePressure)
                        elif DAAcetylenePressure < 0.1:
                            GL_MAX_DAACETYLENE_PRESSURE = DAAcetylenePressure

                    except Exception as e:
                        log.error(f"[-] Error in DAAcetylenePressure {e}")

                    try:
                        if data.get("hydraulicPowerPack") > 160:
                            log.info(f'[+]-value is more then 160 < {data.get("hydraulicPowerPack")}')
                            hydraulicPowerPack = 157
                            GL_AV_HYDROLIC_POWER_PACK.append(hydraulicPowerPack)
                        else:
                            hydraulicPowerPack = data.get("hydraulicPowerPack")
                            if (130 <= data.get("hydraulicPowerPack") <= 160):
                                GL_AV_HYDROLIC_POWER_PACK.append(data.get("hydraulicPowerPack"))

                    except Exception as e:
                        log.error(f"[-] Error in hydraulicPowerPack {e}")
                    prev_cycletime = time.time()
                if not status[1]:
                    log.info(f"[+] Cycle Stopped")
                    GL_FORMING_TEMP = data.get("formingTemperature")
                    FL_STATUS = False

                log.info(f"GL_FORMING_TEMP {data.get('formingTemperature')}")
                log.info(f"GL_INDUCTION_TEMP {GL_INDUCTION_TEMP}")
                log.info(f"GL_PRESSURE_CUTTING {data.get('O2PressureCutting') / 100}")
                log.info(f"GL_PROPANE_PRESSURE {data.get('propanePressure') / 100}")
                log.info(f"GL_DAACETYLENE_PRESSURE {data.get('DAAcetylenePressure') / 100}")
                log.info(f"GL_HYDROLIC_POWER_PACK {data.get('hydraulicPowerPack')}")

                log.info(f'fl_prev status is {FL_PREV_STATUS}, fl status is {FL_STATUS}')
                if FL_PREV_STATUS != FL_STATUS:
                    log.info(f'fl_prev status is {FL_PREV_STATUS}, fl status is {FL_STATUS}')
                    serial_number = ob_db.get_first_serial_number()
                    log.info(serial_number)
                    if serial_number is None:
                        # serial_number = get_unknown_serial(LINE, STAGE, MACHINE_ID)
                        serial_number = "null1"
                        log.info(f"[+] Adding Unknown serial number to queue {serial_number}")
                        ob_db.enqueue_serial_number(serial_number)

                    payload = {
                        "stage": GL_MACHINE_NAME,
                        "timestamp": time.time(),
                        "serialNumber": serial_number,
                    }
                    log.info(f"{payload}")
                    if FL_STATUS:  # if cycle started if started then publish serial number only
                        log.info("[+] Cycle Running")
                        # print(payload)
                    if not FL_STATUS:  # if cycle ended then publish serial number with data
                        log.info(f"[+] Cycle Stopped")
                        power = GL_CURRENT_KWH - GL_PREV_KWH
                        if power > power_consumption:
                            power_consumption = power
                        GL_FORMING_TEMP_AVG = 0
                        GL_MAX_PNG_PRESSURE = 0
                        ob_db.save_running_data(
                            GL_INDUCTION_TEMP,
                            GL_PRESSURE_HEAT_AVG,
                            GL_PRESSURE_CUTTING_AVG,
                            GL_MAX_PNG_PRESSURE,
                            GL_PROPANE_PRESSURE_AVG,
                            GL_DAACETYLENE_PRESSURE_AVG,
                            GL_HYDROLIC_POWER_PACK_AVG,
                            GL_FORMING_TEMP_AVG,
                            serial_number,
                        )

                        try:
                            log.info(f"GL_AV_FORMING_TEMP {GL_AV_FORMING_TEMP}")
                            log.info(f"GL_AV_PRESSURE_HEAT {GL_AV_PRESSURE_HEAT}")
                            log.info(f"GL_AV_PRESSURE_CUTTING {GL_AV_PRESSURE_CUTTING}")
                            log.info(f"GL_AV_PNG_PRESSURE {GL_AV_PNG_PRESSURE}")
                            log.info(f"GL_AV_PROPANE_PRESSURE {GL_AV_PROPANE_PRESSURE}")
                            log.info(f"GL_AV_DAACETYLENE_PRESSURE {GL_AV_DAACETYLENE_PRESSURE}")
                            log.info(f"GL_AV_HYDROLIC_POWER_PACK {GL_AV_HYDROLIC_POWER_PACK}")

                            GL_FORMING_TEMP_AVG = max(GL_AV_FORMING_TEMP)
                            log.info(f'Average forming temp: {GL_FORMING_TEMP_AVG}')
                            if GL_AV_PRESSURE_HEAT:
                                GL_PRESSURE_HEAT_AVG = max(GL_AV_PRESSURE_HEAT)
                                log.info(f'Average pressure heat: {GL_PRESSURE_HEAT_AVG}')
                            else:
                                GL_PRESSURE_HEAT_AVG = GL_MAX_PRESSURE_HEATING
                                log.info(f'Pressure heat is : {GL_PRESSURE_HEAT_AVG}')
                            if GL_AV_PRESSURE_CUTTING:
                                GL_PRESSURE_CUTTING_AVG = max(GL_AV_PRESSURE_CUTTING)
                                log.info(f'Average pressure cutting: {GL_PRESSURE_CUTTING_AVG}')
                            else:
                                GL_PRESSURE_CUTTING_AVG = GL_MAX_PRESSURE_CUTTING
                                log.info(f"Pressure cutting is : {GL_PRESSURE_CUTTING_AVG}")
                            if GL_AV_HYDROLIC_POWER_PACK:
                                GL_HYDROLIC_POWER_PACK_AVG = max(GL_AV_HYDROLIC_POWER_PACK)
                                log.info(f'Average hydrolic power pack: {GL_HYDROLIC_POWER_PACK_AVG}')
                            else:
                                log.info('Hydrolic power pack is empty')
                            if GL_AV_PROPANE_PRESSURE:
                                GL_PROPANE_PRESSURE_AVG = max(GL_AV_PROPANE_PRESSURE)
                                log.info(f'Average propane pressure: {GL_PROPANE_PRESSURE_AVG}')
                            else:
                                log.info('Propane pressure is empty')
                            # log.info('average propane pressure', average)
                            if GL_AV_DAACETYLENE_PRESSURE:
                                GL_DAACETYLENE_PRESSURE_AVG = max(GL_AV_DAACETYLENE_PRESSURE)
                                log.info(f'Average Daacetylene pressure: {GL_DAACETYLENE_PRESSURE_AVG}')
                                # log.info('average daacetylene pressure', average)
                            else:
                                GL_DAACETYLENE_PRESSURE_AVG = GL_MAX_DAACETYLENE_PRESSURE

                        except Exception as e:
                            print(e)

                        payload["data"] = {
                            "inductionTemperature": GL_INDUCTION_TEMP,
                            "O2PressureHeating": GL_PRESSURE_HEAT_AVG,
                            "O2PressureCutting": GL_PRESSURE_CUTTING_AVG,
                            "propanePressure": GL_PROPANE_PRESSURE_AVG,
                            "DAAcetylenePressure": GL_DAACETYLENE_PRESSURE_AVG,
                            "formingTemperature": GL_FORMING_TEMP_AVG,
                            "hydraulicPowerPack": GL_HYDROLIC_POWER_PACK_AVG,
                            "powerConsumption": power_consumption,
                        }
                        # publish_values(payload)
                        # log.info(f"payload published is {payload} ")
                        publish_values1(payload)
                        log.info(f"payload published is {payload} ")
                        ob_db.delete_serial_number(serial_number)
                        log.info(f"serial number deleted")
                        Cycle_time = 0
                        GL_INDUCTION_TEMP = 0
                        GL_PRESSURE_HEAT_AVG = 0
                        GL_PRESSURE_CUTTING_AVG = 0
                        GL_PNG_PRESSURE = 0
                        GL_PROPANE_PRESSURE_AVG = 0
                        GL_DAACETYLENE_PRESSURE_AVG = 0
                        GL_FORMING_TEMP_AVG = 0
                        power_consumption = 0
                        GL_HYDROLIC_POWER_PACK_AVG = 0
                        GL_AV_PRESSURE_HEAT = []
                        GL_AV_PRESSURE_CUTTING = []
                        GL_AV_PNG_PRESSURE = []
                        GL_AV_PROPANE_PRESSURE = []
                        GL_AV_DAACETYLENE_PRESSURE = []
                        GL_AV_FORMING_TEMP = []
                        GL_AV_HYDROLIC_POWER_PACK = []
                FL_PREV_STATUS = FL_STATUS
            else:
                log.error(f"[-] Machine Disconnected got {data}")
                time.sleep(1)
        except Exception as e:
            time.sleep(5)
            log.error(f"[-] Error in running program{e}")
