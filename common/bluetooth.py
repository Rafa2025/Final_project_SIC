# common/bluetooth.py

import os #Interface com o SO
import threading
import subprocess #Permite controlar hardware
import bluetooth
<<<<<<< HEAD
import subprocess
from dataclasses import dataclass
from typing import Dict, Callable, List

MessageCallback = Callable[[int, bytes], None]
LinkLossCallback = Callable[[int], None]  # link_id
=======
from dataclasses import dataclass #Para a criação de classes
from typing import Dict, Callable, List #Permite declarar tipos

MessageCallback = Callable[[int, bytes], None] #Define um esqueleto para funções
>>>>>>> 84af3c4f1867dd8fa7e063ec927ed77a440ec771

RFCOMM_PORT = 3  # Canal SPP RFCOMM

@dataclass
class DeviceInfo: #Informação sobre um dispositivo
    address: str
    name: str
    hop_count: int = -1


class BluetoothManager: #Gestor das comunicações Bluetooth RFCOMM (simula uma porta em série) do PyBluez 
                        #(biblioteca Python para comunicação Bluetooth) que suporta vários adaptadores (cada 
                        #instância liga-se a um)

<<<<<<< HEAD
    def __init__(self, enable_server: bool = False, adapter: str = "hci0"):
        self.enable_server = enable_server
        self.adapter = adapter     
        self.local_mac = self._get_mac_address()  
=======
    def __init__(self, enable_server: bool = False, adapter: str = "hci0"): #Construtor da classe
        self.enable_server = enable_server #Bool para determinar se funcionam como servidor (aceitam conexões de
                                           #conexões de outros dispositivos)
        self.adapter = adapter #Indica a que adaptador se conectar
        self.local_mac = self._get_mac_address() #Descobre a MAC address do adaptador utilizado
