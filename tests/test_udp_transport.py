"""Tests for UDP Transport Layer (MP-03).

Tests the UDPTransport class and related networking functionality.
"""

import socket
import time
import unittest

from scripts.network.messages import Message
from scripts.network.udp_transport import (
    Packet,
    PacketHeader,
    UDPClient,
    UDPServer,
    UDPTransport,
)


class TestPacketHeader(unittest.TestCase):
    """Tests for PacketHeader dataclass."""

    def test_header_defaults(self):
        """Header should have sensible defaults."""
        header = PacketHeader()
        self.assertEqual(header.sequence, 0)
        self.assertEqual(header.ack, 0)
        self.assertEqual(header.ack_bitfield, 0)

    def test_header_custom_values(self):
        """Header should accept custom values."""
        header = PacketHeader(sequence=10, ack=5, ack_bitfield=0xFF)
        self.assertEqual(header.sequence, 10)
        self.assertEqual(header.ack, 5)
        self.assertEqual(header.ack_bitfield, 0xFF)


class TestPacket(unittest.TestCase):
    """Tests for Packet serialization."""

    def test_packet_roundtrip(self):
        """Packet should survive serialization roundtrip."""
        header = PacketHeader(sequence=42, ack=10, ack_bitfield=0b1010)
        message = Message(type="test", payload={"value": 123})
        packet = Packet(header=header, message=message)

        data = packet.to_bytes()
        restored = Packet.from_bytes(data)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.header.sequence, 42)
        self.assertEqual(restored.header.ack, 10)
        self.assertEqual(restored.message.type, "test")
        self.assertEqual(restored.message.payload["value"], 123)

    def test_packet_from_invalid_bytes(self):
        """Malformed bytes should return None."""
        self.assertIsNone(Packet.from_bytes(b"not json"))
        self.assertIsNone(Packet.from_bytes(b"{}"))  # Missing fields
        self.assertIsNone(Packet.from_bytes(b"\xff\xfe"))  # Invalid UTF-8


class TestUDPTransport(unittest.TestCase):
    """Tests for UDPTransport class."""

    def test_transport_binds_to_specific_port(self):
        """Transport should bind to specified port."""
        transport = UDPTransport(port=17777)
        try:
            self.assertEqual(transport.port, 17777)
            self.assertEqual(transport.local_addr[1], 17777)
        finally:
            transport.close()

    def test_transport_binds_to_ephemeral_port(self):
        """Transport should get OS-assigned port when port=0."""
        transport = UDPTransport(port=0)
        try:
            self.assertGreater(transport.port, 0)
        finally:
            transport.close()

    def test_receive_returns_none_when_empty(self):
        """Non-blocking receive should return None when no data."""
        transport = UDPTransport(port=17778)
        try:
            result = transport.receive()
            self.assertIsNone(result)
        finally:
            transport.close()

    def test_loopback_send_receive(self):
        """Should be able to send and receive on localhost."""
        server = UDPTransport(port=17779)
        client = UDPTransport(port=0)

        try:
            # Send message from client to server
            msg = Message(type="input", payload={"tick": 1, "inputs": ["left", "jump"]})
            success = client.send(msg, ("127.0.0.1", 17779))
            self.assertTrue(success)

            # Small delay for packet to arrive
            time.sleep(0.01)

            # Receive on server
            result = server.receive()
            self.assertIsNotNone(result)
            received_msg, sender_addr, header = result

            self.assertEqual(received_msg.type, "input")
            self.assertEqual(received_msg.payload["tick"], 1)
            self.assertIn("left", received_msg.payload["inputs"])
        finally:
            server.close()
            client.close()

    def test_sequence_numbers_increment(self):
        """Sequence numbers should increment with each send."""
        transport = UDPTransport(port=17780)
        receiver = UDPTransport(port=17781)

        try:
            msg = Message(type="test", payload={})

            # Send multiple messages
            transport.send(msg, ("127.0.0.1", 17781))
            transport.send(msg, ("127.0.0.1", 17781))
            transport.send(msg, ("127.0.0.1", 17781))

            time.sleep(0.01)

            # Receive and check sequences
            sequences = []
            while True:
                result = receiver.receive()
                if result is None:
                    break
                _, _, header = result
                sequences.append(header.sequence)

            self.assertEqual(sequences, [0, 1, 2])
        finally:
            transport.close()
            receiver.close()

    def test_malformed_packet_ignored(self):
        """Malformed packets should be gracefully ignored."""
        server = UDPTransport(port=17782)

        try:
            # Send garbage data directly via raw socket
            raw_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            raw_socket.sendto(b"not json at all", ("127.0.0.1", 17782))
            raw_socket.close()

            time.sleep(0.01)

            # Should return None (packet ignored)
            result = server.receive()
            self.assertIsNone(result)
        finally:
            server.close()

    def test_context_manager(self):
        """Transport should work as context manager."""
        with UDPTransport(port=17783) as transport:
            self.assertGreater(transport.port, 0)
        # Socket should be closed after context exit

    def test_ack_tracking(self):
        """Transport should track acknowledgments."""
        server = UDPTransport(port=17784)
        client = UDPTransport(port=0)

        try:
            # Client sends messages
            for i in range(5):
                msg = Message(type="test", payload={"i": i})
                client.send(msg, ("127.0.0.1", 17784))

            time.sleep(0.01)

            # Server receives all
            client_addr = None
            for _ in range(5):
                result = server.receive()
                if result:
                    _, client_addr, _ = result

            # Check ack status
            if client_addr:
                last_ack, bitfield = server.get_ack_status(client_addr)
                self.assertEqual(last_ack, 4)  # Last sequence was 4
        finally:
            server.close()
            client.close()


