import usb_hid
import time
import board
import busio
import json
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.mouse import Mouse

# Initialize UART, Keyboard, and Mouse
uart = busio.UART(board.GP0, board.GP1, baudrate=115200, timeout=0.1)
kbd = Keyboard(usb_hid.devices)
mouse = Mouse(usb_hid.devices)

# Track absolute mouse position
current_x = 0
current_y = 0

# Build a map of all keycodes including modifiers
key_map = {
    k.lower(): v for k, v in Keycode.__dict__.items()
    if not k.startswith("_") and isinstance(v, int)
}

# Helper to parse combos like "ctrl+alt+delete"
def parse_combo_key(name):
    parts = name.lower().split("+")
    mods = []
    main = None
    for part in parts:
        if part == "ctrl":
            mods.append(Keycode.CONTROL)
        elif part == "shift":
            mods.append(Keycode.SHIFT)
        elif part == "alt":
            mods.append(Keycode.ALT)
        elif part in {"gui", "windows", "command"}:
            mods.append(Keycode.GUI)
        elif part in key_map:
            main = key_map[part]
        else:
            print(f"Unknown key part: {part}")
    return mods, main

print("Pico HID bridge running...")

buffer = b""

while True:
    # Read and process only when data is available
    if uart.in_waiting:
        data = uart.read(uart.in_waiting) or b""
        buffer += data

        # Process each complete JSON line
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line.decode())
            except Exception as e:
                print("JSON parse error:", e, "- releasing all keys")
                kbd.release_all()
                continue

            msg_type = payload.get("type")

            if msg_type == "key":
                key_str = payload.get("key", "")
                if not isinstance(key_str, str):
                    print("Bad key field:", key_str, "- skipping")
                    continue
                press = payload.get("press", True)
                mods, main = parse_combo_key(key_str)

                if press:
                    for m in mods:   kbd.press(m)
                    if main:        kbd.press(main)
                    print(f"Pressed: {key_str}")
                else:
                    if main:        kbd.release(main)
                    for m in mods:   kbd.release(m)
                    print(f"Released: {key_str}")

            elif msg_type == "mouse":
                x = payload.get("x", 0)
                y = payload.get("y", 0)
                buttons = payload.get("buttons", 0)
                press = payload.get("press", True)

                # Relative movement
                if x or y:
                    mouse.move(x=x, y=y)
                    print(f"Move: dx={x}, dy={y}")

                # Button press/release
                if buttons and press:
                    if buttons == 1:   mouse.press(Mouse.LEFT_BUTTON)
                    elif buttons == 2: mouse.press(Mouse.RIGHT_BUTTON)
                elif buttons and not press:
                    if buttons == 1:   mouse.release(Mouse.LEFT_BUTTON)
                    elif buttons == 2: mouse.release(Mouse.RIGHT_BUTTON)

            elif msg_type == "mouse_abs":
                abs_x = payload.get("x", 0)
                abs_y = payload.get("y", 0)
                dx = abs_x - current_x
                dy = abs_y - current_y
                mouse.move(x=dx, y=dy)
                current_x, current_y = abs_x, abs_y
                print(f"Absolute Move to: x={abs_x}, y={abs_y}, Δ={dx},{dy}")

            elif msg_type == "reset":
                print("Reset (releasing all keys first)")
                kbd.release_all()
                import microcontroller
                microcontroller.reset()

    # Yield CPU if idle
    time.sleep(0.01)
