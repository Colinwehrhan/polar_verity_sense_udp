import asyncio
import signal
import threading
import socket
from typing import Union
from bleak import BleakScanner
from rich.console import Console
from rich import inspect
from pythonosc import udp_client
from pythonosc.osc_message_builder import OscMessageBuilder

# Ports to send the code to touch designer over udp
TD_IP = "127.0.0.1"
TD_PORT = 8000

# UDP settings for receiving sensor messages
UDP_HOST = "255.255.255.255"  # Broadcast address
UDP_PORT = 12345

osc_client = udp_client.SimpleUDPClient(TD_IP,TD_PORT)

# Global variable to track sensor status
sensor_detected = False

from polar_python import (
    PolarDevice,
    MeasurementSettings,
    SettingType,
    ECGData,
    ACCData,
    HRData,
    #PPIData
)
from polar_python.constants import PPIData

console = Console()

exit_event = threading.Event()


def handle_exit(signum, frame):
    console.print("[bold red]Received exit signal[/bold red]")
    exit_event.set()


async def udp_listener():
    """Listen for UDP messages to determine sensor status"""
    global sensor_detected
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(('', UDP_PORT))  # Bind to all interfaces on the specified port
    sock.setblocking(False)
    
    console.print(f"[bold yellow]UDP listener started on port {UDP_PORT}[/bold yellow]")
    
    try:
        while not exit_event.is_set():
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8').strip()
                console.print(f"[bold cyan]Received UDP message:[/bold cyan] {message} from {addr}")
                
                if message == "SENSOR:DETECTED":
                    sensor_detected = True
                    console.print("[bold green]Sensor status: DETECTED - sending real BPM[/bold green]")
                elif message == "SENSOR:NO_OBJECT":
                    sensor_detected = False
                    console.print("[bold red]Sensor status: NO_OBJECT - sending 0 BPM[/bold red]")
                else:
                    console.print(f"[bold yellow]Unknown message format: {message}[/bold yellow]")
                    
            except socket.error:
                # No data available, continue loop
                await asyncio.sleep(0.1)
                
    except Exception as e:
        console.print(f"[bold red]UDP listener error: {e}[/bold red]")
    finally:
        sock.close()


async def main():
    device = await BleakScanner.find_device_by_filter(
        lambda bd, ad: bd.name and "Polar Sense" in bd.name, timeout=5
    )
    if device is None:
        console.print("[bold red]Device not found[/bold red]")
        return

    inspect(device)

    async with PolarDevice(device) as polar_device:
        available_features = await polar_device.available_features()
        inspect(available_features)

        for feature in available_features:
            settings = await polar_device.request_stream_settings(feature)
            console.print(
                f"[bold blue]Settings for {feature}:[/bold blue] {settings}", end="\n\n"
            )

        acc_settings = MeasurementSettings(
            measurement_type="ACC",
            settings=[
                SettingType(type="SAMPLE_RATE", values=[52]),
                SettingType(type="RESOLUTION", values=[16]),
                SettingType(type="RANGE", values=[8]),
                SettingType(type="CHANNELS", values=[3]),
            ],
        )

        ppi_settings = MeasurementSettings(measurement_type="PPI", settings=[])

        ppg_settings = MeasurementSettings(
            measurement_type="PPG",
            settings=[
                SettingType(type="SAMPLE_RATE", values=[55]),
                SettingType(type="RESOLUTION", values=[22]),
                SettingType(type="CHANNELS", values=[4]),
            ],
        )

        def heartrate_callback(data: HRData):
            global sensor_detected
            real_heart_rate = data.heartrate
            
            # Send real BPM if sensor detected, otherwise send 0
            heart_rate_to_send = real_heart_rate if sensor_detected else 0

            console.print(f"[bold green]Received Data:[/bold green] {data}")
            console.print(f"[bold green]Real Heart Rate:[/bold green] {real_heart_rate} bpm")
            console.print(f"[bold green]Sensor Detected:[/bold green] {sensor_detected}")
            console.print(f"[bold green]Sending Heart Rate:[/bold green] {heart_rate_to_send} bpm")
            
            try:
                # send osc HR over udp via osc
                osc_client.send_message("/polar/hr", heart_rate_to_send)
                console.print(f"[bold blue]Sent OSC message:[/bold blue] /polar/hr {heart_rate_to_send}")
            except Exception as e:
                console.print(f"[bold red]Error sending OSC message: {e}[/bold red]")

        def data_callback(data: Union[ECGData, ACCData, PPIData]):
            console.print(f"[bold green]Received Data:[/bold green] {data}")

        polar_device.set_callback(data_callback, heartrate_callback)
        #await polar_device.start_stream(acc_settings)
        #await polar_device.start_stream(ppi_settings)
        #await polar_device.start_stream(ppg_settings)
        await polar_device.start_heartrate_stream()

        # Start UDP listener as background task
        udp_task = asyncio.create_task(udp_listener())

        while not exit_event.is_set():
            await asyncio.sleep(1)
            
        # Cancel UDP listener task
        udp_task.cancel()
        try:
            await udp_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # Run the main function
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
        console.print("[bold red]Program exited gracefully[/bold red]")