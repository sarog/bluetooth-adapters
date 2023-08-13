from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import aiohttp
import async_timeout
from mac_vendor_lookup import AsyncMacLookup
from usb_devices import BluetoothDevice, NotAUSBDeviceError

from ..adapters import BluetoothAdapters
from ..const import FREEBSD_DEFAULT_BLUETOOTH_ADAPTER
from ..history import AdvertisementHistory
from ..models import AdapterDetails
from .freebsd_hci import get_adapters_from_hci

_LOGGER = logging.getLogger(__name__)

class FreeBSDAdapters(BluetoothAdapters):
    """Class for getting the bluetooth adapters on a FreeBSD system."""

    def __init__(self) -> None:
        """Initialize the adapter."""
        self._adapters: dict[str, AdapterDetails] | None = None
        self._devices: dict[str, BluetoothDevice] = {}
        self._mac_vendor_lookup: AsyncMacLookup | None = None
        self._hci_output: dict[int, dict[str, Any]] | None = None
    async def refresh(self) -> None:
        """Refresh the adapters."""
        await asyncio.get_running_loop().run_in_executor(
            None, self._create_bluetooth_devices
        )
        if not self._mac_vendor_lookup:
            await self._async_setup()
        self._adapters = None
    async def _async_setup(self) -> None:
        self._mac_vendor_lookup = AsyncMacLookup()
        with contextlib.suppress(
            asyncio.TimeoutError, aiohttp.ClientError, asyncio.TimeoutError
        ):
            # We don't care if this fails since it only
            # improves the data we get.
            async with async_timeout.timeout(3):
                await self._mac_vendor_lookup.load_vendors()
    def _async_get_vendor(self, mac_address: str) -> str | None:
        """Lookup the vendor."""
        assert self._mac_vendor_lookup is not None  # nosec
        oui = self._mac_vendor_lookup.sanitise(mac_address)[:6]
        vendor: bytes | None = self._mac_vendor_lookup.prefixes.get(oui.encode())
        return vendor.decode()[:254] if vendor is not None else None
    def _create_bluetooth_devices(self) -> None:
        """Create the bluetooth devices."""
        self._hci_output = get_adapters_from_hci()
        self._devices = {}
        # for adapter in self._bluez.adapter_details:
        #     i = int(adapter[3:])
        #     dev = BluetoothDevice(i)
        #     self._devices[adapter] = dev
        #     try:
        #         dev.setup()
        #     except NotAUSBDeviceError:
        #         continue
        #     except FileNotFoundError:
        #         continue
        #     except Exception:  # pylint: disable=broad-except
        #         _LOGGER.exception("Unexpected error setting up device hci%s", dev)
    # @property
    # def history(self) -> dict[str, AdvertisementHistory]:
    #     """Get the bluez history."""
    #     return self._bluez.history

    @property
    def adapters(self) -> dict[str, AdapterDetails]:
        """Get the adapter details."""
        if self._adapters is None:
            adapters: dict[str, AdapterDetails] = {}
            if self._hci_output:
                for hci_details in self._hci_output.values():
                    name = hci_details["devname"]
                    mac_address = hci_details["bdaddr"].upper()
                    manufacturer = self._async_get_vendor(mac_address)
                    adapters[name] = AdapterDetails(
                        address=mac_address,
                        sw_version="Unknown",
                        hw_version=None,
                        passive_scan=False,  # assume false if we don't know
                        manufacturer=manufacturer,
                        product=None,
                        vendor_id=None,
                        product_id=None,
                    )
            self._adapters = adapters
        return self._adapters
    @property
    def default_adapter(self) -> str:
        """Get the default adapter."""
        return FREEBSD_DEFAULT_BLUETOOTH_ADAPTER
