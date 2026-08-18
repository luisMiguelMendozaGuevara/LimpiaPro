"""Registry transaction tests using an in-memory winreg substitute."""

import pytest

from limpiapro import startup


class FakeKey:
    def __init__(self, registry, hive, subkey):
        self.registry = registry
        self.hive = hive
        self.subkey = subkey

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeRegistry:
    HKEY_CURRENT_USER = "HKCU"
    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}
        self.fail_delete = False

    def CreateKey(self, hive, subkey):
        return FakeKey(self, hive, subkey)

    def OpenKey(self, hive, subkey, *_args):
        return FakeKey(self, hive, subkey)

    def QueryValueEx(self, key, name):
        try:
            return self.values[(key.hive, key.subkey, name)]
        except KeyError as exc:
            raise OSError("missing") from exc

    def SetValueEx(self, key, name, _reserved, value_type, value):
        self.values[(key.hive, key.subkey, name)] = (value, value_type)

    def DeleteValue(self, key, name):
        if self.fail_delete and key.subkey == "Run":
            raise OSError("delete failed")
        self.values.pop((key.hive, key.subkey, name), None)


def test_registry_transfer_rolls_back_destination_on_source_failure(monkeypatch):
    fake = FakeRegistry()
    fake.values[("HKCU", "Run", "MyApp")] = ("C:\\app.exe", fake.REG_SZ)
    fake.fail_delete = True
    monkeypatch.setattr(startup, "winreg", fake)

    with pytest.raises(OSError):
        startup._reg_transfer("HKCU", "Run", "HKCU", "RunDisabled", "MyApp", "C:\\app.exe")

    assert ("HKCU", "RunDisabled", "MyApp") not in fake.values
    assert fake.values[("HKCU", "Run", "MyApp")] == ("C:\\app.exe", fake.REG_SZ)


def test_disabled_startup_filters_entries_still_active(monkeypatch):
    monkeypatch.setattr(
        startup,
        "_read_reg_entries",
        lambda hive, key: {"App": "C:\\app.exe"} if "Disabled" in key else {"App": "C:\\app.exe"},
    )
    monkeypatch.setattr(startup.os.path, "isdir", lambda _path: False)

    assert startup.get_disabled_startup() == []
