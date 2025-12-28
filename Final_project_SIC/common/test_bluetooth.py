from common.bluetooth import BluetoothManager

def callback(link_id, data):
    print(f"[TEST] Received from link {link_id}: {data}")

def main():
    bt = BluetoothManager()
    bt.start(callback)

    print("[TEST] SCANNING...")
    devices = bt.scan_nearby()

    for d in devices:
        print(f"Found device: {d.address}  name={d.name} hop={d.hop_count}")

if __name__ == "__main__":
    main()
