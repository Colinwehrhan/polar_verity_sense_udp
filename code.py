import board
import analogio
import time
import wifi
import socketpool
import os

# connect to the wif
print("Connecting to WiFi....")
try:
    print(f"Trying to connect to {os.getenv("CIRCUITPY_WIFI_SSID")}...")
    wifi.radio.connect(ssid=os.getenv("CIRCUITPY_WIFI_SSID"), password=os.getenv("CIRCUITPY_WIFI_PASSWORD"))
    # If the code reaches this line, the connection was successful
    print("Connection successful!")
    print(f"My IP address is: {wifi.radio.ipv4_address}")
except ConnectionError as e:
    print(f"Failed to connect to Wi-Fi. Error: {e}")
print("Connection attempt complete.")

#setup UPD
pool = socketpool.SocketPool(wifi.radio)

udp_host = "255.255.255.255"  # LAN IP of UDP receiver
udp_port = 8080             # must match receiver!

my_message = "Phototransistor is reading: "

sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM) # UDP, and we'l reuse it each time
# Tell the socket it's allowed to send broadcast packets
sock.setsockopt(pool.SOL_SOCKET, pool.SO_BROADCAST, 1)  # <-- [CHANGE 2] Add this line

photo_pin = analogio.AnalogIn(board.A0)  # Photo resistor exsists on A0

# send the photo transistor as UDP data
while True:
    raw_value = photo_pin.value
    print(f"Raw Value: {raw_value}")
    # stick a nubmer on the end of the message to show progress and conver to bytearray
    udp_message = bytes(f"{my_message} {raw_value}", 'utf-8')
    try:
        print(f"Sending to {udp_host}:{udp_port} message:", udp_message)
        sock.sendto(udp_message, (udp_host,udp_port) )  # send UDP packet to udp_host:port
    except(BrokenPipeError, ConnectionError) as e:
        print(f"Network error as: {e}")
    time.sleep(1)