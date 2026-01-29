from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import io
import zipfile
import re
import logging
from typing import List, Dict, Optional, Tuple

TEMPLATE_DIR = Path("templates")
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

# New SAOS 10 Specific Secret
SAOS10_SECRET = "ku34yr&oi3746t7YT5R434893"

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
    SAFE MODE: Ensures the returned template actually exists.
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

    # Priority 3: Generic SAOS 10
    if software == "saos10":
        candidates.append("ciena_saos10.cfg.j2")
        
    # Priority 4: Generic SAOS 6 (New Fallback)
    if software == "saos6":
        candidates.append("ciena_saos6.cfg.j2")

    # Priority 5: Model + Backhaul (Legacy behavior)
    if model and backhaul:
        candidates += [
            f"ciena_{model}_{backhaul}.cfg.j2",
            f"ciena_{model}_{backhaul}_backhaul.cfg.j2",
            f"ciena_{model}_{backhaul.replace('-', '_')}.cfg.j2",
        ]
        
    # Priority 6: Model + Role
    if model and role:
        candidates.append(f"ciena_{model}_{role}.cfg.j2")
        
    # Priority 7: Model only
    if model:
        candidates.append(f"ciena_{model}.cfg.j2")
        
    # Priority 8: Explicit Generic
    candidates.append("ciena_generic.cfg.j2")

    for c in candidates:
        if c in available_templates:
            return c

    # FALLBACK: Return first available or generic to avoid crash
    if available_templates:
        return available_templates[0]
    return "ciena_generic.cfg.j2"


def render_template(template_name: str, context: Dict) -> str:
    tmpl = env.get_template(template_name)
    return tmpl.render(**context)


def get_model_defaults(model: str) -> Dict[str, List[str]]:
    m = (model or "").strip()
    
    # Common secret for 39xx/51xx legacy
    legacy_secret = "#A#ZlFm6R4dQ0uR4D6rOjaXTMIoNnKVa9BP+s1VMFnBseL+AN66GjfDOwDrLXWCDUZc2dpW54ThKyWUfwFHN+CL3/B+2uqaL2URdzrB8ecyNHlfAYNWZ+1GhbOrCAJq5YwfZsPqN0yWRIfnzswlQhsJnrzTirtK/t9+3skXxLeNIZcr9hbpkGZGtzofwNs/IHA9TW21N9n61M8ms79egItUriziJoSq3XBp1FFUf1E5VRQ61CE0FKCQt+9DxjMDvPzV"
    
    defaults_map = {
        "3903": {
            "tacacs_secret": "#A#xTyOFCALzN92CljilIM/PQmofDrCIdFBXGjyCqe9TzldvYG17jjKp4xXs/25wAHlk0tq5hO9ei4C0QoI7cZckeqHNFEAS6VYCoVxXwDkJ33gvx4tm3Dn73t3sHs37DGvxPi6Mhag0jKYGu50QiD+jKbIn52PMOXOjgOyUETLvByBN4X2LSIQ1vhYPPSKjpdQ5fH1huIZgnSfJvs3p6/sqbs4Ms+u0flvn77Z1SEqFHD0vfdahHY4LM79is9ynsWu",
            "license_keys": ["W9FOI8C7N3NIB4", "WAFOI8C7N3NJB6", "W61WI8C7N3NKXB"],
        },
        "3916": {
            "tacacs_secret": legacy_secret,
            "license_keys": ["W5FNI8C7N3YNM4", "W61WI8C7N3NKXB", "W9FNI8C7N3YLM6", "WAFNI8C7N3YMM8"],
        },
        "3926": {
            "tacacs_secret": legacy_secret,
            "license_keys": ["WDFTI8C7N430RW", "W5FTI8C7N431RP", "WCFTI8C7N432RX", "W6FTI8C7N433RS"],
        },
        "3928": {
            "tacacs_secret": legacy_secret,
            "license_keys": ["WDFUI8C7N3NLBH", "W5FUI8C7N4ZEN3", "WCFUI8C7N3NMBH", "W6FUI8C7N3NNBC"],
        },
        "5142": {"tacacs_secret": legacy_secret, "license_keys": ["<5142-KEY-PLACEHOLDER>"]},
        "5130": {"tacacs_secret": SAOS10_SECRET, "license_keys": []},
        "5171": {"tacacs_secret": SAOS10_SECRET, "license_keys": []},
        "8110": {"tacacs_secret": SAOS10_SECRET, "license_keys": []},
        "8114": {"tacacs_secret": SAOS10_SECRET, "license_keys": []},
    }
    return defaults_map.get(m, {
        "tacacs_secret": "vault://ciena/default/tacacs",
        "license_keys": ["<LICENSE-PLACEHOLDER-1>"]
    })


def safe_filename(s: str) -> str:
    s = re.sub(r"\s+", "_", s)
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)


def create_zip_from_dict(files: Dict[str, str]) -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for fname, content in files.items():
            z.writestr(fname, content)
    return mem.getvalue()


