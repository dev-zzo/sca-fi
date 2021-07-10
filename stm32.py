from chipwhisperer.capture.targets.simpleserial_readers.cwlite import SimpleSerial_ChipWhispererLite

class BootloaderError(Exception):
    "Generic bootloader error"
    pass
class TimeoutError(BootloaderError):
    "Communications timeout"
    pass
class ProtocolError(BootloaderError):
    "Data exchange protocol error"
    pass
class CommandError(BootloaderError):
    "Command execution error"
    pass

def _append_checksum(data):
    "Compute and append the checksum"

    cs = 0
    if len(data) == 1:
        cs = (~data[0]) & 0xFF
    else:
        for x in data:
            cs ^= x
    return data + cs.to_bytes(1, "big")

class Bootloader:
    ACK = 0x79
    NAK = 0x1F
    def __init__(self, scope, baudrate=57600, debug=False):
        self.debug = debug
        self.serif = SimpleSerial_ChipWhispererLite()
        self.serif.con(scope)
        self.serif.cwlite_usart.init(baud=baudrate, parity="even")
        
    def setup(self):
        self.serif.flush()
        self._do_autobaud()

    def read(self, count, timeout=250):
        data = bytearray(self.serif.hardware_read(count, timeout))
        if self.debug:
            print("Read: '" + data.hex() + "'")
        return data
    
    def write(self, data):
        if self.debug:
            print("Write: '" + data.hex() + "'")
        self.serif.hardware_write(data)
        
    def _receive_bytes(self, count):
        "Receive N bytes from the port"

        buffer = b''
        while count > 0:
            chunk = self.read(count)
            if not chunk:
                raise TimeoutError("receiving data")
            buffer += chunk
            count -= len(chunk)
        return buffer

    def _receive_ack(self, timeout=None):
        "Receive and verify the ACK byte"
        if timeout is None:
            timeout = 250
        ack = self.read(1, timeout=timeout)
        if not ack:
            raise TimeoutError("receiving ACK")
        ack = ack[0]
        if ack == Bootloader.ACK:
            return True
        if ack == Bootloader.NAK:
            return False
        raise ProtocolError("unexpected response: %02x" % ack)

    def _send_data_check_ack(self, data):
        self.write(_append_checksum(data))
        return self._receive_ack()

    def _receive_data_check_ack(self, count):
        data = self._receive_bytes(count)
        if not self._receive_ack():
            raise ProtocolError("expected ACK; got NAK instead")
        return data

    def _do_autobaud(self):
        self.write(b"\x7F")
        if not self._receive_ack():
            raise ProtocolError("autobaud failed")

    def read_memory(self, addr, count):
        "Read memory region"

        if not self._send_data_check_ack(b"\x11"):
            raise CommandError("read protection is enabled")
        if not self._send_data_check_ack(addr.to_bytes(4, "big")):
            raise CommandError("address is rejected by the device")
        if not self._send_data_check_ack((count - 1).to_bytes(1, "big")):
            raise CommandError("count is rejected by the device")
        rsp = self._receive_bytes(count)
        return rsp

    def write_memory(self, addr, data):
        "Write memory region"
        
        if not self._send_data_check_ack(b"\x31"):
            raise CommandError("read protection is enabled")
        if not self._send_data_check_ack(addr.to_bytes(4, "big")):
            raise CommandError("address is rejected by the device")
        if not self._send_data_check_ack((count - 1).to_bytes(1, "big")):
            raise CommandError("checksum error")
        # NOTE: according to the diagram in AN3155, 
        # NAK is not sent if memory address is invalid
    
    def readout_protect(self):
        "Enable readout protection on the device"
        if not self._send_data_check_ack(b"\x82"):
            raise CommandError("read protection is already enabled")
        self._receive_ack(10000)

    def readout_unprotect(self):
        "Disable readout protection on the device"
        if not self._send_data_check_ack(b"\x92"):
            raise CommandError("something went wrong")
        self._receive_ack(10000)