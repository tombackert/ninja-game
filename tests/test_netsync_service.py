from scripts.network.messages import Message
from scripts.network.netsync_service import NetSyncService, LocalLoopbackTransport


def test_netsync_loopback_roundtrip():
    transport = LocalLoopbackTransport()
    service = NetSyncService(transport)

    # Send input
    service.send_input(tick=10, inputs=["jump", "right"])

    # Receive
    msgs = service.process_messages()
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg.type == 'input'
    assert msg.payload['tick'] == 10
    assert msg.payload['inputs'] == ["jump", "right"]


def test_netsync_snapshot_serialization():
    transport = LocalLoopbackTransport()
    service = NetSyncService(transport)

    dummy_snap = {"tick": 100, "rng": "seed123", "players": []}
    service.send_snapshot(100, dummy_snap)

    msgs = service.process_messages()
    assert len(msgs) == 1
    assert msgs[0].type == 'snapshot'
    assert msgs[0].payload['snapshot_data'] == dummy_snap


def test_ack_message():
    transport = LocalLoopbackTransport()
    service = NetSyncService(transport)

    service.send_ack(55)

    msgs = service.process_messages()
    assert len(msgs) == 1
    assert msgs[0].type == 'ack'
    assert msgs[0].payload['tick'] == 55
    assert 'received_ts' in msgs[0].payload
