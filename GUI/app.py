from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import serial
import serial.tools.list_ports
import threading
import time
from queue import Queue

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

ser = None
clients = set()
data_queue = Queue()

def list_serial_ports():
    ports = serial.tools.list_ports.comports()
    return [{"device": port.device, "description": port.description} for port in ports]

def read_from_serial():
    global ser
    while True:
        if ser and ser.is_open:
            try:
                if ser.in_waiting:
                    raw_data = ser.readline()
                    try:
                        line = raw_data.decode('utf-8').strip()
                    except UnicodeDecodeError:
                        line = raw_data.decode('latin-1').strip()
                        print(f"Warning: Non-UTF-8 data received: {line}", flush=True)
                    if line:
                        data_queue.put(line)
            except Exception as e:
                print(f"Error reading from serial: {e}", flush=True)
        else:
            time.sleep(0.1)

def send_to_clients():
    while True:
        if not data_queue.empty():
            data = []
            while not data_queue.empty():
                item = data_queue.get()
                if isinstance(item, bytes):
                    item = item.decode('latin-1')
                data.append(item)
            if data:
                print(f"Sending {len(data)} lines to clients", flush=True)
                socketio.emit('serial_message', {'data': data}, namespace='/')
        socketio.sleep(0.01)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_ports')
def get_ports():
    ports = list_serial_ports()
    return jsonify(ports)

@app.route('/connect', methods=['POST'])
def connect():
    global ser
    port = request.form['port']
    baudrate = request.form['baudrate']
    try:
        ser = serial.Serial(port, int(baudrate), timeout=0)
        print(f"Connected to {port} at {baudrate} baud.", flush=True)
        return 'Connected'
    except Exception as e:
        print(f"Failed to connect: {e}", flush=True)
        return f"Failed to connect: {str(e)}", 400

@app.route('/send_command', methods=['POST'])
def handle_command():
    if not ser or not ser.is_open:
        return "Serial port not connected", 400
    command = request.form['command']
    try:
        ser.write((command + '\n').encode())
        print(f"Command sent: {command}", flush=True)
        return 'Command sent'
    except Exception as e:
        print(f"Error sending command: {e}", flush=True)
        return f"Error sending command: {str(e)}", 400

@socketio.on('connect')
def handle_connect():
    print("Client connected", flush=True)
    clients.add(request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected", flush=True)
    clients.remove(request.sid)

if __name__ == '__main__':
    read_thread = threading.Thread(target=read_from_serial)
    read_thread.daemon = True
    read_thread.start()

    send_thread = threading.Thread(target=send_to_clients)
    send_thread.daemon = True
    send_thread.start()

    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
