#!/usr/local/bin/python
#
#-----------------------------------------------------------------------------
# "THE BEER-WARE LICENSE":
# Updated and added funtions to send data via MQTT to Home-assistant
# Changed interfacing to work with adapter bought from China (off-label)
# - Niclas Flach
# ----------------------------------------------------------------------------
# "THE BEER-WARE LICENSE" (Revision 42):
# <phk@FreeBSD.ORG> wrote this file.  As long as you retain this notice you
# can do whatever you want with this stuff. If we meet some day, and you think
# this stuff is worth it, you can buy me a beer in return.   Poul-Henning Kamp
# ----------------------------------------------------------------------------
#

from __future__ import print_function

# You need pySerial 
import serial
import requests as req
import math
import paho.mqtt.client as mqtt

#######################################################################
# These are the variables I have managed to identify
# Submissions welcome.

kamstrup_382_var = {

	0x0001: "Energy in",
	0x0002: "Energy out",

	0x000d: "Energy in hi-res",
	0x000e: "Energy out hi-res",

	0x041e: "Voltage p1",
	0x041f: "Voltage p2",
	0x0420: "Voltage p3",

	0x0434: "Current p1",
	0x0435: "Current p2",
	0x0436: "Current p3",

	0x0438: "Power p1",
	0x0439: "Power p2",
	0x043a: "Power p3",

	0x03ff: "Power In",
	0x0438: "Power p1 In",
	0x0439: "Power p2 In",
	0x043a: "Power p3 In",

	0x0400: "Power Out",
	0x0540: "Power p1 Out",
	0x0541: "Power p2 Out",
	0x0542: "Power p3 Out",
}

kamstrup_681_var = {
	1:	"Date",
	60:	"Heat",
	61:	"x",
	62:	"x",
	63:	"x",
	95:	"x",
	96:	"x",
	97:	"x",
}

kamstrup_MC601_var = {
	0x003C: "Energy register 1: Heat energy",
	0x0044: "Volume register V1",
	0x0058: "Current temperature T3",
	0x03EC: "Operation hours counter",
}


#######################################################################
# Units, provided by Erik Jensen

units = {
	0: '', 1: 'Wh', 2: 'kWh', 3: 'MWh', 4: 'GWh', 5: 'j', 6: 'kj', 7: 'Mj',
	8: 'Gj', 9: 'Cal', 10: 'kCal', 11: 'Mcal', 12: 'Gcal', 13: 'varh',
	14: 'kvarh', 15: 'Mvarh', 16: 'Gvarh', 17: 'VAh', 18: 'kVAh',
	19: 'MVAh', 20: 'GVAh', 21: 'kW', 22: 'kW', 23: 'MW', 24: 'GW',
	25: 'kvar', 26: 'kvar', 27: 'Mvar', 28: 'Gvar', 29: 'VA', 30: 'kVA',
	31: 'MVA', 32: 'GVA', 33: 'V', 34: 'A', 35: 'kV',36: 'kA', 37: 'C',
	38: 'K', 39: 'l', 40: 'm3', 41: 'l/h', 42: 'm3/h', 43: 'm3xC',
	44: 'ton', 45: 'ton/h', 46: 'h', 47: 'hh:mm:ss', 48: 'yy:mm:dd',
	49: 'yyyy:mm:dd', 50: 'mm:dd', 51: '', 52: 'bar', 53: 'RTC',
	54: 'ASCII', 55: 'm3 x 10', 56: 'ton x 10', 57: 'GJ x 10',
	58: 'minutes', 59: 'Bitfield', 60: 's', 61: 'ms', 62: 'days',
	63: 'RTC-Q', 64: 'Datetime'
}

#######################################################################
# Kamstrup uses the "true" CCITT CRC-16
#

def crc_1021(message):
        poly = 0x1021
        reg = 0x0000
        for byte in message:
                mask = 0x80
                while(mask > 0):
                        reg<<=1
                        if byte & mask:
                                reg |= 1
                        mask>>=1
                        if reg & 0x10000:
                                reg &= 0xffff
                                reg ^= poly
        return reg

#######################################################################
# Byte values which must be escaped before transmission
#

escapes = {
	0x06: True,
	0x0d: True,
	0x1b: True,
	0x40: True,
	0x80: True,
}

