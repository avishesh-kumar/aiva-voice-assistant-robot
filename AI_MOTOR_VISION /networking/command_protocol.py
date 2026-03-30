import json
import struct
from typing import List, Dict


def encode_message(obj: dict) -> bytes:
    """
    Encode a dictionary as a framed JSON message.
    
    Format:
    - 4 bytes big-endian unsigned int = payload length
    - followed by UTF-8 JSON bytes
    
    Args:
        obj: Dictionary to encode
        
    Returns:
        bytes: Framed message ready for transmission
    """
    # Convert dictionary to JSON string, then to UTF-8 bytes
    json_bytes = json.dumps(obj).encode('utf-8')
    
    # Get payload length (big-endian 4-byte unsigned integer)
    length_bytes = struct.pack('>I', len(json_bytes))
    
    # Combine length prefix and JSON payload
    return length_bytes + json_bytes


def decode_messages(buffer: bytearray) -> List[dict]:
    """
    Extract complete framed messages from buffer.
    
    Process:
    1. Read 4-byte length prefix
    2. Read that many bytes of JSON payload
    3. Parse JSON to dictionary
    4. Remove processed bytes from buffer
    5. Repeat until insufficient bytes remain
    
    Args:
        buffer: Bytearray containing received data
        
    Returns:
        List[dict]: List of decoded messages
    """
    messages = []
    
    while True:
        # Need at least 4 bytes to read the length
        if len(buffer) < 4:
            break
            
        # Read the 4-byte length prefix (big-endian)
        length_prefix = buffer[:4]
        payload_length = struct.unpack('>I', length_prefix)[0]
        
        # Check if we have the complete payload
        if len(buffer) < 4 + payload_length:
            # Not enough data for complete message
            break
            
        # Extract the JSON payload
        json_bytes = buffer[4:4 + payload_length]
        
        try:
            # Decode JSON
            message = json.loads(json_bytes.decode('utf-8'))
            messages.append(message)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # Skip invalid JSON, but still remove it from buffer
            print(f"Warning: Failed to decode message: {e}")
        
        # Remove processed bytes from buffer
        del buffer[:4 + payload_length]
    
    return messages


# Alternative version that returns new buffer (non-destructive)
def decode_messages_with_new_buffer(buffer: bytes) -> tuple[List[dict], bytes]:
    """
    Extract complete framed messages from buffer without modifying original.
    
    Returns:
        tuple[List[dict], bytes]: 
            - List of decoded messages
            - Remaining buffer bytes (incomplete message)
    """
    messages = []
    pos = 0
    
    while True:
        # Need at least 4 bytes to read the length
        if len(buffer) - pos < 4:
            break
            
        # Read the 4-byte length prefix (big-endian)
        length_prefix = buffer[pos:pos + 4]
        payload_length = struct.unpack('>I', length_prefix)[0]
        
        # Check if we have the complete payload
        if len(buffer) - pos < 4 + payload_length:
            # Not enough data for complete message
            break
            
        # Extract the JSON payload
        json_bytes = buffer[pos + 4:pos + 4 + payload_length]
        
        try:
            # Decode JSON
            message = json.loads(json_bytes.decode('utf-8'))
            messages.append(message)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # Skip invalid JSON, but still advance position
            print(f"Warning: Failed to decode message: {e}")
        
        # Move to next message
        pos += 4 + payload_length
    
    # Return remaining buffer (from current position to end)
    return messages, buffer[pos:]


# Example usage:
if __name__ == "__main__":
    # Test encoding
    test_msg = {"type": "chat", "text": "Hello, world!", "timestamp": 1234567890}
    framed = encode_message(test_msg)
    print(f"Encoded message length: {len(framed)} bytes")
    print(f"First 4 bytes (length): {framed[:4].hex()}")
    print(f"Payload: {framed[4:].decode('utf-8')}")
    
    # Test decoding with multiple messages
    buffer = bytearray()
    
    # Add two complete messages
    msg1 = {"type": "chat", "text": "First"}
    msg2 = {"type": "chat", "text": "Second"}
    
    buffer.extend(encode_message(msg1))
    buffer.extend(encode_message(msg2))
    buffer.extend(b"incomplete")  # Add some trailing incomplete data
    
    print(f"\nBuffer size: {len(buffer)} bytes")
    
    # Decode complete messages
    messages = decode_messages(buffer)
    print(f"Decoded {len(messages)} messages: {messages}")
    print(f"Remaining buffer size: {len(buffer)} bytes")
    print(f"Remaining buffer content: {buffer}")
    
    # Test with alternative non-destructive version
    print("\n--- Testing non-destructive version ---")
    buffer_bytes = b""
    buffer_bytes += encode_message(msg1)
    buffer_bytes += encode_message(msg2)
    buffer_bytes += b"partial"
    
    messages, remaining = decode_messages_with_new_buffer(buffer_bytes)
    print(f"Decoded {len(messages)} messages: {messages}")
    print(f"Remaining buffer: {remaining}")
    print(f"Original buffer unchanged: {len(buffer_bytes)} bytes")
