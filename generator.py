from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import io
import zipfile
import re
import logging
from typing import List, Dict, Optional, Tuple

TEMPLATE_DIR = Path("templates")
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape([]),
    trim_blocks=True,
    lstrip_blocks=True,
)

logger = logging.getLogger(__name__)


def list_templates() -> List[str]:
    return sorted([p.name for p in TEMPLATE_DIR.glob("*.j2")])


def choose_template(model: str, backhaul: str, software: str = "", role: str = "", available_templates: Optional[List[str]] = None) -> str:
    """
    Selects the best template based on model, software version, backhaul type, and role.
    """
    model = (model or "").strip()
    backhaul = (backhaul or "").strip()
    software = (software or "").strip()
    role = (role or "").strip()
    
    if available_templates is None:
        available_templates = list_templates()

    candidates = []
    
    # Priority 1: Model + Software
    if model and software:
        candidates.append(f"ciena_{model}_{software}.cfg.j2")
        
    # Priority 2: Model + Software + Backhaul
    if model and software and backhaul:
        candidates.append(f"ciena_{model}_{software}_{backhaul}.cfg.j2")

    # Priority 3: Model + Backhaul (Legacy behavior)
    if model and backhaul:
        candidates += [
            f"ciena_{model}_{backhaul}.cfg.j2",
            f"ciena_{model}_{backhaul}_backhaul.cfg.j2",
            f"ciena_{model}_{backhaul.replace('-', '_')}.cfg.j2",
        ]
        
    # Priority 4: Model + Role
    if model and role:
        candidates.append(f"ciena_{model}_{role}.cfg.j2")
        
    # Priority 5: Model only
    if model:
        candidates.append(f"ciena_{model}.cfg.j2")
        
    candidates.append("ciena_generic.cfg.j2")

    for c in candidates:
        if c in available_templates:
            return c

    # fallback: return generic name
    return "ciena_generic.cfg.j2"


def render_template(template_name: str, context: Dict) -> str:
    tmpl = env.get_template(template_name)
    return tmpl.render(**context)


def get_model_defaults(model: str) -> Dict[str, List[str]]:
    m = (model or "").strip()
    
    # Common secret for 39xx/51xx legacy (Example)
    default_secret = "#A#ZlFm6R4dQ0uR4D6rOjaXTMIoNnKVa9BP+s1VMFnBseL+AN66GjfDOwDrLXWCDUZc2dpW54ThKyWUfwFHN+CL3/B+2uqaL2URdzrB8ecyNHlfAYNWZ+1GhbOrCAJq5YwfZsPqN0yWRIfnzswlQhsJnrzTirtK/t9+3skXxLeNIZcr9hbpkGZGtzofwNs/IHA9TW21N9n61M8ms79egItUriziJoSq3XBp1FFUf1E5VRQ61CE0FKCQt+9DxjMDvPzV"
    
    defaults_map = {
        "3903": {
            "tacacs_secret": "#A#xTyOFCALzN92CljilIM/PQmofDrCIdFBXGjyCqe9TzldvYG17jjKp4xXs/25wAHlk0tq5hO9ei4C0QoI7cZckeqHNFEAS6VYCoVxXwDkJ33gvx4tm3Dn73t3sHs37DGvxPi6Mhag0jKYGu50QiD+jKbIn52PMOXOjgOyUETLvByBN4X2LSIQ1vhYPPSKjpdQ5fH1huIZgnSfJvs3p6/sqbs4Ms+u0flvn77Z1SEqFHD0vfdahHY4LM79is9ynsWu",
            "license_keys": ["W9FOI8C7N3NIB4", "WAFOI8C7N3NJB6", "W61WI8C7N3NKXB"],
        },
        "3916": {
            "tacacs_secret": default_secret,
            "license_keys": ["W5FNI8C7N3YNM4", "W61WI8C7N3NKXB", "W9FNI8C7N3YLM6", "WAFNI8C7N3YMM8"],
        },
        "3926": {
            "tacacs_secret": default_secret,
            "license_keys": ["WDFTI8C7N430RW", "W5FTI8C7N431RP", "WCFTI8C7N432RX", "W6FTI8C7N433RS"],
        },
        "3928": {
            "tacacs_secret": default_secret,
            "license_keys": ["WDFUI8C7N3NLBH", "W5FUI8C7N4ZEN3", "WCFUI8C7N3NMBH", "W6FUI8C7N3NNBC"],
        },
        # For new models, providing placeholders to prevent errors. 
        # Update these with real default license keys if you have them.
        "5142": {"tacacs_secret": default_secret, "license_keys": ["<5142-KEY-PLACEHOLDER>"]},
        "5130": {"tacacs_secret": default_secret, "license_keys": ["<5130-KEY-PLACEHOLDER>"]},
        "5171": {"tacacs_secret": default_secret, "license_keys": ["<5171-KEY-PLACEHOLDER>"]},
        "8110": {"tacacs_secret": default_secret, "license_keys": ["<8110-KEY-PLACEHOLDER>"]},
        "8114": {"tacacs_secret": default_secret, "license_keys": ["<8114-KEY-PLACEHOLDER>"]},
    }
    return defaults_map.get(m, {
        "tacacs_secret": "vault://ciena/default/tacacs",
        "license_keys": ["<LICENSE-PLACEHOLDER-1>"]
    })


