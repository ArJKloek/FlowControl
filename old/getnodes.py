from propar import master  # adjust import if needed

# Create a master connected to the RS485 port
m = master('/dev/ttyUSB1', baudrate=38400)

# Scan the RS485 network
nodes = m.get_nodes()

# Print found nodes
print("Found devices:")
for node in nodes:
    print(f"Address: {node['address']}, Type: {node['type']}, Serial: {node['serial']}, ID: {node['id']}, Channels: {node['channels']}")
