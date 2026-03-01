# Serial-BLE-Terminal-with-Real-Time-Plot
# Serial/BLE Terminal & Real-Time Plot

This application allows you to connect to a serial COM port or a BLE device and display incoming data in a terminal-like interface, with real-time plotting capabilities.

  Screenshot illustration (the right part is dynamically built with data you send to be displayed as key/values):

<img width="1424" height="799" alt="image" src="https://github.com/user-attachments/assets/575e6bd2-bc1c-460b-9539-11a0ae2a24c2" />

---

## Key Features

- Receive and send data over COM or BLE  
- Display incoming data with normalized line endings  
- Parse and display key–value pairs in a side panel  
- Plot numeric data in real time (oscilloscope-like view)  
- Record terminal output to a log file  
- Take screenshots of the plot area  

---

## Usage

1. Select the mode: **COM** or **BLE**  
2. Configure the connection:
   - **COM**: Select or enter the port name (e.g. `COM3`)
   - **BLE**: Select a device from the list (automatic scanning is performed)
3. Click **Connect** to start receiving data  
4. Use **Stop plot** to pause or resume real-time plotting  
5. Use **Record term** to start or stop recording terminal output to `terminal.log`  
6. Use **Clear term** to clear the terminal display  
7. Use **Screenshot** to save an image of the current plot area  

---

## Special Data Format – Key–Value Frames (Right Panel)

Lines received over Serial or BLE that start with `^` are treated as key–value frames.

Example: `^Temp:25\tHum:60\n`

- These lines are parsed and displayed in the right panel.
- Syntax is similar to the Arduino Serial Plotter:
  - `key:value` pairs
  - separated by `\t`
  - terminated by `\n`
- The `^` prefix distinguishes them from normal terminal lines.
- When a key is received for the first time, a new entry is dynamically created in the right panel.
- If the key already exists, its value is updated.

---

## Special Data Format – Real-Time Plot Data

Lines starting with `~` are treated as plot data and are **not displayed in the terminal**.

Example: `~Signal1:10\tSignal2:20\n`

- Each `key:value` pair is parsed.
- Values are plotted in real time.
- The key is used as the curve label.
- Syntax follows the same structure as Arduino Serial Plotter:
  - `key:value`
  - separated by `\t`
  - terminated by `\n`
- The `~` prefix distinguishes plot frames from normal terminal output.

### Plot Interaction

- Right-click to access the plot context menu (auto-range, grid, etc.).
- Left-click and drag to zoom.
- Right-click and drag to pan.