def safe_filename(s: str) -> str:
    # keep common safe chars; normalize spaces -> underscore
    s = re.sub(r"\s+", "_", s)
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)


def create_zip_from_dict(files: Dict[str, str]) -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for fname, content in files.items():
            z.writestr(fname, content)
    return mem.getvalue()


def _build_interfaces_from_backhaul(dev: Dict) -> List[Dict]:
    interfaces = []
    backhaul = dev.get("backhaul", "") or ""
    aggregation_enabled = bool(dev.get("aggregation_enabled"))

    def normalize_port(port_raw):
        if isinstance(port_raw, (list, tuple)):
            return str(port_raw[0]) if port_raw else ""
        return str(port_raw or "")

    if backhaul == "single":
        port = normalize_port(dev.get("single_port"))
        interfaces.append({
            "name": dev.get("single_if_name") or (f"Port_{port}" if port else "Port_BH"),
            "description": "BACKHAUL",
            "vlan": dev.get("single_vlan"),
            "ip": dev.get("single_ip"),
            "mtu": dev.get("single_mtu"),
            "port": dev.get("aggregation_name") if aggregation_enabled else dev.get("single_port"),
            "neighbor_name": dev.get("single_neighbor_name"),
            "neighbor_port": dev.get("single_neighbor_port"),
            "neighbor_ip": dev.get("single_neighbor_ip"),
        })
        interfaces.extend(dev.get("other_interfaces") or [])
        return interfaces

    if backhaul == "dual":
        for i in ("primary", "secondary"):
            port = normalize_port(dev.get(f"{i}_port"))
            interfaces.append({
                "name": dev.get(f"{i}_if_name") or (f"Port_{port}" if port else "Port_BH"),
                "description": "BACKHAUL",
                "vlan": dev.get(f"{i}_vlan"),
                "ip": dev.get(f"{i}_ip"),
                "mtu": dev.get(f"{i}_mtu"),
                "port": dev.get(f"{i}_port") if dev.get(f"{i}_port") is not None else (
                    dev.get("aggregations")[0 if i == "primary" else 1]["name"] if aggregation_enabled and dev.get("aggregations") else None
                ),
                "neighbor_name": dev.get(f"{i}_neighbor_name"),
                "neighbor_port": dev.get(f"{i}_neighbor_port"),
                "neighbor_ip": dev.get(f"{i}_neighbor_ip"),
            })
        interfaces.extend(dev.get("other_interfaces") or [])
        return interfaces

    return dev.get("other_interfaces") or []


def render_device(dev: Dict, available_templates: Optional[List[str]] = None) -> Tuple[str, str, str]:
    if available_templates is None:
        available_templates = list_templates()

    model = str(dev.get("model") or "").strip()
    model_defaults = get_model_defaults(model)

    dev = dict(dev)  # shallow copy to avoid mutating caller
    if not dev.get("tacacs_secret"):
        dev["tacacs_secret"] = model_defaults.get("tacacs_secret")
    if not dev.get("license_keys"):
        dev["license_keys"] = model_defaults.get("license_keys", [])

    dev["interfaces"] = _build_interfaces_from_backhaul(dev)

    # Updated to pass software version
    tpl_used = choose_template(
        model, 
        dev.get("backhaul", ""), 
        dev.get("software_version", ""), 
        dev.get("role", ""), 
        available_templates
    )
    content = render_template(tpl_used, dev)
    hostname = dev.get("hostname") or "unnamed-device"
    base_fname = f"{hostname}.txt"
    return base_fname, content, tpl_used