# Projeto Final Segurança Informática e nas Comunicações
---
## How to execute
1. Start in other pc or dongle sink:
```
 python3 -m sync.main_sink
```
2. Start the node:
```
python3 -m node.main_node
```
*Note: Gives an error, it generates the network id (nid)*
3. Issue node certificate:
```
bash issue_device_cert.sh
```. After getting the node id (nid). Do:
```
python3 -m node.main_node <nid>
```
5. After establish connections, the interface is intuitive.
