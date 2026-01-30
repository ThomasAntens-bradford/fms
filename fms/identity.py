from fms.utils.general_utils import load_from_json, save_to_json
import subprocess

_operator = None
_author = None


def init_identity():
    global _operator, _author

    if _operator is not None and _author is not None:
        return

    operator_check = load_from_json("operator")
    if operator_check:
        _operator = operator_check.get("operator", "")
        _author = operator_check.get("author", "")
        return

    username = subprocess.check_output(
        [
            "powershell",
            "-Command",
            "(Get-WmiObject Win32_UserAccount -Filter \"Name='$env:USERNAME'\").FullName"
        ],
        text=True
    ).strip()

    name_parts = username.split(" ")
    first_name = name_parts[0] if len(name_parts) > 0 else ""
    last_name = name_parts[-1] if len(name_parts) > 1 else ""

    try:
        _author = first_name[0].upper() + "." + last_name.capitalize()
    except Exception:
        _author = "T.Antens"

    try:
        _operator = first_name[0].upper() + last_name[0].upper() + last_name[-1].upper()
    except Exception:
        _operator = "TAS"

    save_to_json({"operator": _operator, "author": _author}, "operator")


def get_operator():
    if _operator is None:
        init_identity()
    return _operator


def get_author():
    if _author is None:
        init_identity()
    return _author