class TestUDPClientServer(unittest.TestCase):
    """Tests for UDPClient and UDPServer convenience classes."""

    def test_client_server_communication(self):
        """Client and server should communicate successfully."""
        server = UDPServer(port=17785)
        client = UDPClient("127.0.0.1", 17785)

        try:
            # Client sends to server
            msg = Message(type="hello", payload={"name": "player1"})
            client.send(msg)

            time.sleep(0.01)

            # Server receives
            result = server.receive()
            self.assertIsNotNone(result)
            received_msg, client_addr, _ = result
            self.assertEqual(received_msg.type, "hello")

            # Server responds
            response = Message(type="welcome", payload={"id": 1})
            server.send(response, client_addr)

            time.sleep(0.01)

            # Client receives response
            result = client.receive()
            self.assertIsNotNone(result)
            response_msg, _ = result
            self.assertEqual(response_msg.type, "welcome")
        finally:
            server.close()
            client.close()

    def test_server_broadcast(self):
        """Server should broadcast to all known clients."""
        server = UDPServer(port=17786)
        client1 = UDPClient("127.0.0.1", 17786)
        client2 = UDPClient("127.0.0.1", 17786)

        try:
            # Clients register by sending a message
            client1.send(Message(type="join", payload={}))
            client2.send(Message(type="join", payload={}))

            time.sleep(0.01)

            # Server receives to register clients
            server.receive()
            server.receive()

            # Broadcast
            broadcast_msg = Message(type="update", payload={"tick": 100})
            count = server.broadcast(broadcast_msg)
            self.assertEqual(count, 2)

            time.sleep(0.01)

            # Both clients should receive
            r1 = client1.receive()
            r2 = client2.receive()
            self.assertIsNotNone(r1)
            self.assertIsNotNone(r2)
        finally:
            server.close()
            client1.close()
            client2.close()


class TestNetSyncServiceWithUDP(unittest.TestCase):
    """Integration tests for NetSyncService with UDP transport."""

    def test_netsync_with_udp_transport(self):
        """NetSyncService should work with UDP transport."""
        from scripts.network.netsync_service import NetSyncService

        server_transport = UDPTransport(port=17787)
        client_transport = UDPTransport(port=0)

        server_sync = NetSyncService(server_transport)
        client_sync = NetSyncService(client_transport, default_address=("127.0.0.1", 17787))

        try:
            # Client sends input
            client_sync.send_input(tick=42, inputs=["right", "dash"])

            time.sleep(0.01)

            # Server processes
            messages = server_sync.process_messages()
            self.assertEqual(len(messages), 1)

            msg, addr = messages[0]
            self.assertEqual(msg.type, "input")
            self.assertEqual(msg.payload["tick"], 42)
            self.assertIn("right", msg.payload["inputs"])
        finally:
            server_sync.close()
            client_sync.close()


if __name__ == "__main__":
    unittest.main()
