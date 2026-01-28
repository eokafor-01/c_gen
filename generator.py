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

    # Priority 3: Generic SAOS 10 (Fallback for all saos10 devices)
    if software == "saos10":
        candidates.append("ciena_saos10.cfg.j2")

    # Priority 4: Model + Backhaul (Legacy behavior)
    if model and backhaul:
        candidates += [
            f"ciena_{model}_{backhaul}.cfg.j2",
            f"ciena_{model}_{backhaul}_backhaul.cfg.j2",
            f"ciena_{model}_{backhaul.replace('-', '_')}.cfg.j2",
        ]
        
    # Priority 5: Model + Role
    if model and role:
        candidates.append(f"ciena_{model}_{role}.cfg.j2")
        
    # Priority 6: Model only
    if model:
        candidates.append(f"ciena_{model}.cfg.j2")
        
    # Priority 7: Explicit Generic
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


def _derive_saos10_link_id(local_host: str, remote_host: str) -> str:
    """
    Generates a link ID like 'AJO-IKJ8114' from hostnames.
    Pattern: LocalSite-RemoteSiteRemoteModel
    Example:
      Local: NGA-AJO-CNA5130-01 -> AJO
      Remote: NGA-IKJ-CNA8114-01 -> IKJ, 8114
      Result: AJO-IKJ8114
    """
    if not local_host or not remote_host:
        return ""
    
    # Extract Site (between first and second hyphen usually)
    # NGA-AJO-... or AJO-...
    def extract_site(s):
        parts = s.split('-')
        if len(parts) >= 2:
            # If starts with NGA, take 2nd part. 
            if len(parts[0]) == 3 and parts[0].isalpha(): 
                return parts[1]
            return parts[0] # Fallback
        return s

    local_site = extract_site(local_host)
    remote_site = extract_site(remote_host)

    # Extract Model from Remote (digits in the 3rd chunk usually)
    # NGA-IKJ-CNA8114-01 -> 8114
    remote_model = ""
    match = re.search(r"[A-Z]+(\d{4})", remote_host) # matches CNA8114
    if match:
        remote_model = match.group(1)

    return f"{local_site}-{remote_site}{remote_model}"


def _build_interfaces_from_backhaul(dev: Dict) -> List[Dict]:
    interfaces = []
    backhaul = dev.get("backhaul", "") or ""
    aggregation_enabled = bool(dev.get("aggregation_enabled"))
    is_saos10 = dev.get("software_version") == "saos10"
    local_host = dev.get("hostname", "")

    def normalize_port(port_raw):
        if isinstance(port_raw, (list, tuple)):
            return str(port_raw[0]) if port_raw else ""
        return str(port_raw or "")

    def create_iface(prefix, idx):
        port_raw = dev.get(f"{prefix}_port")
        port = normalize_port(port_raw)
        
        # Name logic: SAOS 6/8 uses Port_X, SAOS 10 uses Link ID if avail
        base_name = dev.get(f"{prefix}_if_name") or (f"Port_{port}" if port else "Port_BH")
        neighbor = dev.get(f"{prefix}_neighbor_name")
        
        link_id = ""
        if is_saos10 and neighbor:
            link_id = _derive_saos10_link_id(local_host, neighbor)

        return {
            "name": base_name,
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
            "saos10_link_id": link_id # Pass generated ID to template
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