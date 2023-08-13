from __future__ import annotations

import ctypes
import fcntl
import logging
import socket
from typing import Any

_LOGGER = logging.getLogger(__name__)

# https://man.freebsd.org/cgi/man.cgi?query=bt_gethostbyname&apropos=0&sektion=3&manpath=FreeBSD+13.2-RELEASE+and+Ports&arch=default&format=html
# misc: https://github.com/freebsd/freebsd-src/blob/main/sys/netgraph/bluetooth/include/ng_hci.h#L82
AF_BLUETOOTH = 36  # sys/sys/socket.h#L265
PF_BLUETOOTH = AF_BLUETOOTH
BTPROTO_HCI = (
    134  # "BLUETOOTH_PROTO_HCI" sys/netgraph/bluetooth/include/ng_btsocket.h#L43
)
HCI_MAX_DEV = 16  # HCI_DEVMAX=32 lib/libbluetooth/bluetooth.h#L99 or MAX_NODE_NUM=16 in hccontrol.h?

# _IOWR('b', NGM_HCI_NODE_LIST_NAMES, struct ng_btsocket_hci_raw_node_list_names)
HCIGETDEVLIST = 0xC01062C8

# _IOWR('b', NGM_HCI_NODE_GET_CON_LIST, struct ng_btsocket_hci_raw_con_list)
# bt_devinquiry()
HCIGETDEVINFO = 0xC010626F

NG_HCI_FEATURES_SIZE = 8  # sys/netgraph/bluetooth/include/ng_hci.h#L82
NG_NODESIZ = 32


# lib/libbluetooth/bluetooth.h#L143
class hci_dev_req(ctypes.Structure):
    _fields_ = [("dev_id", ctypes.c_uint16), ("dev_opt", ctypes.c_uint32)]


# usr.sbin/bluetooth/hccontrol/node.c#L461
# hci_read_node_list()
class hci_dev_list_req(ctypes.Structure):
    _fields_ = [("dev_num", ctypes.c_uint16), ("dev_req", hci_dev_req * HCI_MAX_DEV)]


class bdaddr_t(ctypes.Structure):
    _fields_ = [("b", ctypes.c_uint8 * 6)]  # hg_hci.h NG_HCI_BDADDR_SIZE

    def __str__(self) -> str:
        return ":".join(["%02X" % x for x in reversed(self.b)])


# https://github.com/freebsd/freebsd-src/blob/main/lib/libbluetooth/bluetooth.h#L124
class hci_dev_stats(ctypes.Structure):
    _fields_ = [
        # ("err_rx", ctypes.c_uint32),
        # ("err_tx", ctypes.c_uint32),
        ("cmd_sent", ctypes.c_uint32),
        ("evt_recv", ctypes.c_uint32),
        ("acl_recv", ctypes.c_uint32),
        ("acl_sent", ctypes.c_uint32),
        ("sco_recv", ctypes.c_uint32),
        ("sco_sent", ctypes.c_uint32),
        ("bytes_recv", ctypes.c_uint32),
        ("bytes_sent", ctypes.c_uint32),
    ]


# https://github.com/freebsd/freebsd-src/blob/main/lib/libbluetooth/bluetooth.h#L103
class hci_dev_info(ctypes.Structure):
    _fields_ = [
        # ("dev_id", ctypes.c_uint16), # nodeinfo->id
        ("devname", ctypes.c_char * NG_NODESIZ),
        ("bdaddr", bdaddr_t),
        ("state", ctypes.c_uint32),
        # ("type", ctypes.c_uint8),  # nodeinfo->type?
        ("features", ctypes.c_uint8 * NG_HCI_FEATURES_SIZE),
        ("packet_type_info", ctypes.c_uint16),
        ("link_policy_info", ctypes.c_uint16),
        ("role_switch_info", ctypes.c_uint16),
        # ("link_mode", ctypes.c_uint32),
        ("acl_size", ctypes.c_uint16),
        ("acl_pkts", ctypes.c_uint16),
        ("sco_size", ctypes.c_uint16),
        ("sco_pkts", ctypes.c_uint16),
        ("stat", hci_dev_stats),
    ]


hci_dev_info_p = ctypes.POINTER(hci_dev_info)


# https://github.com/freebsd/freebsd-src/blob/main/lib/libbluetooth/hci.c#L713
def get_adapters_from_hci() -> dict[int, dict[str, Any]]:
    """Get bluetooth adapters from HCI."""
    out: dict[int, dict[str, Any]] = {}
    sock: socket.socket | None = None
    try:
        sock = socket.socket(AF_BLUETOOTH, socket.SOCK_RAW, BTPROTO_HCI)
        buf = hci_dev_list_req()
        buf.dev_num = HCI_MAX_DEV
        # hccontrol -n ubt0hci read_node_list  =>  bt_devenum()
        # if (ioctl(s, SIOC_HCI_RAW_NODE_LIST_NAMES, &r, sizeof(r)) < 0) {
        ret = fcntl.ioctl(sock.fileno(), HCIGETDEVLIST, buf)
        if ret < 0:
            raise OSError(f"HCIGETDEVLIST failed: {ret}")
        for i in range(buf.dev_num):
            dev_req = buf.dev_req[i]
            dev = hci_dev_info()
            dev.dev_id = dev_req.dev_id
            # hci.c#L600 // bt_devinfo()
            ret = fcntl.ioctl(sock.fileno(), HCIGETDEVINFO, dev)
            info = {str(k): getattr(dev, k) for k, v_ in dev._fields_}
            info["bdaddr"] = str(info["bdaddr"])
            info["devname"] = info["devname"].decode()  # "ubt0hci"
            out[int(dev.dev_id)] = info
    except OSError as error:
        _LOGGER.debug("Error while getting HCI devices: %s", error)
        return out
    except Exception as error:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected error while getting HCI devices: %s", error)
        return out
    finally:
        if sock:
            sock.close()
    return out
