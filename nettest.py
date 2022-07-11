#!/usr/bin/env python3
###############################################################################
#   @author         :   Jeffrey Stone 
#   @date           :   03/09/2019
#   @script        	:   nettest.py
#   @description    :   Script to run a network speedtest and publish the results to MQTT
###############################################################################
import sys
import speedtest
import os
import time
import json
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
# set custom .env file-path if your file isn't found
load_dotenv("./env-sample.env")

# state variables
phao_client = None
# config variables
app_mode = os.getenv("app_mode")
interval = int(os.getenv("interval"))
broker = os.getenv("broker")
port = int(os.getenv("port"))
topic = os.getenv("topic")
user = os.getenv("user")
password = os.getenv("password")
test_server = [] if os.getenv("test_server") == "False" else [int(os.getenv("test_server"))]
name = os.getenv("name")
# Splunk env:
http_event_collector_key = os.getenv("splunk_hec_key")
http_event_collector_host = os.getenv("splunk_server")
http_event_collector_ssl = os.getenv("splunk_hec_ssl")
http_event_collector_port = int(os.getenv("splunk_hec_port"))
splunk_host = os.getenv("splunk_host")
splunk_source = os.getenv("splunk_source")
splunk_sourcetype = os.getenv("splunk_sourcetype")
splunk_index = os.getenv("splunk_index")

# JSON config payload for HomeAssistant
device_config = {
	"name": name
}
name_config_payload = {
	"name": name + " ServerName",
	"state_topic": topic.to_string()+"N/state",
	"exp_aft": 3660, 
	"icon": "mdi:speedometer", 
	"value_template": "{{value_json.name | is_defined}}",
	"device": device_config
}
up_config_payload = {
	"name": name + " Upload", 
	"unit_of_meas": "Mbit/s", 
	"state_topic": topic.to_string()+"U/state",
	"exp_aft": 3660, 
	"icon": "mdi:speedometer", 
	"state_class": "measurement",
	"value_template": "{{value_json.up | is_defined}}",
	"device": device_config
}
down_config_payload = {
	"name": name + " Download", 
	"unit_of_meas": "Mbit/s", 
	"state_topic": topic.to_string()+"D/state",
	"exp_aft": 3660, 
	"icon": "mdi:speedometer", 
	"state_class": "measurement",
	"value_template": "{{value_json.down | is_defined}}",
	"device": device_config
}

# if splunk hec key set in .env load the splunk libraries
if http_event_collector_key:
	import json
	from splunk_http_event_collector import http_event_collector
	if http_event_collector_ssl == "False":
		http_event_collector_ssl = False
	else:
		http_event_collector_ssl = True

def splunkIt(test,result,total_elapsed_time):
	if app_mode == 'debug': print("Time to Splunk It Yo...\n")
	logevent = http_event_collector(http_event_collector_key, http_event_collector_host, http_event_port = http_event_collector_port, http_event_server_ssl = http_event_collector_ssl)
	logevent.popNullFields = True

	payload = {}
	payload.update({"index":splunk_index})
	payload.update({"sourcetype":splunk_sourcetype})
	payload.update({"source":splunk_source})
	payload.update({"host":splunk_host})
	event = {}
	event.update({"action":"success"})
	event.update({"test":test})
	event.update({"total_elapsed_time":total_elapsed_time})
	event.update({"test_result":result})
	payload.update({"event":event})
	logevent.sendEvent(payload)
	logevent.flushBatch()
	if app_mode == 'debug': print("It has been Splunked...\n")


def testDownSpeed():
	global down_speed, testserver_name
	if app_mode == 'debug': print("Starting Download test...")
	start = time.time()
	speedtester = speedtest.Speedtest()
	speedtester.get_servers(test_server)
	best_server = speedtester.get_best_server()
	speed = round(speedtester.download() / 1000 / 1000)
	end = time.time()
	total_elapsed_time = (end - start)
	if app_mode == 'debug': print("Saving Download result {}...".format(speed))
	testserver_name = best_server["sponsor"]
	down_speed = speed
	if http_event_collector_key:
		splunkIt('download',speed,total_elapsed_time)


def testUpSpeed():
	global up_speed
	if app_mode == 'debug': print("Starting Upload test...")
	start = time.time()
	speedtester = speedtest.Speedtest()
	speedtester.get_servers(test_server)
	speedtester.get_best_server()
	speed = round(speedtester.upload() / 1000 / 1000)
	end = time.time()
	total_elapsed_time = (end - start)
	if app_mode == 'debug': print("Saving Upload test result {}...".format(speed))
	up_speed = speed
	if http_event_collector_key:
		splunkIt('upload',speed,total_elapsed_time)

def publishToMqtt():
	if app_mode == 'debug': print("Publishing test results {},{},{} to MQTT...".format(testserver_name, up_speed, down_speed))
	data_payload = {
		"server_name": "",
		"up_speed": 0.0,
		"down_speed": 0.0,
	}
	data_payload["server_name"] = testserver_name
	data_payload["up"] = up_speed
	data_payload["down"] = down_speed
	phao_client.publish(topic+"/state",json.dumps(data_payload))

# subscribe to config topic to check init-state
def on_connect(client, userdata, flags, rc):
	if rc==0:
		print("Connected with result code 0")
	else:
		raise ValueError("Bad connection returned code=",rc)

def initMqtt():
	global phao_client
	if app_mode == 'debug': print("Initilizing MQTT Service....")
	phao_client = mqtt.Client(name)
	phao_client.on_connect = on_connect
	phao_client.username_pw_set(user, password=password)
	phao_client.connect(broker,port)
	
def main(interval):
	print("app mode: "+app_mode)

	# setup mqtt service
	initMqtt()
	while (not phao_client):
		if app_mode == 'debug': print("wating for mqtt connect....")
		time.sleep(1)
	phao_client.loop_start()

	while True:
		if app_mode == 'debug': print("Starting network tests....")
		testDownSpeed()
		testUpSpeed()
		publishToMqtt()
		if app_mode == 'debug': print("Tests completed...")
		if interval > 0:
			print("Time to sleep for {} seconds\n".format(interval))
			time.sleep(interval)
		else:
			if app_mode == 'debug': print("No Interval set...exiting...\n")
			sys.exit()

if __name__ == "__main__":
    main(interval)