#######################################################################
# And here we go....
#
class kamstrup(object):

	def __init__(self, serial_port = "/dev/ttyUSB0"):
		#self.debug_fd = open("/tmp/_kamstrup", "a")
		#self.debug_msg.write("\n\nStart\n")
		#self.debug_id = None

  
		#Set up USB to communicate at Baudrate 9600 which my meter uses for IR communication

		self.ser = serial.Serial(
		    port = serial_port,
		    baudrate = 9600,
		    timeout = 1.0)

	

	
	#Write byte-array
	def wr(self, b):
		b = bytearray(b)
		
		self.ser.write(b)
	#Read byte-array
	def rd(self):
		a = self.ser.read(1)
		if len(a) == 0:
			
			return None
		b = bytearray(a)[0]
		
		return b
	#send msg
	def send(self, pfx, msg):
		b = bytearray(msg)

		b.append(0)
		b.append(0)
		c = crc_1021(b)
		b[-2] = c >> 8
		b[-1] = c & 0xff

		c = bytearray()
		c.append(pfx)
		for i in b:
			if i in escapes:
				c.append(0x1b)
				c.append(i ^ 0xff)
			else:
				c.append(i)
		c.append(0x0d)
		self.wr(c)
	#Recieve data
	def recv(self):
		b = bytearray()
		while True:
			d = self.rd()
			if d == None:
				return None
			if d == 0x40:
				b = bytearray()
			b.append(d)
			if d == 0x0d:
				break
		c = bytearray()
		i = 1;
		while i < len(b) - 1:
			if b[i] == 0x1b:
				v = b[i + 1] ^ 0xff
				if v not in escapes:
					self.debug_msg(
					    "Missing Escape %02x" % v)
				c.append(v)
				i += 2
			else:
				c.append(b[i])
				i += 1
		if crc_1021(c):
			self.debug_msg("CRC error")
		return c[:-2]

	def readvar(self, nbr):
		# I wouldn't be surprised if you can ask for more than
		# one variable at the time, given that the length is
		# encoded in the response.  Havn't tried.

		self.send(0x80, (0x3f, 0x10, 0x01, nbr >> 8, nbr & 0xff))

		b = self.recv()
		if b == None:
			return (None, None)

		if b[0] != 0x3f or b[1] != 0x10:
			return (None, None)

		if b[2] != nbr >> 8 or b[3] != nbr & 0xff:
			return (None, None)

		if b[4] in units:
			u = units[b[4]]
		else:
			u = None

		# Decode the mantissa
		x = 0
		for i in range(0,b[5]):
			x <<= 8
			x |= b[i + 7]

		# Decode the exponent
		i = b[6] & 0x3f
		if b[6] & 0x40:
			i = -i
		i = math.pow(10,i)
		if b[6] & 0x80:
			i = -i
		x *= i

		if False:
			# Debug print
			s = ""
			for i in b[:4]:
				s += " %02x" % i
			s += " |"
			for i in b[4:7]:
				s += " %02x" % i
			s += " |"
			for i in b[7:]:
				s += " %02x" % i

			print(s, "=", x, units[b[4]])

		return (x, u)
			

if __name__ == "__main__":

	import time
	
	def on_connect(client, userdata, flags, rc):
		if rc==0:
			print("Connection OK")
		else:
			print("connection issues", rc)
	#def on_log(client, userdata, level, buf):
		#print("log: "+buf)

	#Address to MQTT Broker eg Home assistant server
	broker = "IP-ADRESS-TO-BROKER"
	#Name the client
	client = mqtt.Client("Energy_Script")
	#Run function upon connection with MQTT broker, for debug etc
 	#client.on_connect=on_connect
  	#client.on_log=on_log
	#Username and token from MQTT Broker addon in home assistant
	client.username_pw_set("homeassistant_username", "Long_lived_Token_from_Broker")
	#connect to broker change to applicable port on MQTT broker 1883 is what i am using
 	client.connect(broker, 1883)
	client.loop_start()
	foo = kamstrup()
	while(True):
		for i in kamstrup_382_var:
			x,u = foo.readvar(i)
			try:
				#Publish data to MQTT Broker
				client.publish("house/energy/"+kamstrup_382_var[i], round(float(x),2), 0)
				#Printing recieved data to console mostly for debug
    			print("%-25s" % kamstrup_382_var[i], round(float(x),2), u)
			except:
				#If an error occured during publish or there is an error in conversion and rounding of values
				print("None value present")
			#Wait 20 seconds to not spam the server with measurments
  			time.sleep(20)
    #And properly close the connection to the broker afterwards 
	client.loop_stop()
	client.disconnect