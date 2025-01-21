import socket
import json
import threading

class GameClient:
    def __init__(self, server_ip="localhost", server_port=5555):
        """
        Establishes connection to the server and starts receiving threads.
        """
        self.server_ip = server_ip
        self.server_port = server_port

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False

        # Local game state: e.g., player_id, positions etc.
        self.player_id = None
        self.game_state = {}
        self.running = True

    def connect(self):
        try:
            self.sock.connect((self.server_ip, self.server_port))
            self.connected = True
            print(f"[CLIENT] Successfully connected to {self.server_ip}:{self.server_port}")

            # Start receiving thread
            recv_thread = threading.Thread(target=self.listen_server)
            recv_thread.start()

        except Exception as e:
            print(f"[CLIENT] Error while connecting: {e}")

    def listen_server(self):
        """
        Continuously receives data from the server and processes it.
        """
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    print("[CLIENT] Lost connection to server.")
                    self.running = False
                    break

                msg = json.loads(data.decode("utf-8"))
                self.handle_server_message(msg)

            except Exception as e:
                print(f"[CLIENT] Error while receiving: {e}")
                self.running = False
                break

        self.sock.close()

    def handle_server_message(self, msg):
        """
        Processes a message from the server:
          e.g., 'WELCOME', 'STATE' etc.
        """
        msg_type = msg.get("type")
        if msg_type == "WELCOME":
            # Server assigns you a player_id
            self.player_id = msg.get("client_id")
            print(f"[CLIENT] Welcome, you are player {self.player_id}")

        elif msg_type == "STATE":
            # Global game state
            self.game_state = msg.get("players", {})
            # You can update your Pygame UI here:
            #   -> Update positions of other players

        else:
            print(f"[CLIENT] Unknown message: {msg}")

    def send_move(self, dx, dy):
        """
        Example: Send movement command to the server.
        """
        if not self.connected:
            return
        move_msg = {
            "type": "MOVE",
            "dx": dx,
            "dy": dy
        }
        self.send_data(move_msg)

    def send_data(self, data_dict):
        try:
            msg_str = json.dumps(data_dict)
            self.sock.sendall(msg_str.encode("utf-8"))
        except:
            print("[CLIENT] Error while sending.")

    def close(self):
        self.running = False
        self.sock.close()
        print("[CLIENT] Connection closed.")