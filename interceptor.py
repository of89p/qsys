import evdev
import asyncio
import requests

# Use the paths you found in /dev/input/by-id/
DRINKS_DEVICE_PATH = '/dev/input/by-id/usb-Drinks_Keypad-event-kbd'
FOOD_DEVICE_PATH = '/dev/input/by-id/usb-Food_Keypad-event-kbd'

# Map keycodes to actual numbers
KEY_MAP = {
    evdev.ecodes.KEY_KP1: '1', evdev.ecodes.KEY_KP2: '2', # ... map all keypad keys
    evdev.ecodes.KEY_KPENTER: 'ENTER'
}

async def read_keypad(device_path, station_name):
    device = evdev.InputDevice(device_path)
    
    # CRITICAL: Grab the device so the inputs don't leak into the terminal or GUI
    device.grab() 
    
    current_input = ""
    
    try:
        async for event in device.async_read_loop():
            if event.type == evdev.ecodes.EV_KEY and event.value == 1: # Keydown event
                key = KEY_MAP.get(event.code)
                if key == 'ENTER':
                    if current_input:
                        # Send to Next.js API
                        requests.post('http://localhost:3000/api/queue', json={
                            "station": station_name,
                            "number": current_input
                        })
                        current_input = ""
                elif key:
                    current_input += key
    except Exception as e:
        print(f"Error reading {station_name}: {e}")
    finally:
        device.ungrab()

async def main():
    await asyncio.gather(
        read_keypad(DRINKS_DEVICE_PATH, "drinks"),
        read_keypad(FOOD_DEVICE_PATH, "food")
    )

if __name__ == "__main__":
    asyncio.run(main())