def _derive_interface_name(local_host: str, remote_host: str) -> str:
    """
    Smartly derives an Interface Name (<= 15 chars) from various hostname formats.
    Supports SAOS 10 (NGA-AJO...) and Legacy 39XX (A_steel_sagamu...).
    """
    if not local_host or not remote_host:
        return ""

    def clean_id(hostname: str) -> str:
        # Standard SAOS 10: NGA-AJO-CNA5130-01 -> AJO
        parts_dash = hostname.split('-')
        if len(parts_dash) >= 3 and len(parts_dash[1]) == 3 and parts_dash[1].isalpha():
            return parts_dash[1]
        
        # Legacy: A_steel_sagamu_3903 -> A_steel
        # Remove trailing models/indices
        base = re.sub(r'(_39\d{2}|_51\d{2}|_81\d{2}|_0\d|-0\d)+$', '', hostname, flags=re.IGNORECASE)
        parts_score = base.split('_')
        
        # Heuristic: If first part is single char (A_Steel), take first two.
        if len(parts_score) > 1 and len(parts_score[0]) == 1:
            return f"{parts_score[0]}_{parts_score[1]}"
        return parts_score[0]

    def get_model(hostname: str) -> str:
        # Extract model number (e.g. 8114, 3903) from remote host
        match = re.search(r'(\d{4})', hostname)
        return match.group(1) if match else ""

    local_id = clean_id(local_host)
    remote_id = clean_id(remote_host)
    remote_model = get_model(remote_host)

    # Strategy: Local-RemoteModel
    # Example: A_steel-SAK8110
    
    # 1. Try Full: L-RM
    candidate = f"{local_id}-{remote_id}{remote_model}"
    if len(candidate) <= 15:
        return candidate
    
    # 2. Try without model: L-R
    candidate = f"{local_id}-{remote_id}"
    if len(candidate) <= 15:
        return candidate

    # 3. Truncate to fit 15 chars (Max safe limit for interface names)
    # Give roughly equal weight, slightly favoring Remote to distinguish
    # limit is 15. hyphen is 1. 14 chars remain. 7 each.
    l_short = local_id[:7]
    r_short = remote_id[:7]
    return f"{l_short}-{r_short}"


def _build_interfaces_from_backhaul(dev: Dict) -> List[Dict]:
    interfaces = []
    backhaul = dev.get("backhaul", "") or ""
    aggregation_enabled = bool(dev.get("aggregation_enabled"))
    local_host = dev.get("hostname", "")

    def normalize_port(port_raw):
        if isinstance(port_raw, (list, tuple)):
            return str(port_raw[0]) if port_raw else ""
        return str(port_raw or "")

    def create_iface(prefix, idx):
        port_raw = dev.get(f"{prefix}_port")
        port = normalize_port(port_raw)
        
        neighbor = dev.get(f"{prefix}_neighbor_name")
        
        # Generate Smart Name if not provided explicitly
        # Use existing input if user typed one, otherwise generate
        manual_name = dev.get(f"{prefix}_if_name")
        
        # Check if the manual name looks like a default "Port_X" or is empty
        # If it is default/empty, we try to generate a smarter one
        is_default_name = not manual_name or manual_name.startswith("Port_")
        
        smart_name = ""
        if neighbor:
            smart_name = _derive_interface_name(local_host, neighbor)
        
        # Final name selection:
        # 1. Use Smart Name if generated and manual was default/empty
        # 2. Use Manual Name if user typed something specific
        # 3. Fallback to Port_X
        if smart_name and is_default_name:
            final_name = smart_name
        else:
            final_name = manual_name or (f"Port_{port}" if port else "Port_BH")

        return {
            "name": final_name,
            "description": "BACKHAUL",
            "vlan": dev.get(f"{prefix}_vlan"),
            "ip": dev.get(f"{prefix}_ip"),
            "mtu": dev.get(f"{prefix}_mtu"),
            "port": dev.get("aggregation_name") if aggregation_enabled and backhaul == "single" else (
                dev.get("aggregations")[idx]["name"] if aggregation_enabled and backhaul == "dual" else port
            ),
            "neighbor_name": neighbor,
            "neighbor_port": dev.get(f"{prefix}_neighbor_port"),
            "neighbor_ip": dev.get(f"{prefix}_neighbor_ip"),
            "saos10_link_id": smart_name # Keep for templates explicitly asking for it
        }

    if backhaul == "single":
        interfaces.append(create_iface("single", 0))
    elif backhaul == "dual":
        interfaces.append(create_iface("primary", 0))
        interfaces.append(create_iface("secondary", 1))

    interfaces.extend(dev.get("other_interfaces") or [])
    return interfaces


def render_device(dev: Dict, available_templates: Optional[List[str]] = None) -> Tuple[str, str, str]:
    if available_templates is None:
        available_templates = list_templates()

    model = str(dev.get("model") or "").strip()
    model_defaults = get_model_defaults(model)

    dev = dict(dev)  # shallow copy
    if not dev.get("tacacs_secret"):
        dev["tacacs_secret"] = model_defaults.get("tacacs_secret")
    if not dev.get("license_keys"):
        dev["license_keys"] = model_defaults.get("license_keys", [])

    dev["interfaces"] = _build_interfaces_from_backhaul(dev)

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