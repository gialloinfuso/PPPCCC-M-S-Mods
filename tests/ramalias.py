# RAM-Loch hinter dem BSS: 0x42330000..0x4233ffff (gecacht) und 0x4a330000..0x4a33ffff (ungecachter Spiegel) sind auf
# der Maschine derselbe Speicher. Im Emulator beide Adressen auf denselben Puffer legen.
import ctypes
from unicorn import UC_PROT_ALL
_keep = []
def map_ram(uc):
    buf = ctypes.create_string_buffer(0x10000); _keep.append(buf)
    uc.mem_map_ptr(0x4A330000, 0x10000, UC_PROT_ALL, ctypes.addressof(buf))
    uc.mem_map_ptr(0x42330000, 0x10000, UC_PROT_ALL, ctypes.addressof(buf))
