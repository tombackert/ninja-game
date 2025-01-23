import socket
import threading
import json
import time

class GameServer:
    def __init__(self, host="localhost", port=5555, tick_rate=30):
        """
        Simple server for a 2D game:
          - host: IP address (e.g., "0.0.0.0" for all interfaces)
          - port: Port number
          - tick_rate: How many times per second the GameState is updated/sent
        """
        self.host = host
        self.port = port
        self.tick_rate = tick_rate

        # Server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()

        print(f"[SERVER] Running on {self.host}:{self.port}")

        # Dictionary for connected clients: { client_id: (conn, addr) }
        self.clients = {}
        self.next_client_id = 0

        # GameState: Simple example -> {client_id: {"x": 100, "y": 100}}
        # Can be extended later with more info (HP, Items, etc.)
        self.game_state = {}

        # Flag for main loop
        self.running = True

    def start(self):
        """
        Starts the server: 
          - Thread for 'accept_clients'
          - Thread/main loop for 'game_loop'
        """
        accept_thread = threading.Thread(target=self.accept_clients)
        accept_thread.start()

        self.game_loop()

    def accept_clients(self):
        """
        Waits for new connections and stores them in self.clients.
        """
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                print(f"[SERVER] New connection from {addr}")
                
                # Assign client ID
                client_id = self.next_client_id
                self.next_client_id += 1

                # Initial state of new player
                self.game_state[client_id] = {"x": 100, "y": 100}

                self.clients[client_id] = (conn, addr)

                # Start thread for client
                client_thread = threading.Thread(target=self.client_handler, args=(client_id,))
                client_thread.start()

            except OSError:
                # In case socket is closed etc.
                break

    def client_handler(self, client_id):
        """
        Processes incoming data from a client until they disconnect.
        """
        conn, addr = self.clients[client_id]
        # Could send client their ID as welcome message
        welcome_msg = {"type": "WELCOME", "client_id": client_id}
        self.send_data(client_id, welcome_msg)

        while self.running:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                # Interpret data as JSON
                msg = json.loads(data.decode("utf-8"))
                self.handle_client_message(client_id, msg)
            except ConnectionResetError:
                break
            except Exception as e:
                print(f"[SERVER] Error with client {client_id}: {e}")
                break

        # Client disconnected
        print(f"[SERVER] Client {client_id} disconnected.")
        conn.close()
        # Remove from dictionaries
        if client_id in self.clients:
            del self.clients[client_id]
        if client_id in self.game_state:
            del self.game_state[client_id]

    def handle_client_message(self, client_id, msg):
        """
        Processes a message (dictionary), e.g., movement commands.
        """
        # Example: {"type": "MOVE", "dx": 1, "dy": 0}
        msg_type = msg.get("type")
        if msg_type == "MOVE":
            dx = msg.get("dx", 0)
            dy = msg.get("dy", 0)
            # Adjust player position
            self.game_state[client_id]["x"] += dx
            self.game_state[client_id]["y"] += dy
        # You could implement more types: "SHOOT", "JUMP", "CHAT", etc.

    def game_loop(self):
        """
        The 'GameState' loop that periodically sends updates to all clients.
        """
        dt = 1.0 / self.tick_rate
        try:
            while self.running:
                time.sleep(dt)
                # Server-side logic could happen here: enemy movement, collisions, ...
                self.broadcast_game_state()
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def broadcast_game_state(self):
        """
        Sends current game state to all clients.
        """
        # Minimal example: {"type": "STATE", "players": {...}}
        state_msg = {
            "type": "STATE",
            "players": self.game_state
        }
        for cid in list(self.clients.keys()):
            self.send_data(cid, state_msg)

    def send_data(self, client_id, data_dict):
        """
        Serializes data_dict as JSON and sends it to client_id.
        """
        if client_id not in self.clients:
            return
        conn, _ = self.clients[client_id]
        try:
            msg_str = json.dumps(data_dict)
            conn.sendall(msg_str.encode("utf-8"))
        except:
            print(f"[SERVER] Error sending to client {client_id}")

    def shutdown(self):
        """
        Cleanly stops the server.
        """
        self.running = False
        self.server_socket.close()
        print("[SERVER] Shutdown completed.")