>>>>>>> 84af3c4f1867dd8fa7e063ec927ed77a440ec771

        os.environ["BLUETOOTH_DEVICE"] = self.adapter #Força o PyBluez a usar um adaptador específico

        self._callback: MessageCallback | None = None #Define a função de callback, é chamada cada vez que chegam
                                                      #dados a um socket
        self._next_link = 1 #Contador de links
        self._sockets: Dict[int, bluetooth.BluetoothSocket] = {} #Guarda os sockets (pontos de comunicação entre
                                                                 #dois dispositivos) que estão ativos
        self._recv_threads: Dict[int, threading.Thread] = {} #Guarda as threads criadas para cada conexão ativa

        self._server_sock: bluetooth.BluetoothSocket | None = None #Socket que espera por pedidos de conexão
                                                                   #feitos por outros dispositivos

        print(f"[BT] Initialized on adapter {self.adapter} ({self.local_mac})")

        # Set initial name
        initial_hop = 0 if enable_server else -1
        self.set_name(f"MESH|{initial_hop}")
        self._on_link_loss: LinkLossCallback | None = None
    
    
    def set_link_loss_callback(self, callback: LinkLossCallback) -> None:
        self._on_link_loss = callback

    # ---------------------------------------------------------------
    # Utility: Get MAC address of selected adapter
    # ---------------------------------------------------------------
    def _get_mac_address(self) -> str:
        try:
            out = subprocess.check_output(["hciconfig", self.adapter]).decode()
            for line in out.splitlines():
                line = line.strip()
                if "BD Address:" in line:
                    return line.split()[2]
        except:
            pass
        raise RuntimeError(f"Cannot find MAC for {self.adapter}")
    
    def set_name(self, name: str) -> None:
        try:
            subprocess.check_call(["hciconfig", self.adapter, "name", name])
            print(f"[BT] Set device name to {name} on {self.adapter}")
        except Exception as e:
            print(f"[BT] Failed to set name: {e}")

    # ================================================================
    # START
    # ================================================================
    def start(self, callback: MessageCallback):
        self._callback = callback

        if self.enable_server:
            self.start_server()
        else:
            print("[BT] Server disabled (client-only mode).")

    # ================================================================
    # SERVER (Sink only)
    # ================================================================
    def start_server(self):
        print(f"[BT] Starting RFCOMM server on {self.adapter} ({self.local_mac})...")

        try:
            server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)

            # NEW: bind to a specific adapter via MAC
            server_sock.bind(("", RFCOMM_PORT))

            server_sock.listen(10)
        except Exception as e:
            print(f"[BT] ERROR starting server: {e}")
            raise

        self._server_sock = server_sock
        print(f"[BT] RFCOMM server listening on channel {RFCOMM_PORT} @ {self.adapter}")

        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()

    def _accept_loop(self):
        server = self._server_sock
        while True:
            try:
                client_sock, addr = server.accept()
                print(f"[BT] Incoming connection from {addr}")

                link_id = self._next_link
                self._next_link += 1
                self._sockets[link_id] = client_sock

                t = threading.Thread(target=self._recv_loop, args=(link_id,), daemon=True)
                t.start()
                self._recv_threads[link_id] = t

            except Exception as e:
                print(f"[BT] Server accept failed: {e}")
                return

    # ================================================================
    # CLIENT MODE (Nodes)
    # ================================================================
    def connect_to(self, address: str) -> int:
        print(f"[BT] Connecting via {self.adapter} ({self.local_mac}) to {address}...")

        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)

        # NEW: bind outbound socket to adapter
        sock.connect((address, RFCOMM_PORT))

        link_id = self._next_link
        self._next_link += 1
        self._sockets[link_id] = sock

        print(f"[BT] Connected on link {link_id} using {self.adapter}")

        t = threading.Thread(target=self._recv_loop, args=(link_id,), daemon=True)
        t.start()
        self._recv_threads[link_id] = t

        return link_id

    # ================================================================
    # SCAN
    # ================================================================
    def scan_nearby(self) -> List[DeviceInfo]:
        print(f"[BT] Scanning on adapter {self.adapter}...")

        raw = bluetooth.discover_devices(lookup_names=True)

        devices = []
        for addr, name in raw:
            hop = -1
            if "|" in name:
                try:
                    hop = int(name.split("|")[1])
                except:
                    pass
            devices.append(DeviceInfo(address=addr, name=name, hop_count=hop))

        return devices

    # ================================================================
    # SEND
    # ================================================================
    def send(self, link_id: int, data: bytes):
        sock = self._sockets.get(link_id)
        if not sock:
            print(f"[BT] ERROR: link {link_id} not found")
            return

        try:
            sock.send(data)
        except Exception as e:
            print(f"[BT] Send error: {e}")

    # ================================================================
    # RECEIVE LOOP
    # ================================================================
    def _recv_loop(self, link_id: int):
        sock = self._sockets[link_id]
        while link_id in self._sockets:  # Check if socket still exists
            try:
                data = sock.recv(4096)
                if not data:
                    print(f"[BT] Link {link_id}: closed by peer (empty recv)")
                    if self._on_link_loss:
                        self._on_link_loss(link_id)
                    self.disconnect(link_id)
                    return

                if self._callback:
                    self._callback(link_id, data)

            except OSError as e:
                if e.errno in (9, 107, 32):  # Bad fd, transport shutdown, broken pipe
                    print(f"[BT] Link {link_id}: socket closed ({e})")
                    if self._on_link_loss:
                        self._on_link_loss(link_id)
                    self.disconnect(link_id)
                    return
                else:
                    print(f"[BT] Temporary receive error on link {link_id}: {e}")
                    continue  # Retry on temporary errors

            except Exception as e:
                print(f"[BT] Unexpected receive error on link {link_id}: {e}")
                if self._on_link_loss:
                    self._on_link_loss(link_id)
                self.disconnect(link_id)
                return

    # ================================================================
    # DISCONNECT
    # ================================================================
    def disconnect(self, link_id: int):
        sock = self._sockets.get(link_id)
        if not sock:
            return

        print(f"[BT] Closing link {link_id}")
        try:
            sock.close()
        except:
            pass

        del self._sockets[link_id]

    # ================================================================
    # STOP
    # ================================================================
    def stop(self):
        print("[BT] Stopping Bluetooth Manager...")

        for lid in list(self._sockets.keys()):
            self.disconnect(lid)

        if self._server_sock:
            try:
                self._server_sock.close()
            except:
                pass

        print("[BT] Manager stopped")

