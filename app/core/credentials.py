from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_PCREDENTIALW = ctypes.POINTER(_CREDENTIALW)


class CredentialStore:
    """API key storage backed by Windows Credential Manager."""

    target_prefix = "Playgrounds/"

    def __init__(self) -> None:
        self._api = self._load_api()

    @staticmethod
    def _load_api() -> ctypes.WinDLL | None:
        if sys.platform != "win32":
            return None
        try:
            api = ctypes.WinDLL("advapi32", use_last_error=True)
        except OSError:
            log.warning("advapi32 unavailable, secrets will not persist")
            return None
        api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(_PCREDENTIALW),
        ]
        api.CredReadW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        api.CredFree.restype = None
        return api

    def _target(self, name: str) -> str:
        return f"{self.target_prefix}{name}"

    @property
    def available(self) -> bool:
        return self._api is not None

    def set_secret(self, name: str, secret: str) -> bool:
        if self._api is None or not secret:
            return False
        blob = secret.encode("utf-16-le")
        buffer = ctypes.create_string_buffer(blob, len(blob))
        credential = _CREDENTIALW()
        credential.Type = _CRED_TYPE_GENERIC
        credential.TargetName = self._target(name)
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))
        credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = name
        ok = bool(self._api.CredWriteW(ctypes.byref(credential), 0))
        if not ok:
            log.warning("CredWriteW failed: %s", ctypes.get_last_error())
        return ok

    def get_secret(self, name: str) -> str | None:
        if self._api is None:
            return None
        pointer = _PCREDENTIALW()
        ok = self._api.CredReadW(self._target(name), _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer))
        if not ok:
            error = ctypes.get_last_error()
            if error != _ERROR_NOT_FOUND:
                log.warning("CredReadW failed: %s", error)
            return None
        try:
            credential = pointer.contents
            size = credential.CredentialBlobSize
            raw = ctypes.string_at(credential.CredentialBlob, size) if size else b""
            return raw.decode("utf-16-le", errors="replace")
        finally:
            self._api.CredFree(pointer)

    def delete_secret(self, name: str) -> bool:
        if self._api is None:
            return False
        ok = bool(self._api.CredDeleteW(self._target(name), _CRED_TYPE_GENERIC, 0))
        if not ok:
            error = ctypes.get_last_error()
            if error != _ERROR_NOT_FOUND:
                log.warning("CredDeleteW failed: %s", error)
        return ok

    def has_secret(self, name: str) -> bool:
        return bool(self.get_secret(name))
