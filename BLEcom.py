import asyncio
import threading
import queue
from typing import Optional, Tuple


class BLEComm:
    def __init__(self, address: str):
        from bleak import BleakClient

        self.address = address
        self._client = BleakClient(address)

        self._rx_queue: "queue.Queue[bytes]" = queue.Queue()
        self._stop_evt = threading.Event()

        self._loop = None
        self._thread = threading.Thread(target=self._thread_main, daemon=True)

        self._connected = False
        self._connect_failed = False
        self._last_error = None

        self._rx_uuid: Optional[str] = None
        self._tx_uuid: Optional[str] = None

        self._thread.start()

        if not self._wait_connected(8.0):
            if self._last_error:
                raise RuntimeError(self._last_error)
            raise RuntimeError(f"BLE connect timeout to {address}")

    def _wait_connected(self, timeout_s: float) -> bool:
        import time

        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self._connected:
                return True
            if self._connect_failed:
                return False
            time.sleep(0.05)
        return False

    def _thread_main(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._async_run())
        finally:
            try:
                self._loop.stop()
            except Exception:
                pass
            try:
                self._loop.close()
            except Exception:
                pass

    @staticmethod
    def _pick_chars(services) -> Tuple[Optional[str], Optional[str]]:
        notify = []
        write_wo = []
        write = []

        for service in services:
            for ch in service.characteristics:
                props = set(ch.properties or [])

                if "notify" in props or "indicate" in props:
                    notify.append((service.uuid, ch.uuid))

                if "write_without_response" in props:
                    write_wo.append((service.uuid, ch.uuid))

                if "write" in props:
                    write.append((service.uuid, ch.uuid))

        write_candidates = write_wo if write_wo else write

        if not notify:
            raise RuntimeError("Aucune characteristic NOTIFY ou INDICATE trouvée.")
        if not write_candidates:
            raise RuntimeError("Aucune characteristic WRITE trouvée.")

        notify_by_service = {}
        for svc_uuid, ch_uuid in notify:
            notify_by_service.setdefault(svc_uuid, []).append(ch_uuid)

        for svc_uuid, ch_uuid in write_candidates:
            if svc_uuid in notify_by_service:
                return ch_uuid, notify_by_service[svc_uuid][0]

        return write_candidates[0][1], notify[0][1]

    @staticmethod
    def _gatt_summary(services) -> str:
        lines = ["GATT services détectés :"]

        for service in services:
            lines.append(f"Service {service.uuid}")
            for ch in service.characteristics:
                props = ",".join(ch.properties or [])
                lines.append(f"  Characteristic {ch.uuid} [{props}]")

        return "\n".join(lines)

    async def _async_run(self):

        async def _on_notify(_, data: bytearray):
            self._rx_queue.put(bytes(data))

        try:
            await self._client.connect()

            # CORRECTION ICI
            services = self._client.services

            rx_uuid, tx_uuid = self._pick_chars(services)

            self._rx_uuid = rx_uuid
            self._tx_uuid = tx_uuid

            self._connected = True

            await self._client.start_notify(self._tx_uuid, _on_notify)

            print(f"Notify enabled on {self._tx_uuid}")
            print(f"Write characteristic: {self._rx_uuid}")

            while not self._stop_evt.is_set():
                await asyncio.sleep(0.05)

        except Exception as e:
            self._last_error = f"BLE error: {repr(e)}"
            self._connect_failed = True
            self._connected = False
            print(self._last_error)

        finally:
            try:
                if self._tx_uuid:
                    await self._client.stop_notify(self._tx_uuid)
            except Exception:
                pass

            try:
                await self._client.disconnect()
            except Exception:
                pass

            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._loop.stop)

    def write(self, data: bytes):
        if not self._loop or self._loop.is_closed() or not self._connected:
            return

        async def _awrite():
            try:
                await self._client.write_gatt_char(
                    self._rx_uuid, data, response=False
                )
            except Exception:
                pass

        asyncio.run_coroutine_threadsafe(_awrite(), self._loop)

    def read(self) -> bytes:
        out = bytearray()
        try:
            while len(out) < 1024:
                out += self._rx_queue.get_nowait()
        except queue.Empty:
            pass
        return bytes(out)

    def close(self):
        self._stop_evt.set()